import json
import sys
import time
from pathlib import Path

from agent import metrics, rag
from agent import orchestrator as agent_graph

SCENARIOS_FILE = Path(__file__).resolve().parent.parent / 'evaluation' / 'scenarios.json'


def _outcome(result: dict) -> str:
    """Классифицировать исход запуска: resolved / escalated / failed."""
    if result.get('escalated'):
        return 'escalated'
    if (result.get('final') or '').strip():
        return 'resolved'
    return 'failed'


def main() -> int:
    scenarios = json.loads(SCENARIOS_FILE.read_text(encoding='utf-8'))
    app = agent_graph.build_graph(confirm=lambda name, args: True)  # авто-подтверждение
    rag.ensure_index(force=False)

    print(f'Оценка {len(scenarios)} сценариев...\n')
    passed = 0
    for s in scenarios:
        started = time.monotonic()
        result = app.invoke({
            'email': s['email'],
            'user_input': s['user_input'],
            'history': [],
            'steps': 0,
            'limit_note_sent': False,
            'tools_used': 0,
            'nudged': False,
        })
        duration = time.monotonic() - started
        outcome = _outcome(result)
        ok = outcome == s['expect']
        passed += ok
        metrics.record_run({
            'source': 'evaluation',
            'scenario': s['name'],
            'email': s['email'],
            'user_input': s['user_input'],
            'duration_sec': round(duration, 2),
            'llm_calls': result.get('llm_calls', 0),
            'prompt_tokens': result.get('prompt_tokens', 0),
            'completion_tokens': result.get('completion_tokens', 0),
            'tools_used': result.get('tools_used', 0),
            'escalated': result.get('escalated', False),
            'outcome': outcome,
            'expected': s['expect'],
            'final_len': len(result.get('final') or ''),
        })
        print(f"[{'OK' if ok else 'FAIL'}] {s['name']}: {outcome} (ожид. {s['expect']}) "
              f"— {duration:.1f}s, tools={result.get('tools_used')}, "
              f"tokens={result.get('prompt_tokens', 0) + result.get('completion_tokens', 0)}, "
              f"≈${metrics.compute_cost(result.get('prompt_tokens', 0), result.get('completion_tokens', 0)):.4f}")

    print(f'\nИтог: {passed}/{len(scenarios)} сценариев прошли')
    print('Сводные метрики за прогон:')
    for key, value in metrics.summarize().items():
        print(f'  {key}: {value}')
    return 0 if passed == len(scenarios) else 1


if __name__ == '__main__':
    sys.exit(main())