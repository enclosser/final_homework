import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

app = FastAPI(
    title='Exchange Service',
    description='Эмулятор Microsoft Exchange: почтовые ящики, доставка, OWA.',
    version='0.2.0',
)

# Загружаем мок-данные из JSON-файла, лежащего рядом с приложением.
_DATA_FILE = Path(__file__).parent / 'mock_data.json'
MAILBOXES = json.loads(_DATA_FILE.read_text(encoding='utf-8'))['mailboxes']


@app.get('/mailboxes/{email}')
def get_mailbox(email: str) -> dict:
    """Вернуть состояние почтового ящика пользователя."""
    if email not in MAILBOXES:
        raise HTTPException(status_code=404, detail=f'Ящик {email} не найден')
    return {'email': email, **MAILBOXES[email]}


@app.post('/mailboxes/{email}/set_quota')
def set_quota(email: str, quota_mb: int) -> dict:
    """Установить квоту почтового ящика (например, временно увеличить)."""
    if email not in MAILBOXES:
        raise HTTPException(status_code=404, detail=f'Ящик {email} не найден')
    MAILBOXES[email]['quota_mb'] = quota_mb
    return {'email': email, 'quota_mb': quota_mb}