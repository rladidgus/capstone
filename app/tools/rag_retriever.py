"""
Pinecone 기반 경영 메모 + 외부 지식 검색 (RAG)
"""
from typing import Optional

from app.agent.state import AgentState
from app.db.vector_store import get_pinecone_index
from app.services.llm_service import LLMService

llm = LLMService()
TOP_K = 5


async def retrieve_relevant_knowledge(state: AgentState) -> AgentState:
    """질의와 유사도 높은 메모/지식 Top-K 검색"""
    query = state["user_query"]
    store_id = state.get("store_id", "")
    date_range = state.get("date_range") or {}

    query_vector = await llm.embed(query)
    index = get_pinecone_index()

    filter_meta: dict = {"store_id": store_id}
    if date_range.get("start"):
        filter_meta["date"] = {"$gte": date_range["start"]}

    results = index.query(
        vector=query_vector,
        top_k=TOP_K,
        include_metadata=True,
        filter=filter_meta,
    )

    contexts = [
        f"[{m['metadata'].get('date', '')}] {m['metadata'].get('content', '')}"
        for m in results.get("matches", [])
    ]
    rag_context = "\n".join(contexts) if contexts else "관련 경영 메모 없음"

    return {
        **state,
        "rag_context": rag_context,
        "tool_calls": [{"tool": "rag_retriever", "retrieved_count": len(contexts)}],
    }
