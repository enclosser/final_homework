import json
import sys
import time

from config import settings


def compute_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Условная стоимость токенов по тарифам из настроек."""
    return (prompt_tokens / 1000 * settings.COST_PER_1K_INPUT
            + completion_tokens / 1000 * settings.COST_PER_1K_OUTPUT)


def record_run(run: dict) -> None:
    """Записать метрики одного запуска агента.

    Если переданы токены и не задана стоимость — автоматически добавляется cost_usd.
    """
    if 'cost_usd' not in run and ('prompt_tokens' in run or 'completion_tokens' in run):
        run = {**run, 'cost_usd': round(
            compute_cost(run.get('prompt_tokens', 0), run.get('completion_tokens', 0)), 4)}
    record = {**run, 'ts': round(time.time(), 3)}
    settings.METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with settings.METRICS_FILE.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')


def _read_runs() -> list[dict]:
    if not settings.METRICS_FILE.exists():
        return []
    runs = []
    for line in settings.METRICS_FILE.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line:
            runs.append(json.loads(line))
    return runs


def summarize() -> dict:
    """Агрегировать метрики из накопленных запусков."""
    runs = _read_runs()
    if not runs:
        return {'runs': 0}

    total_input = sum(r.get('prompt_tokens', 0) for r in runs)
    total_output = sum(r.get('completion_tokens', 0) for r in runs)
    total_sec = sum(r.get('duration_sec', 0) for r in runs)
    resolved = sum(1 for r in runs if r.get('outcome') == 'resolved')
    escalated = sum(1 for r in runs if r.get('outcome') == 'escalated')
    failed = sum(1 for r in runs if r.get('outcome') == 'failed')
    cost = compute_cost(total_input, total_output)

    return {
        'runs': len(runs),
        'resolved': resolved,
        'escalated': escalated,
        'failed': failed,
        'success_rate': round((resolved + escalated) / len(runs), 2),
        'total_sec': round(total_sec, 1),
        'avg_sec_per_run': round(total_sec / len(runs), 1),
        'total_tokens': total_input + total_output,
        'avg_tokens_per_run': round((total_input + total_output) / len(runs), 1),
        'estimated_cost_usd': round(cost, 4),
    }


def main() -> int:
    """CLI-отчёт по метрикам."""
    report = summarize()
    if report.get('runs', 0) == 0:
        print('Метрики пусты — сначала запустите агента (python main.py) '
              'или оценку (python -m agent.evaluate).')
        return 0
    print('=== Метрики агента ===')
    for key, value in report.items():
        print(f'  {key}: {value}')
    return 0


if __name__ == '__main__':
    sys.exit(main())