import json
import sys
import time

from agent import metrics, rag, toolkit
from agent import orchestrator as agent_graph
from config import settings

EXIT_WORDS = {'exit', 'quit', 'q', 'выход'}


def _confirm(name: str, args: dict) -> bool:
    """Запрос подтверждения чувствительной операции (guardrail)."""
    print(f'\n⚠️  Чувствительная операция: {name} {json.dumps(args, ensure_ascii=False)}')
    answer = input('    Подтвердить выполнение? [y/N]: ').strip().lower()
    return answer in {'y', 'yes', 'да'}


def ask_email() -> str:
    """Идентификация пользователя: почта проверяется в LDAP."""
    print('Добро пожаловать в ИИ-ассистента технической поддержки.')
    print('Сначала укажите вашу корпоративную почту.')
    while True:
        email = input('\nПочта: ').strip().lower()
        if not email:
            continue
        result = toolkit.get_ldap_user(email)
        if 'error' in result:
            print(f'  Не удалось подтвердить почту: {result["error"]}')
            print('  Попробуйте ещё раз (пример: ivanov@corp.local)')
            continue
        print(f'  Здравствуйте, {email}! Опишите вашу проблему.')
        return email


def _outcome(result: dict, raw_final: str | None) -> str:
    """Классифицировать исход запуска для метрик: resolved / escalated / failed."""
    if result.get('escalated'):
        return 'escalated'
    if raw_final and raw_final.strip():
        return 'resolved'
    return 'failed'


def main() -> int:
    print(f'LLM: {settings.LM_STUDIO_HOST}')
    print(f'Тяжёлая модель: {settings.LM_STUDIO_MODEL_HEAVY}')
    print(f'Лёгкая модель: {settings.LM_STUDIO_MODEL_LIGHT}')

    try:
        n_docs = rag.ensure_index()
        print(f'Векторная память: {n_docs} документов в базе знаний.')
    except Exception as exc:  # noqa: BLE001
        print(f'⚠️  Не удалось инициализировать базу знаний: {exc!r}')
        print('   Агент продолжит работу без RAG.')

    email = ask_email()
    app = agent_graph.build_graph(confirm=_confirm)
    # История диалога (пользователь/ассистент) — передаётся в каждый запуск графа,
    # чтобы агент помнил предыдущие обращения (например, подтверждение «да»).
    history: list[dict[str, str]] = []

    while True:
        try:
            user_input = input('\nВы> ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nДо свидания!')
            break
        if user_input.lower() in EXIT_WORDS:
            print('До свидания!')
            break
        if not user_input:
            continue

        initial = {
            'email': email,
            'user_input': user_input,
            'history': history,
            'steps': 0,
            'limit_note_sent': False,
            'tools_used': 0,
            'nudged': False,
        }
        started = time.monotonic()
        result = app.invoke(initial)
        duration = time.monotonic() - started
        raw_final = result.get('final')
        final = raw_final or 'Не удалось сформировать ответ.'
        outcome = _outcome(result, raw_final)
        history.append({'role': 'user', 'content': user_input})
        history.append({'role': 'assistant', 'content': final})
        metrics.record_run({
            'source': 'interactive',
            'email': email,
            'user_input': user_input,
            'topic': result.get('topic', ''),
            'duration_sec': round(duration, 2),
            'llm_calls': result.get('llm_calls', 0),
            'prompt_tokens': result.get('prompt_tokens', 0),
            'completion_tokens': result.get('completion_tokens', 0),
            'tools_used': result.get('tools_used', 0),
            'escalated': result.get('escalated', False),
            'outcome': outcome,
            'final_len': len(final),
        })
        print(f'\n🤖 Ассистент: {final}')
        pt = result.get('prompt_tokens', 0)
        ct = result.get('completion_tokens', 0)
        print(f'⏱ {duration:.1f}s · LLM-вызовов {result.get("llm_calls", 0)} · '
              f'токенов {pt + ct} · ≈ ${metrics.compute_cost(pt, ct):.4f}')

    return 0


if __name__ == '__main__':
    sys.exit(main())