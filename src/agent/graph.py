"""Build and compile the shopping assistant LangGraph."""

from langchain_core.messages import SystemMessage
from langfuse import Langfuse, propagate_attributes
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from .prompts import (
    FIRST_TURN_MEMORY_PROMPT_NAME,
    PRODUCTION_LABEL,
    SYSTEM_PROMPT_NAME,
    load_prompt,
)
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
    prompt_registry: Langfuse | None = None,
    prompt_label: str = PRODUCTION_LABEL,
):
    """Build the graph using an application-owned checkpointer."""
    tools = [
        make_search_catalog_tool(retrieval_controller),
        make_filter_products_tool(product_model),
        make_read_memory_tool(memory_controller),
        make_write_memory_tool(memory_controller),
    ]

    # Stable, provider-independent name for the model call in traces.
    chat_model = llm_provider.chat_model.bind_tools(tools).with_config(
        run_name="generate-agent-response"
    )
    tool_node = ToolNode(tools)

    async def agent_node(state: AgentState):
        system_prompt = load_prompt(prompt_registry, SYSTEM_PROMPT_NAME, prompt_label)
        system_messages = [SystemMessage(content=system_prompt.text)]
        if len(state["messages"]) == 1:
            first_turn_prompt = load_prompt(
                prompt_registry, FIRST_TURN_MEMORY_PROMPT_NAME, prompt_label
            )
            system_messages.append(SystemMessage(content=first_turn_prompt.text))

        # Links the model call in the trace to the prompt version that produced it.
        with propagate_attributes(prompt=system_prompt.registered):
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

    return builder.compile(checkpointer=checkpointer, name="shopping-agent")
