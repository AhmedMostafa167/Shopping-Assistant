"""LangChain chat-model adapter for the repository's Cohere provider."""

import json
import uuid
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool


class ChatCohereCustom(BaseChatModel):
    """Expose the repository's Cohere provider through LangChain's chat API."""

    llm_provider: Any

    def bind_tools(self, tools: List[BaseTool], **kwargs):
        formatted_tools = [convert_to_openai_tool(tool) for tool in tools]
        return self.bind(tools=formatted_tools, **kwargs)

    def _convert_messages(self, messages: List[BaseMessage]) -> list[dict]:
        converted: list[dict] = []

        for message in messages:
            if isinstance(message, HumanMessage):
                converted.append(
                    {
                        "role": "user",
                        "content": message.content,
                    }
                )

            elif isinstance(message, SystemMessage):
                converted.append(
                    {
                        "role": "system",
                        "content": message.content,
                    }
                )

            elif isinstance(message, AIMessage):
                item = {
                    "role": "assistant",
                    "content": message.content or "",
                }

                if message.tool_calls:
                    item.pop("content", None)
                    item["tool_plan"] = message.content or ""
                    item["tool_calls"] = [
                        {
                            "id": str(call["id"]),
                            "type": "function",
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(
                                    call.get("args", {})
                                ),
                            },
                        }
                        for call in message.tool_calls
                    ]

                converted.append(item)

            elif isinstance(message, ToolMessage):
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(message.tool_call_id),
                        "content": [
                            {
                                "type": "document",
                                "document": {
                                    "data": str(message.content),
                                },
                            }
                        ],
                    }
                )

        return converted


    @staticmethod
    def _parse_response(response) -> AIMessage:
        message = getattr(response, "message", None)
        if message is None:
            raise RuntimeError("Cohere returned a response without a message")

        tool_calls = []
        for tool_call in getattr(message, "tool_calls", None) or []:
            function = getattr(tool_call, "function", None)
            if function is None:
                continue
            arguments = getattr(function, "arguments", None)
            if isinstance(  arguments, str):
                arguments = json.loads(arguments) if arguments else {}
            tool_calls.append(
                {
                    "id": getattr(tool_call, "id", None) or str(uuid.uuid4()),
                    "name": getattr(function, "name", ""),
                    "args": arguments or {},
                }
            )

        content = getattr(message, "content", None) or []
        text = ""
        if isinstance(content, str):
            text = content
        elif content:
            first = content[0]
            text = getattr(first, "text", None) or (
                first.get("text", "") if isinstance(first, dict) else ""
            )

        tool_plan = getattr(message, "tool_plan", None) or ""

        return AIMessage(
            content=tool_plan or text,
            tool_calls=tool_calls,
        )

    def _request_kwargs(self, kwargs: dict) -> dict:
        return {
            "tools": kwargs.get("tools"),
            "temperature": self.llm_provider.default_generation_temperature,
            "max_tokens": self.llm_provider.default_generation_max_output_tokens,
        }

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> ChatResult:
        response = self.llm_provider.chat(
            messages=self._convert_messages(messages),
            **self._request_kwargs(kwargs),
        )
        return ChatResult(
            generations=[ChatGeneration(message=self._parse_response(response))]
        )

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> ChatResult:
        response = await self.llm_provider.achat(
            messages=self._convert_messages(messages),
            **self._request_kwargs(kwargs),
        )
        return ChatResult(
            generations=[ChatGeneration(message=self._parse_response(response))]
        )

    @property
    def _llm_type(self) -> str:
        return "cohere-custom"
