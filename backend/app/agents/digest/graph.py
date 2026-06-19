"""LangGraph StateGraph construction for the digest agent."""

from langgraph.graph import END, StateGraph

from app.agents.digest.nodes import (
    llm_node,
    route_after_llm,
    route_after_tool,
    setup_node,
    tool_node,
)
from app.agents.digest.state import DigestAgentState


def create_digest_graph():
    """Build and compile the digest agent StateGraph.

    Graph structure:
        setup → llm_node → (has_tool_calls / digest_sent / error?)
          tool_calls → tool_node → (digest_sent + record_saved / error?)
            yes  → END
            no   → llm_node (cycle)
          digest_sent / error / no calls → END
    """
    builder = StateGraph(DigestAgentState)

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
