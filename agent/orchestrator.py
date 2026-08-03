import json
import time
from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from agent import llm, toolkit
from agent.trace import log_step
from config import settings

MAX_STEPS = 6

PROMPT_DIR = Path(__file__).resolve().parent / 'prompts'


def _load_prompt(name: str) -> str:
    """Прочитать текст промта из agent/prompts/<name>.json."""
    return json.loads((PROMPT_DIR / f'{name}.json').read_text(encoding='utf-8'))['content']


LIMIT_NOTE = _load_prompt('limit_note')
CLASSIFY_PROMPT = _load_prompt('classify')
SYSTEM_TEMPLATE = _load_prompt('system')
NUDGE_PROMPT = _load_prompt('nudge')

# Какой инструмент проверки рекомендовать для каждой темы (шаг nudge)
_DIAGNOSTIC_TOOL = {
    'ldap': ('get_ldap_user', 'проверить состояние учётной записи'),
    'exchange': ('get_exchange_mailbox', 'проверить состояние почтового ящика'),
    'onec': ('list_1c_sessions', 'посмотреть активные сессии'),
}


class AgentState(TypedDict, total=False):
    email: str
    user_input: str
    topic: str
    history: list[dict[str, str]]
    messages: list[dict[str, Any]]
    pending_tools: list[dict[str, Any]]
    final: str
    steps: int
    limit_note_sent: bool
    tools_used: int
    nudged: bool


def build_system_prompt(email: str) -> str:
    """Собрать системный промт для конкретного заявителя."""
    return SYSTEM_TEMPLATE.format(email=email)


def _parse_arguments(raw: str) -> dict:
    """Разобрать JSON-аргументы инструмента; при ошибке вернуть их сырыми."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {'_parse_error': raw}


def _short(result: dict, limit: int = 200) -> str:
    """Короткое текстовое представление результата инструмента для лога."""
    text = json.dumps(result, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + '…'


def classify(state: AgentState) -> dict:
    """Лёгкая модель определяет тему обращения и собирает стартовые сообщения."""
    started = time.monotonic()
    msg, _ = llm.complete(
        [
            {'role': 'system', 'content': CLASSIFY_PROMPT},
            {'role': 'user', 'content': state['user_input']},
        ],
        route='light',
    )
    text = (msg.content or '').strip().lower()
    topic = next((t for t in ('ldap', 'exchange', 'onec') if t in text), 'other')

    messages = [
        {'role': 'system', 'content': build_system_prompt(state['email'])},
        *state.get('history', []),
        {'role': 'system', 'content': f'Предварительная тема обращения: {topic}.'},
        {'role': 'user', 'content': state['user_input']},
    ]
    log_step('classify', detail=f'тема={topic}', model=settings.LM_STUDIO_MODEL_LIGHT,
             seconds=time.monotonic() - started)
    return {'topic': topic, 'messages': messages, 'pending_tools': [],
            'tools_used': 0, 'nudged': False}


def decide(state: AgentState) -> dict:
    """Тяжёлая модель: выбирает инструменты для вызова или даёт финальный ответ.
    """
    started = time.monotonic()
    limit_reached = state.get('limit_note_sent', False)

    resp = llm.chat(state['messages'], route='heavy', tools=toolkit.TOOLS)
    msg = resp.choices[0].message

    new_messages = state['messages'] + [{'role': 'assistant', 'content': msg.content or ''}]
    pending: list[dict[str, Any]] = []
    final = None

    if msg.tool_calls and not limit_reached:
        pending = [
            {'id': tc.id, 'name': tc.function.name, 'arguments': tc.function.arguments}
            for tc in msg.tool_calls
        ]
        new_messages[-1]['tool_calls'] = [
            {'id': tc.id, 'type': 'function',
             'function': {'name': tc.function.name, 'arguments': tc.function.arguments}}
            for tc in msg.tool_calls
        ]
        detail = ', '.join(tc.function.name for tc in msg.tool_calls)
    else:
        final = msg.content or ('Обращение передано специалисту.' if limit_reached else '')
        detail = 'финальный ответ'

    log_step('decide', detail=detail, model=settings.LM_STUDIO_MODEL_HEAVY,
             seconds=time.monotonic() - started)
    return {'messages': new_messages, 'pending_tools': pending, 'final': final}


def route_decide(state: AgentState) -> str:
    """Куда идти после `decide`: исполнять инструменты, напомнить про проверку или завершить."""
    if state.get('pending_tools'):
        return 'act'
    # Модель ответила без единого вызова инструмента по теме поддержки — напомним проверить.
    if state.get('topic') != 'other' and state.get('tools_used', 0) == 0 and not state.get('nudged'):
        return 'nudge'
    return END


def nudge(state: AgentState) -> dict:
    """Напомнить модели подтвердить состояние системы инструментом, если она ответила без вызовов.
    """
    tool, reason = _DIAGNOSTIC_TOOL.get(
        state['topic'],
        ('search_knowledge_base', 'найти информацию по проблеме'),
    )
    note = NUDGE_PROMPT.format(tool=tool, reason=reason)
    messages = state['messages'] + [{'role': 'system', 'content': note}]
    log_step('nudge', detail=f'напоминание: вызвать {tool}')
    return {'messages': messages, 'nudged': True}


def build_graph(confirm: Callable[[str, dict], bool] | None = None):
    """Собрать граф. `confirm(name, args)` — подтверждение чувствительных операций."""

    def act(state: AgentState) -> dict:
        """Исполнить запрошенные моделью инструменты и вернуть результаты модели.
        """
        new_messages = list(state['messages'])
        for tc in state['pending_tools']:
            started = time.monotonic()
            args = _parse_arguments(tc['arguments'])
            result = toolkit.execute_tool(tc['name'], args, confirm=confirm)
            new_messages.append({
                'role': 'tool',
                'tool_call_id': tc['id'],
                'content': json.dumps(result, ensure_ascii=False),
            })
            log_step('act', detail=f"{tc['name']} -> {_short(result)}",
                     seconds=time.monotonic() - started)

        steps = state.get('steps', 0) + 1
        limit_note_sent = state.get('limit_note_sent', False)
        if steps >= MAX_STEPS and not limit_note_sent:
            new_messages.append({'role': 'system', 'content': LIMIT_NOTE})
            limit_note_sent = True
        return {'messages': new_messages, 'pending_tools': [], 'steps': steps,
                'limit_note_sent': limit_note_sent,
                'tools_used': state.get('tools_used', 0) + len(state['pending_tools'])}

    builder = StateGraph(AgentState)
    builder.add_node('classify', classify)
    builder.add_node('decide', decide)
    builder.add_node('act', act)
    builder.add_node('nudge', nudge)
    builder.add_edge(START, 'classify')
    builder.add_edge('classify', 'decide')
    builder.add_conditional_edges('decide', route_decide, {'act': 'act', 'nudge': 'nudge', END: END})
    builder.add_edge('act', 'decide')
    builder.add_edge('nudge', 'decide')
    return builder.compile()
