import json
import time

from config import settings

TRACE_FILE = settings.TRACE_FILE


def log_step(step: str, *, detail: str = '', model: str = '', seconds: float = 0.0, **extra) -> None:
    """Записать один шаг агентного цикла."""
    record = {
        'ts': round(time.time(), 3),
        'step': step,
        'detail': detail,
        'model': model,
        'seconds': round(seconds, 3),
        **extra,
    }

    TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with TRACE_FILE.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')

    model_tag = f' [{model}]' if model else ''
    secs = f' ({seconds:.1f}s)' if seconds else ''

    print(f'  ∎ {step}{model_tag}{secs}: {detail}')
