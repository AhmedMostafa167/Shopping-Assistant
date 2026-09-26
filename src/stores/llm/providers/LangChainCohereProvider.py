"""LangChain-native Cohere integrations used by the application."""

import asyncio
import time
from threading import Lock

from cohere.errors import TooManyRequestsError
from langchain_cohere import ChatCohere, CohereEmbeddings, CohereRerank

from helpers.logging import get_logger
from ..LLMInterface import LLMInterface
from ..LLMEnums import CoHereEnums


class LangChainCohereProvider(LLMInterface):
    EMBED_MAX_INPUTS_PER_REQUEST = 96
    EMBED_INPUTS_PER_MINUTE = 2000
    EMBED_RATE_WINDOW_SECONDS = 60.0
    EMBED_MAX_RETRIES = 3

    def __init__(
        self,
        api_key: str,
        default_input_max_characters: int = 1000,
        default_generation_max_output_tokens: int = 1000,
        default_generation_temperature: float = 0.1,
    ):
        self.api_key = api_key
        self.default_input_max_characters = default_input_max_characters
        self.default_generation_max_output_tokens = default_generation_max_output_tokens
        self.default_generation_temperature = default_generation_temperature
        self.generation_model_id = None
        self.embedding_model_id = None
        self.embedding_size = None
        self.reranking_model_id = None
        self.chat_model = None
        self.embedding_model = None
        self.rerank_model = None
        self._embed_window_started_at = time.monotonic()
        self._embed_inputs_in_window = 0
        self._embed_rate_lock = Lock()
        self.logger = get_logger(__name__)

    def set_generation_model(self, model_id: str):
        self.generation_model_id = model_id
        self.chat_model = ChatCohere(
            model=model_id,
            cohere_api_key=self.api_key,
            temperature=self.default_generation_temperature,
            max_tokens=self.default_generation_max_output_tokens,
        )

    def set_embedding_model(self, model_id: str, embedding_size: int):
        self.embedding_model_id = model_id
        self.embedding_size = embedding_size
        self.embedding_model = CohereEmbeddings(
            model=model_id,
            cohere_api_key=self.api_key,
            embedding_types=["float"],
        )

    def set_reranking_model(self, model_id: str):
        self.reranking_model_id = model_id
        self.rerank_model = CohereRerank(
            model=model_id,
            cohere_api_key=self.api_key,
        )

    def process_text(self, text: str) -> str:
        return text[: self.default_input_max_characters].strip()

    @staticmethod
    def _content_to_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                else:
                    text = getattr(item, "text", None)
                if text:
                    parts.append(text)
            return "".join(parts)
        return str(content or "")

    async def agenerate_text(
        self,
        prompt: str,
        chat_history: list | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str | None:
        if self.chat_model is None:
            self.logger.error("llm_generation_model_not_configured")
            return None
        model = self.chat_model
        if max_output_tokens is not None or temperature is not None:
            model = model.bind(
                **({"max_tokens": max_output_tokens} if max_output_tokens is not None else {}),
                **({"temperature": temperature} if temperature is not None else {}),
            )
        response = await model.ainvoke([
            {"role": "user", "content": self.process_text(prompt)},
        ])
        return self._content_to_text(response.content)

    def generate_text(
        self,
        prompt: str,
        chat_history: list | None = None,
        max_output_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str | None:
        if self.chat_model is None:
            self.logger.error("llm_generation_model_not_configured")
            return None
        response = self.chat_model.invoke(
            [{"role": "user", "content": self.process_text(prompt)}]
        )
        return self._content_to_text(response.content)

    def embed_texts(
        self,
        texts: list[str],
        document_type: str | None = None,
        batch_size: int = 96,
        **kwargs,
    ) -> list[list[float]] | None:
        if self.embedding_model is None:
            self.logger.error("llm_embedding_model_not_configured")
            return None
        if not texts:
            return []

        input_type = (
            "search_query"
            if document_type == CoHereEnums.QUERY.value
            else "search_document"
        )
        request_batch_size = min(max(batch_size, 1), self.EMBED_MAX_INPUTS_PER_REQUEST)
        return [
            embedding
            for start in range(0, len(texts), request_batch_size)
            for embedding in self._embed_batch(
                texts[start:start + request_batch_size],
                input_type,
            )
        ]

    def _embed_batch(self, texts: list[str], input_type: str) -> list[list[float]]:
        """Embed one Cohere-sized batch with simple rate limiting and retries."""
        for attempt in range(self.EMBED_MAX_RETRIES + 1):
            self._wait_for_embed_capacity(len(texts))
            try:
                return self.embedding_model.embed(texts, input_type=input_type)
            except TooManyRequestsError as exc:
                if attempt >= self.EMBED_MAX_RETRIES:
                    raise
                wait_seconds = self._retry_wait_seconds(exc)
                self.logger.warning(
                    "cohere_embedding_rate_limited",
                    retry=attempt + 1,
                    wait_seconds=wait_seconds,
                    batch_size=len(texts),
                )
                time.sleep(wait_seconds)
        raise RuntimeError("Cohere embedding retry loop exited unexpectedly")

    def _wait_for_embed_capacity(self, input_count: int) -> None:
        """Keep requests within Cohere's 2,000-inputs-per-minute limit."""
        while True:
            with self._embed_rate_lock:
                now = time.monotonic()
                elapsed = now - self._embed_window_started_at
                if elapsed >= self.EMBED_RATE_WINDOW_SECONDS:
                    self._embed_window_started_at = now
                    self._embed_inputs_in_window = 0
                if self._embed_inputs_in_window + input_count <= self.EMBED_INPUTS_PER_MINUTE:
                    self._embed_inputs_in_window += input_count
                    return
                wait_seconds = self.EMBED_RATE_WINDOW_SECONDS - elapsed
            time.sleep(max(wait_seconds, 0.0))

    @staticmethod
    def _retry_wait_seconds(exc: TooManyRequestsError) -> float:
        headers = getattr(exc, "headers", {}) or {}
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        try:
            return max(float(retry_after), 0.0)
        except (TypeError, ValueError):
            return LangChainCohereProvider.EMBED_RATE_WINDOW_SECONDS

    async def aembed_texts(
        self,
        texts: list[str],
        document_type: str | None = None,
        **kwargs,
    ) -> list[list[float]] | None:
        return await asyncio.to_thread(
            self.embed_texts,
            texts,
            document_type,
            kwargs.get("batch_size", self.EMBED_MAX_INPUTS_PER_REQUEST),
        )

    async def rerank(self, retrieved_products: list, query: str):
        if self.rerank_model is None:
            self.logger.error("llm_reranking_model_not_configured")
            return None
        from langchain_core.documents import Document

        documents = [
            Document(
                page_content=self._product_to_text(product),
                metadata={"product_index": index},
            )
            for index, product in enumerate(retrieved_products)
        ]
        reranked_documents = await self.rerank_model.acompress_documents(documents, query)
        reranked_indexes = [
            document.metadata["product_index"]
            for document in reranked_documents
            if "product_index" in document.metadata
        ]
        return [retrieved_products[index] for index in reranked_indexes]

    @staticmethod
    def _product_to_text(product) -> str:
        """Build the searchable document sent to Cohere from a product model."""
        fields = (
            "title",
            "description",
            "store",
            "category_name",
            "price",
            "average_rating",
        )
        return "\n".join(
            f"{field}: {getattr(product, field, '')}"
            for field in fields
            if getattr(product, field, None) not in (None, "")
        )
