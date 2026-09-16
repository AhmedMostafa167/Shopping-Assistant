"""LangChain-native Cohere integrations used by the application."""

import asyncio

from langchain_cohere import ChatCohere, CohereEmbeddings, CohereRerank

from helpers.logging import get_logger
from ..LLMInterface import LLMInterface
from ..LLMEnums import CoHereEnums


class LangChainCohereProvider(LLMInterface):
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
        if document_type == CoHereEnums.QUERY.value:
            return [self.embedding_model.embed_query(text) for text in texts]
        return self.embedding_model.embed_documents(texts)

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
        )

    async def rerank(self, retrieved_products: list, query: str):
        if self.rerank_model is None:
            self.logger.error("llm_reranking_model_not_configured")
            return None
        from langchain_core.documents import Document

        documents = [Document(page_content=str(product)) for product in retrieved_products]
        return await self.rerank_model.acompress_documents(documents, query)
