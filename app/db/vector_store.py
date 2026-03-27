import os
from pinecone import Pinecone, ServerlessSpec

_pc: Pinecone | None = None
_index = None


def get_pinecone_index():
    global _pc, _index
    if _index is None:
        api_key = os.getenv("PINECONE_API_KEY", "")
        index_name = os.getenv("PINECONE_INDEX_NAME", "viewpoint-memos")
        env = os.getenv("PINECONE_ENVIRONMENT", "us-east-1")
        
        _pc = Pinecone(api_key=api_key)
        existing = [i.name for i in _pc.list_indexes()]
        if index_name not in existing:
            _pc.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region=env),
            )
        _index = _pc.Index(index_name)
    return _index

