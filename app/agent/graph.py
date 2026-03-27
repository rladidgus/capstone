from langgraph.graph import StateGraph, END

from app.agent.state import AgentState
from app.agent.planner import run_planner
from app.agent.evaluator import run_evaluator
from app.agent.reporter import run_reporter
from app.tools.code_interpreter import run_code_interpreter
from app.tools.api_connector import fetch_external_data
from app.tools.interpolation_engine import run_interpolation
from app.tools.rag_retriever import retrieve_relevant_knowledge
from app.tools.statistical_analyzer import run_statistical_analysis


def route_after_evaluator(state: AgentState) -> str:
    if state["is_sufficient"] or state["retry_count"] >= 3:
        return "reporter"
    return "code_interpreter"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("planner", run_planner)
    graph.add_node("tool_router", _tool_router)
    graph.add_node("code_interpreter", run_code_interpreter)
    graph.add_node("api_connector", fetch_external_data)
    graph.add_node("interpolation", run_interpolation)
    graph.add_node("rag_retriever", retrieve_relevant_knowledge)
    graph.add_node("statistical_analyzer", run_statistical_analysis)
    graph.add_node("evaluator", run_evaluator)
    graph.add_node("reporter", run_reporter)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "code_interpreter")
    graph.add_edge("code_interpreter", "api_connector")
    graph.add_edge("api_connector", "interpolation")
    graph.add_edge("interpolation", "rag_retriever")
    graph.add_edge("rag_retriever", "statistical_analyzer")
    graph.add_edge("statistical_analyzer", "evaluator")
    graph.add_conditional_edges("evaluator", route_after_evaluator)
    graph.add_edge("reporter", END)

    return graph.compile()


def _tool_router(state: AgentState) -> AgentState:
    """도구 호출 순서 및 필요 도구를 결정합니다."""
    return state


agent_graph = build_graph()
