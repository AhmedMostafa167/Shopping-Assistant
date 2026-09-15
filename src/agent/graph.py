"""Build and compile the shopping assistant LangGraph."""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from .chat_model import ChatCohereCustom
from .state import AgentState
from .tools import (
    make_filter_products_tool,
    make_read_memory_tool,
    make_search_catalog_tool,
    make_write_memory_tool,
)


def build_graph(
    llm_provider,
    retrieval_controller,
    product_model,
    memory_controller,
    *,
    checkpointer: BaseCheckpointSaver,
):
    """Build the graph using an application-owned checkpointer.

    The checkpointer is deliberately injected instead of constructed here. The
    FastAPI lifespan owns its async PostgreSQL connection for the lifetime of
    the application and passes it to this factory.
    """
    tools = [
        make_search_catalog_tool(retrieval_controller),
        make_filter_products_tool(product_model),
        make_read_memory_tool(memory_controller),
        make_write_memory_tool(memory_controller),
    ]

    chat_model = ChatCohereCustom(llm_provider=llm_provider).bind_tools(tools)
    tool_node = ToolNode(tools)

    async def agent_node(state: AgentState):
        response = await chat_model.ainvoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    
    builder.add_edge(START, "agent")
    builder.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=checkpointer)
