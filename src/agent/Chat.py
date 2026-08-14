"""
Builds and compiles the agent graph.

Checkpointer/store use in-memory backends for now, deliberately — matching the same
"defer infra, ship the feature" approach already applied to the Ollama-later decision.
Swap to langgraph.checkpoint.postgres.PostgresSaver / langgraph.store.postgres.PostgresStore
(pointed at the same POSTGRES_URI used everywhere else) when state needs to survive a restart.
"""
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore  
from langgraph.runtime import Runtime  

from .state import AgentState
from .chat_model import ChatCohereCustom
from .tools import (
    make_search_catalog_tool,
    make_filter_products_tool,
    make_read_memory_tool,
    make_write_memory_tool,
)


def build_graph(llm_provider, retrieval_controller, product_model, memory_controller):
    tools = [
        make_search_catalog_tool(retrieval_controller),
        make_filter_products_tool(product_model),
        make_read_memory_tool(memory_controller),
        make_write_memory_tool(memory_controller),
    ]

    chat_model = ChatCohereCustom(llm_provider=llm_provider).bind_tools(tools)
    tool_node = ToolNode(tools)

    def agent_node(state: AgentState):
        response = chat_model.invoke(state["messages"])
        return {"messages": [response]}

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    builder = StateGraph(AgentState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.set_entry_point("agent")
    builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")

    checkpointer = PostgresSaver()
    store = PostgresStore()

    return builder.compile(checkpointer=checkpointer, store=store)