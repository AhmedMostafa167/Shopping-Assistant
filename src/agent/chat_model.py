"""
Wraps the existing CoHereProvider as a LangChain BaseChatModel, so LangGraph's
bind_tools()/ToolNode work without installing langchain-cohere (which would pin its own,
conflicting `cohere` SDK version).

IMPORTANT — verify before relying on this:
Cohere's ClientV2.chat() uses `messages=[{"role":..,"content":..}]` and returns
`response.message.content[0].text` per Cohere's current v2 docs. This differs from what
CoHereProvider.generate_text calls (`chat_history=`, `message=`, and `response.text`) — that
method may be using an outdated calling convention. Test generate_text directly against your
installed `cohere` version before trusting either it or this file.

Tool-call response shape (response.message.tool_calls[i].function.name/arguments) is written
against Cohere's documented tool-use format — confirm against one real tool-triggering response
before depending on this; it has not been executed against a live API key here.
"""
import json
import uuid
from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool


class ChatCohereCustom(BaseChatModel):
    llm_provider: Any
    bound_tools: list = []

    def bind_tools(self, tools: List[BaseTool], **kwargs):
        formatted = [convert_to_openai_tool(t) for t in tools]
        return self.bind(tools=formatted)

    def _convert_messages(self, messages: List[BaseMessage]) -> list[dict]:
        converted = []
        for m in messages:
            if isinstance(m, HumanMessage):
                converted.append({"role": "user", "content": m.content})
            elif isinstance(m, SystemMessage):
                converted.append({"role": "system", "content": m.content})
            elif isinstance(m, AIMessage):
                converted.append({"role": "assistant", "content": m.content or ""})
            elif isinstance(m, ToolMessage):
                converted.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content})
        return converted

    def _parse_response(self, response) -> AIMessage:
        tool_calls = []
        for tc in getattr(response.message, "tool_calls", None) or []:
            tool_calls.append({
                "id": tc.id or str(uuid.uuid4()),
                "name": tc.function.name,
                "args": json.loads(tc.function.arguments) if tc.function.arguments else {},
            })

        text = ""
        if response.message.content:
            text = response.message.content[0].text

        return AIMessage(content=text, tool_calls=tool_calls)

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        cohere_messages = self._convert_messages(messages)
        response = self.llm_provider.client.chat(
            model=self.llm_provider.generation_model_id,
            messages=cohere_messages,
            tools=kwargs.get("tools") or self.bound_tools or None,
            temperature=self.llm_provider.default_generation_temperature,
            max_tokens=self.llm_provider.default_generation_max_output_tokens,
        )
        ai_message = self._parse_response(response)
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    @property
    def _llm_type(self) -> str:
        return "cohere-custom"