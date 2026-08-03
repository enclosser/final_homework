"""Эмулятор LDAP-каталога.

Мок-данные пользователей хранятся в ``mock_data.json`` (ключ — e-mail).
Эндпоинты принимают e-mail и изменяют данные в памяти
(учебный проект, без реальных паролей).
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

app = FastAPI(
    title='LDAP Service',
    description='Эмулятор LDAP-каталога: пользователи, пароли, блокировки.',
    version='0.2.0',
)

# Загружаем мок-данные из JSON-файла, лежащего рядом с приложением.
_DATA_FILE = Path(__file__).parent / 'mock_data.json'
USERS = json.loads(_DATA_FILE.read_text(encoding='utf-8'))['users']


@app.get('/users/{email}')
def get_user(email: str) -> dict:
    """Вернуть состояние учётной записи пользователя."""
    if email not in USERS:
        raise HTTPException(status_code=404, detail=f'Пользователь {email} не найден')
    return {'email': email, **USERS[email]}


@app.post('/users/{email}/unlock')
def unlock_user(email: str) -> dict:
    """Разблокировать учётную запись."""
    if email not in USERS:
        raise HTTPException(status_code=404, detail=f'Пользователь {email} не найден')
    USERS[email]['locked'] = False
    return {'email': email, 'unlocked': True}


@app.post('/users/{email}/reset_password')
def reset_password(email: str) -> dict:
    """Сбросить пароль (в учебном проекте — просто помечаем смену)."""
    if email not in USERS:
        raise HTTPException(status_code=404, detail=f'Пользователь {email} не найден')
    USERS[email]['password_expired'] = True
    return {'email': email, 'password_reset': True}