# final_homework

Финальный проект создания ИИ-агента (техподдержка).

## Кейс

ИИ-агент, помогающий сотрудникам решать технические проблемы: ищет ответы
в базе знаний (RAG), выполняет операции через сервисы LDAP/Exchange/1С
(function calling) или передаёт обращение специалисту.

## Структура

- `config/` — настройки проекта (django-environ, файл `.env`).
- `services/` — сервисы-эмуляторы внешних систем:
  - `ldap/` — LDAP-каталог (пользователи, пароли, блокировки);
  - `exchange/` — Microsoft Exchange (почта);
  - `onec/` — 1С:Предприятие (базы, сессии).

  Внутри каждого сервиса `documentation/` — документация по типовым проблемам
  (источник для будущего RAG).

## Запуск сервисов

Активировать виртуальное окружение:

```bash
source .venv/bin/activate
```

Каждый сервис в отдельном терминале:

```bash
uvicorn services.ldap.app:app --port 8101      # LDAP
uvicorn services.exchange.app:app --port 8102  # Exchange
uvicorn services.onec.app:app --port 8103      # 1С
```

Или все три сразу одной командой (остановка — `Ctrl+C`):

```bash
uvicorn services.ldap.app:app --port 8101 & \
uvicorn services.exchange.app:app --port 8102 & \
uvicorn services.onec.app:app --port 8103 & \
wait
```

Проверка, что сервис поднялся:

```bash
curl http://localhost:8101/users/ivanov@corp.local
```

Интерактивная схема API (OpenAPI) каждого сервиса — по адресу `/docs`.

## Настройки

Переменные окружения читаются из `.env` (см. `.env.example`).