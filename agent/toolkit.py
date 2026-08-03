import json
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from agent import rag
from config import settings

TOOL_DIR = Path(__file__).resolve().parent / 'tools'


def _load_tools() -> tuple[list[dict], set[str]]:
    """Загрузить описания инструментов и множество чувствительных операций."""
    tools: list[dict] = []
    sensitive: set[str] = set()
    for path in sorted(TOOL_DIR.glob('*.json')):
        spec = json.loads(path.read_text(encoding='utf-8'))
        if spec.pop('sensitive', False):
            sensitive.add(spec['name'])
        tools.append({'type': 'function', 'function': spec})
    return tools, sensitive


TOOLS, SENSITIVE = _load_tools()


class CircuitBreaker:
    """Предохранитель: размыкает цепь после серии сбоев сервиса.
    """

    def __init__(self, threshold: int = 3, reset_seconds: float = 30.0):
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self._failures: dict[tuple, int] = {}
        self._open_until: dict[tuple, float] = {}

    def is_open(self, key: tuple) -> bool:
        return time.time() < self._open_until.get(key, 0.0)

    def record_success(self, key: tuple) -> None:
        self._failures.pop(key, None)
        self._open_until.pop(key, None)

    def record_failure(self, key: tuple) -> None:
        self._failures[key] = self._failures.get(key, 0) + 1
        if self._failures[key] >= self.threshold:
            self._open_until[key] = time.time() + self.reset_seconds


breaker = CircuitBreaker()


def _service_key(url: str) -> tuple:
    """Ключ сервиса для circuit breaker (host, port)."""
    parsed = urlparse(url)
    return parsed.hostname or '', parsed.port or 0


# HTTP-вызовы GET с обработкой ошибок
def _http_get(url: str) -> dict:
    key = _service_key(url)
    if breaker.is_open(key):
        return {'error': 'Сервис недоступен: circuit breaker открыт', 'circuit_open': True}
    try:
        resp = httpx.get(url, timeout=5.0)
    except httpx.HTTPError as exc:
        breaker.record_failure(key)
        return {'error': f'Сервис недоступен: {type(exc).__name__}'}
    if resp.status_code == 200:
        breaker.record_success(key)
        return resp.json()
    if resp.status_code >= 500:
        breaker.record_failure(key)
    detail = ''
    try:
        detail = resp.json().get('detail', '')
    except json.JSONDecodeError:
        pass
    return {'error': f'HTTP {resp.status_code}', 'detail': detail}

# HTTP-вызовы POST с обработкой ошибок
def _http_post(url: str, params: dict | None = None) -> dict:
    key = _service_key(url)
    if breaker.is_open(key):
        return {'error': 'Сервис недоступен: circuit breaker открыт', 'circuit_open': True}
    try:
        resp = httpx.post(url, params=params, timeout=5.0)
    except httpx.HTTPError as exc:
        breaker.record_failure(key)
        return {'error': f'Сервис недоступен: {type(exc).__name__}'}
    if resp.status_code == 200:
        breaker.record_success(key)
        return resp.json()
    if resp.status_code >= 500:
        breaker.record_failure(key)
    detail = ''
    try:
        detail = resp.json().get('detail', '')
    except json.JSONDecodeError:
        pass
    return {'error': f'HTTP {resp.status_code}', 'detail': detail}


def _escalate(args: dict) -> dict:
    ticket_id = f'T-{uuid.uuid4().hex[:8].upper()}'
    return {
        'escalated': True,
        'ticket_id': ticket_id,
        'reason': args.get('reason', ''),
        'message': 'Обращение передано специалисту технической поддержки.',
    }


# Обработчики инструментов
_HANDLERS = {
    'search_knowledge_base': lambda args: {'results': rag.search(args['query'])},
    'get_ldap_user': lambda args: _http_get(f"{settings.LDAP_BASE_URL}/users/{args['email']}"),
    'unlock_ldap_user': lambda args: _http_post(f"{settings.LDAP_BASE_URL}/users/{args['email']}/unlock"),
    'reset_ldap_password': lambda args: _http_post(f"{settings.LDAP_BASE_URL}/users/{args['email']}/reset_password"),
    'get_exchange_mailbox': lambda args: _http_get(f"{settings.EXCHANGE_BASE_URL}/mailboxes/{args['email']}"),
    'set_exchange_quota': lambda args: _http_post(
        f"{settings.EXCHANGE_BASE_URL}/mailboxes/{args['email']}/set_quota",
        params={'quota_mb': args['quota_mb']},
    ),
    'list_1c_sessions': lambda args: _http_get(f'{settings.ONEC_BASE_URL}/sessions'),
    'terminate_1c_session': lambda args: _http_post(f"{settings.ONEC_BASE_URL}/sessions/{args['session_id']}/terminate"),
    'unlock_1c_user': lambda args: _http_post(f"{settings.ONEC_BASE_URL}/users/{args['email']}/unlock"),
    'escalate_to_human': _escalate,
}


def _validate(name: str, args: dict) -> str | None:
    """Проверка аргументов инструмента. Возвращает описание ошибки или None..
    """

    def _ok_email(value) -> bool:
        return isinstance(value, str) and value.count('@') == 1 and value.split('@')[1]

    email_tools = {'get_ldap_user', 'unlock_ldap_user', 'reset_ldap_password',
                   'get_exchange_mailbox', 'unlock_1c_user'}
    if name in email_tools and not _ok_email(args.get('email')):
        return 'Некорректный email'
    if name == 'set_exchange_quota':
        if not _ok_email(args.get('email')):
            return 'Некорректный email'
        quota = args.get('quota_mb')
        if not isinstance(quota, int) or not 1000 <= quota <= 1_000_000:
            return 'Квота должна быть целым числом от 1000 до 1000000 МБ'
    if name == 'terminate_1c_session':
        if not isinstance(args.get('session_id'), int) or args.get('session_id') <= 0:
            return 'Некорректный id сессии'
    if name == 'search_knowledge_base':
        if not isinstance(args.get('query'), str) or not args.get('query', '').strip():
            return 'Пустой запрос к базе знаний'
    if name == 'escalate_to_human':
        if not isinstance(args.get('reason'), str) or not args.get('reason', '').strip():
            return 'Не указана причина эскалации'
    return None


def execute_tool(name: str, args: dict, confirm=None) -> dict:
    """Выполнить инструмент. Для чувствительных — запросить подтверждение.

    Для чувствительных операций в результат добавляется `confirmed`:
    True — подтверждено и выполнено,
    False — отменено пользователем.
    """
    if name in SENSITIVE:
        allowed = confirm(name, args) if confirm else True
        if not allowed:
            return {'confirmed': False, 'message': 'Операция отменена пользователем.'}
        is_sensitive = True
    else:
        is_sensitive = False
    error = _validate(name, args)
    if error:
        return {'error': f'Некорректные аргументы: {error}'}
    handler = _HANDLERS.get(name)
    if handler is None:
        return {'error': f'Неизвестный инструмент: {name}'}
    try:
        result = handler(args)
    except Exception as exc:  # noqa: BLE001 — последний рубеж защиты
        return {'error': f'Не удалось выполнить {name}: {exc!r}'}
    if is_sensitive:
        return {'confirmed': True, **result}
    return result


def get_ldap_user(email: str) -> dict:
    """Проверка пользователя для идентификации в консоли."""
    return _http_get(f'{settings.LDAP_BASE_URL}/users/{email}')