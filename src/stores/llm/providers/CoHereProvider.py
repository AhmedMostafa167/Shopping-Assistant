"""Cohere provider with synchronous compatibility and async application paths."""

import asyncio
import logging
import time

import cohere

from ..LLMEnums import CoHereEnums
from ..LLMInterface import LLMInterface


class CoHereProvider(LLMInterface):
    def __init__(
        self,
        api_key: str,
        default_input_max_characters: int = 1000,
        default_generation_max_output_tokens: int = 1000,
        default_generation_temperature: float = 0.1,
    ):
        self.api_key = api_key
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = (
            default_generation_max_output_tokens
        )
        self.default_generation_temperature = default_generation_temperature

        self.generation_model_id = None
        self.reranking_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None

        self.client = cohere.ClientV2(api_key=self.api_key)
        # async_client_cls = getattr(cohere, "AsyncClientV2", None)
        # self.async_client = (
        #     async_client_cls(api_key=self.api_key) if async_client_cls else None
        # )
        self.async_client = cohere.AsyncClient(api_key=self.api_key)
        self.logger = logging.getLogger(__name__)

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size

    def set_reranking_model(self, model_id: str):
        self.reranking_model_id = model_id

    def process_text(self, text: str) -> str:
        return text[: self.default_input_max_characters].strip()

    @staticmethod
    def _message_text(response) -> str | None:
        message = getattr(response, "message", None)
        content = getattr(message, "content", None) if message else None
        if isinstance(content, str):
            return content
        if content:
            first = content[0]
            if isinstance(first, dict):
                return first.get("text")
            return getattr(first, "text", None)
        return getattr(response, "text", None)

    def chat(self, *, messages: list[dict], tools=None, temperature=None, max_tokens=None):
        """Synchronous V2 chat method retained for non-async callers."""
        return self.client.chat(
            model=self.generation_model_id,
            messages=messages,
            tools=tools or None,
            temperature=(
                self.default_generation_temperature
                if temperature is None
                else temperature
            ),
            max_tokens=(
                self.default_generation_max_output_tokens
                if max_tokens is None
                else max_tokens
            ),
        )

    async def achat(
        self,
        *,
        messages: list[dict],
        tools=None,
        temperature=None,
        max_tokens=None,
    ):
        """Asynchronous V2 chat method used by LangGraph nodes."""
        request = {
            "model": self.generation_model_id,
            "messages": messages,
            "tools": tools or None,
            "temperature": (
                self.default_generation_temperature
                if temperature is None
                else temperature
            ),
            "max_tokens": (
                self.default_generation_max_output_tokens
                if max_tokens is None
                else max_tokens
            ),
        }
        if self.async_client is not None:
            return await self.async_client.chat(**request)
        return await asyncio.to_thread(self.client.chat, **request)

    def generate_text(
        self,
        prompt: str,
        chat_history: list | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ):
        if not self.generation_model_id:
            self.logger.error("Generation model for Cohere was not set")
            return None

        response = self.chat(
            messages=[
                {
                    "role": "user",
                    "content": self.process_text(prompt),
                }
            ],
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        text = self._message_text(response)
        if not text:
            self.logger.error("Error while generating text with Cohere")
        return text

    async def agenerate_text(
        self,
        prompt: str,
        chat_history: list | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str | None:
        response = await self.achat(
            messages=[
                {
                    "role": "user",
                    "content": self.process_text(prompt),
                }
            ],
            temperature=temperature,
            max_tokens=max_output_tokens,
        )
        text = self._message_text(response)
        if not text:
            self.logger.error("Error while generating text with Cohere")
        return text

    def embed_texts(
        self,
        texts: list,
        document_type: str | None = None,
        batch_size: int = 96,
        max_retries: int = 5,
    ):
        if not self.embedding_model_id:
            self.logger.error("Embedding model for Cohere was not set")
            return None

        input_type = CoHereEnums.DOCUMENT.value
        if document_type == CoHereEnums.QUERY.value:
            input_type = CoHereEnums.QUERY.value

        all_embeddings = []
        for batch_num, i in enumerate(range(0, len(texts), batch_size)):
            batch = texts[i : i + batch_size]
            response = None
            for attempt in range(max_retries + 1):
                try:
                    response = self.client.embed(
                        model=self.embedding_model_id,
                        texts=batch,
                        input_type=input_type,
                        output_dimension=self.embedding_size,
                        embedding_types=["float"],
                    )
                    break
                except cohere.errors.TooManyRequestsError:
                    if attempt == max_retries:
                        self.logger.error(
                            "Embedding batch %s failed after retries", batch_num
                        )
                        return None
                    time.sleep(60)

            embeddings = getattr(response, "embeddings", None)
            float_embeddings = getattr(embeddings, "float", None)
            if not float_embeddings:
                self.logger.error("Error while embedding text with Cohere")
                return None
            all_embeddings.extend(float_embeddings)
        return all_embeddings

    async def aembed_texts(
        self,
        texts: list,
        document_type: str | None = None,
        batch_size: int = 96,
        max_retries: int = 5,
    ):
        if not self.embedding_model_id:
            self.logger.error("Embedding model for Cohere was not set")
            return None

        input_type = CoHereEnums.DOCUMENT.value
        if document_type == CoHereEnums.QUERY.value:
            input_type = CoHereEnums.QUERY.value

        all_embeddings = []
        for batch_num, i in enumerate(range(0, len(texts), batch_size)):
            batch = texts[i : i + batch_size]
            request = {
                "model": self.embedding_model_id,
                "texts": batch,
                "input_type": input_type,
                "output_dimension": self.embedding_size,
                "embedding_types": ["float"],
            }
            for attempt in range(max_retries + 1):
                try:
                    if self.async_client is not None:
                        response = await self.async_client.embed(**request)
                    else:
                        response = await asyncio.to_thread(self.client.embed, **request)
                    break
                except cohere.errors.TooManyRequestsError:
                    if attempt == max_retries:
                        self.logger.error(
                            "Embedding batch %s failed after retries", batch_num
                        )
                        return None
                    await asyncio.sleep(60)

            embeddings = getattr(response, "embeddings", None)
            float_embeddings = getattr(embeddings, "float", None)
            if not float_embeddings:
                self.logger.error("Error while embedding text with Cohere")
                return None
            all_embeddings.extend(float_embeddings)
        return all_embeddings

    async def rerank(self, retrieved_products: list, query: str):
        if not self.reranking_model_id:
            self.logger.error("Reranking model for Cohere was not set")
            return None

        request = {
            "model": self.reranking_model_id,
            "documents": retrieved_products,
            "query": query,
        }
        if self.async_client is not None:
            response = await self.async_client.rerank(**request)
        else:
            response = await asyncio.to_thread(self.client.rerank, **request)

        results = getattr(response, "results", None)
        if not results:
            self.logger.error("Error while reranking with Cohere")
            return None
        return sorted(results, key=lambda item: item.relevance_score, reverse=True)
