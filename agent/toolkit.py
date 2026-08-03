import json
import uuid
from pathlib import Path

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


# HTTP-вызовы GET с обработкой ошибок
def _http_get(url: str) -> dict:
    try:
        resp = httpx.get(url, timeout=5.0)
    except httpx.HTTPError as exc:
        return {'error': f'Сервис недоступен: {type(exc).__name__}'}
    if resp.status_code == 200:
        return resp.json()
    detail = ''
    try:
        detail = resp.json().get('detail', '')
    except json.JSONDecodeError:
        pass
    return {'error': f'HTTP {resp.status_code}', 'detail': detail}

# HTTP-вызовы POST с обработкой ошибок
def _http_post(url: str, params: dict | None = None) -> dict:
    try:
        resp = httpx.post(url, params=params, timeout=5.0)
    except httpx.HTTPError as exc:
        return {'error': f'Сервис недоступен: {type(exc).__name__}'}
    if resp.status_code == 200:
        return resp.json()
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