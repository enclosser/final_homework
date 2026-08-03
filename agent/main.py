import json
import sys
from pathlib import Path

# Проверяем, что корень проекта доступен в sys.path при запуске
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import orchestrator as agent_graph
from agent import rag, toolkit
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
        result = app.invoke(initial)
        final = result.get('final') or 'Не удалось сформировать ответ.'
        history.append({'role': 'user', 'content': user_input})
        history.append({'role': 'assistant', 'content': final})
        print(f'\n🤖 Ассистент: {final}')

    return 0


if __name__ == '__main__':
    sys.exit(main())