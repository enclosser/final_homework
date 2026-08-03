import chromadb

from agent import llm
from config import settings

COLLECTION = settings.CHROMA_COLLECTION


def _collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
    return client.get_or_create_collection(
        name=COLLECTION,
        metadata={'hnsw:space': 'cosine'},
    )


def _knowledge_docs() -> list[tuple[str, str]]:
    """Все .md-документы сервисов: (путь относительно корня, текст)."""
    docs: list[tuple[str, str]] = []
    for path in sorted(settings.BASE_DIR.glob('services/*/documentation/*.md')):
        rel = str(path.relative_to(settings.BASE_DIR))
        docs.append((rel, path.read_text(encoding='utf-8')))
    return docs


def ensure_index(force: bool = False) -> int:
    """Заполнить векторную базу, если она пуста. Возвращает число документов."""
    col = _collection()
    if force or col.count() == 0:
        items = _knowledge_docs()
        if items:
            ids = [str(i) for i in range(len(items))]
            col.upsert(
                ids=ids,
                documents=[t for _, t in items],
                metadatas=[{'path': p} for p, _ in items],
                embeddings=llm.embed([t for _, t in items]),
            )
    return col.count()


def search(query: str, k: int = 3) -> str:
    """Найти релевантные документы и вернуть читаемый текст для модели."""
    col = _collection()
    if col.count() == 0:
        return 'База знаний пуста.'
    try:
        embedding = llm.embed([query])[0]
        res = col.query(
            query_embeddings=[embedding],
            n_results=k,
            include=['documents', 'metadatas', 'distances'],
        )
    except Exception as exc:  # noqa: BLE001 — возвращаем ошибку в модель
        return f'Ошибка поиска в базе знаний: {exc!r}'

    parts = []
    for doc, meta, dist in zip(res['documents'][0], res['metadatas'][0], res['distances'][0]):
        parts.append(f"--- Источник: {meta['path']} (distance={dist:.3f}) ---\n{doc}")
    return '\n\n'.join(parts)