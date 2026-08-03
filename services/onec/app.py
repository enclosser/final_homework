"""Эмулятор 1С:Предприятие.

Мок-данные пользователей и сессий хранятся в ``mock_data.json``
(пользователи — по e-mail, сессии — по числовым id). Эндпоинты изменяют
данные в памяти (учебный проект).
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

app = FastAPI(
    title='1С Service',
    description='Эмулятор 1С:Предприятие: базы, сессии, пользователи.',
    version='0.2.0',
)

# Загружаем мок-данные из JSON-файла, лежащего рядом с приложением.
_DATA_FILE = Path(__file__).parent / 'mock_data.json'
_DATA = json.loads(_DATA_FILE.read_text(encoding='utf-8'))
USERS = _DATA['users']
# Ключи сессий в JSON — строки, для эндпоинтов удобнее числовые id.
SESSIONS = {int(session_id): session for session_id, session in _DATA['sessions'].items()}


@app.get('/sessions')
def list_sessions() -> dict:
    """Вернуть список активных сессий."""
    return {'sessions': [{'id': session_id, **session} for session_id, session in SESSIONS.items()]}


@app.post('/sessions/{session_id}/terminate')
def terminate_session(session_id: int) -> dict:
    """Принудительно завершить сессию пользователя."""
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail=f'Сессия {session_id} не найдена')
    del SESSIONS[session_id]
    return {'session_id': session_id, 'terminated': True}


@app.post('/users/{email}/unlock')
def unlock_user(email: str) -> dict:
    """Разблокировать пользователя."""
    if email not in USERS:
        raise HTTPException(status_code=404, detail=f'Пользователь {email} не найден')
    USERS[email]['locked'] = False
    return {'email': email, 'unlocked': True}