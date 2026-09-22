"""Build and compile the shopping assistant LangGraph."""

from langchain_core.messages import SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .Templates import AGENT_SYSTEM_PROMPT, FIRST_TURN_MEMORY_INSTRUCTION
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
    """Build the graph using an application-owned checkpointer."""
    tools = [
        make_search_catalog_tool(retrieval_controller),
        make_filter_products_tool(product_model),
        make_read_memory_tool(memory_controller),
        make_write_memory_tool(memory_controller),
    ]

    chat_model = llm_provider.chat_model.bind_tools(tools)
    tool_node = ToolNode(tools)

    async def agent_node(state: AgentState):
        system_messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT)]
        if len(state["messages"]) == 1:
            system_messages.append(
                SystemMessage(content=FIRST_TURN_MEMORY_INSTRUCTION)
            )
        response = await chat_model.ainvoke(
            [*system_messages, *state["messages"]]
        )
        return {"messages": [response]}

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    return builder.compile(checkpointer=checkpointer)
