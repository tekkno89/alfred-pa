from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    llm_node,
    process_message_node,
    retrieve_context_node,
    route_after_llm,
    route_after_process,
    save_assistant_message_node,
    save_user_message_node,
    tool_node,
)
from app.agents.state import AgentState


def create_agent_graph() -> StateGraph:
    """
    Build and compile the Alfred agent StateGraph.

    Graph structure:
        START → process_message → (error?)
          yes → END
          no  → retrieve_context → save_user_message → llm_node → (has_tool_calls?)
                    yes → tool_node → llm_node (cycle)
                    no  → save_assistant_message → END
    """
    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("process_message", process_message_node)
    builder.add_node("retrieve_context", retrieve_context_node)
    builder.add_node("save_user_message", save_user_message_node)
    builder.add_node("llm_node", llm_node)
    builder.add_node("tool_node", tool_node)
    builder.add_node("save_assistant_message", save_assistant_message_node)

    # Entry point
    builder.add_edge(START, "process_message")

    # After process_message: route to normal path or end (error)
    builder.add_conditional_edges(
        "process_message",
        route_after_process,
        {
            "retrieve_context": "retrieve_context",
            "end": END,
        },
    )

    # Normal path
    builder.add_edge("retrieve_context", "save_user_message")
    builder.add_edge("save_user_message", "llm_node")

    # After LLM: route to tool execution or finish
    builder.add_conditional_edges(
        "llm_node",
        route_after_llm,
        {
            "tool_node": "tool_node",
            "save_assistant_message": "save_assistant_message",
        },
    )

    # Tool loop: tool_node → llm_node (cycle)
    builder.add_edge("tool_node", "llm_node")

    # Finish path
    builder.add_edge("save_assistant_message", END)

    return builder.compile()
