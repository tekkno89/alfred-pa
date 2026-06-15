"""LangGraph StateGraph construction for the triage agent."""

from langgraph.graph import END, StateGraph

from app.agents.triage.nodes import (
    llm_node,
    route_after_llm,
    route_after_tool,
    setup_node,
    tool_node,
)
from app.agents.triage.state import TriageAgentState


def create_triage_graph():
    """Build and compile the triage agent StateGraph.

    Graph structure:
        setup → llm_node → (has_tool_calls / action_taken / error?)
          tool_calls → tool_node → (action_taken / needs_review?)
            yes  → END
            no   → llm_node (cycle)
          action_taken / error / no calls → END
    """
    builder = StateGraph(TriageAgentState)

    # Register nodes
    builder.add_node("setup", setup_node)
    builder.add_node("llm_node", llm_node)
    builder.add_node("tool_node", tool_node)

    # Entry point
    builder.set_entry_point("setup")

    # setup → llm_node
    builder.add_edge("setup", "llm_node")

    # After LLM: route to tool execution or end
    builder.add_conditional_edges(
        "llm_node",
        route_after_llm,
        {
            "tool_node": "tool_node",
            "end": END,
        },
    )

    # After tool: route back to LLM or end
    builder.add_conditional_edges(
        "tool_node",
        route_after_tool,
        {
            "llm_node": "llm_node",
            "end": END,
        },
    )

    return builder.compile()
