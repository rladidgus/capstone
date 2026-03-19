from pinecone import Pinecone, ServerlessSpec

from app.config import settings

_pc: Pinecone | None = None
_index = None


def get_pinecone_index():
    global _pc, _index
    if _index is None:
        _pc = Pinecone(api_key=settings.pinecone_api_key)
        existing = [i.name for i in _pc.list_indexes()]
        if settings.pinecone_index_name not in existing:
            _pc.create_index(
                name=settings.pinecone_index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region=settings.pinecone_environment),
            )
        _index = _pc.Index(settings.pinecone_index_name)
    return _index
