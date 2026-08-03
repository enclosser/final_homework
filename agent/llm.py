from typing import Any

from openai import OpenAI

from config import settings


def _client() -> OpenAI:
    """Создать HTTP-клиент к локальному API LM Studio.
    """
    return OpenAI(
        base_url=settings.LM_STUDIO_HOST,
        api_key=settings.LM_STUDIO_API_KEY,
        max_retries=0,
        timeout=180.0,
    )


def chat(
    messages: list[dict[str, Any]],
    route: str = 'heavy',
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict | None = 'auto',
) -> Any:
    """Вызвать chat-модель без стриминга и вернуть сырой ответ API.
    """
    model = settings.LM_STUDIO_MODEL_HEAVY if route == 'heavy' else settings.LM_STUDIO_MODEL_LIGHT
    kwargs: dict[str, Any] = {'model': model, 'messages': messages, 'temperature': 0.0}
    if tools:
        # Схемы инструментов передаём, только когда они нужны, без этого параметра модель просто отвечает текстом.
        kwargs['tools'] = tools
        kwargs['tool_choice'] = tool_choice
    return _client().chat.completions.create(**kwargs)


def complete(
    messages: list[dict[str, Any]],
    route: str = 'heavy',
    tools: list[dict[str, Any]] | None = None,
) -> tuple[Any, Any]:
    """Вызвать модель и вернуть удобную пару (сообщение-ответ, usage).
    """
    resp = chat(messages, route=route, tools=tools)
    return resp.choices[0].message, getattr(resp, 'usage', None)


def embed(texts: list[str]) -> list[list[float]]:
    """Получить векторные представления текстов для RAG.
    """
    resp = _client().embeddings.create(model=settings.EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in resp.data]