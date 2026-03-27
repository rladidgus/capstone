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

    try:
        # Pinecone API 키가 없거나 연결 에러 시 RAG 단계를 안전하게 패스합니다.
        query_vector = await llm.embed(query)
        index = get_pinecone_index()

        filter_meta: dict = {"store_id": str(store_id)}
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
        tool_status = {"tool": "rag_retriever", "retrieved_count": len(contexts)}
    except Exception as e:
        print(f"⚠️ Pinecone RAG 연결 실패 (API키 확인 요망): {e}")
        rag_context = "관련 경영 메모 없음 (데이터베이스 연결 안 됨)"
        tool_status = {"tool": "rag_retriever", "status": "skipped", "error": str(e)}

    return {
        "rag_context": rag_context,
        "tool_calls": state.get("tool_calls", []) + [tool_status],
    }
