import asyncio
import os
import sys
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

from cohere.errors import TooManyRequestsError

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

os.environ.update(
    {
        "APP_NAME": "test",
        "APP_VERSION": "0.0.0",
        "FILE_ALLOWED_TYPES": "[]",
        "FILE_ALLOWED_SIZE": "1",
        "POSTGRES_USERNAME": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_DB": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "POSTGRES_MAIN_DATABASE": "postgres",
        "EMBEDDING_MODEL_SIZE": "1",
        "EMBEDDING_MODEL": "test",
        "VECTOR_DB_BACKEND": "test",
        "LLM_BACKEND": "test",
        "COHERE_API_KEY": "test",
        "GENERATION_MODEL": "test",
        "DEFAULT_INPUT_MAX_CHARACTERS": "1000",
        "DEFAULT_GENERATION_MAX_OUTPUT_TOKENS": "1000",
        "DEFAULT_GENERATION_TEMPERATURE": "0.1",
        "RERANKING_MODEL": "test",
    }
)

from controllers.RetrievalController import RetrievalController
from stores.llm.providers.LangChainCohereProvider import LangChainCohereProvider


class FakeReranker:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def rerank(self, products, query):
        self.calls.append((products, query))
        return self.result


class FakeCohereRerankModel:
    async def acompress_documents(self, documents, query):
        assert query == "wireless headphones"
        return [documents[1], documents[0]]


def test_retrieval_controller_uses_configured_reranker():
    products = [SimpleNamespace(product_id=1), SimpleNamespace(product_id=2)]
    reranked = [products[1], products[0]]
    reranker = FakeReranker(reranked)
    controller = RetrievalController(None, None, None, reranking_client=reranker)

    result = asyncio.run(controller.rerank_results(products, "wireless headphones"))

    assert result == reranked
    assert reranker.calls == [(products, "wireless headphones")]


def test_retrieval_controller_falls_back_to_existing_order():
    products = [SimpleNamespace(product_id=1), SimpleNamespace(product_id=2)]
    controller = RetrievalController(None, None, None)

    result = asyncio.run(controller.rerank_results(products, "headphones"))

    assert result == products


def test_product_text_contains_searchable_product_fields():
    product = SimpleNamespace(
        title="Noise cancelling headphones",
        description="Over-ear wireless headphones",
        store="Audio Store",
        category_name="electronics",
        price=99.0,
        average_rating=4.5,
    )

    text = LangChainCohereProvider._product_to_text(product)

    assert "title: Noise cancelling headphones" in text
    assert "description: Over-ear wireless headphones" in text
    assert "price: 99.0" in text


def test_cohere_rerank_preserves_original_product_objects():
    provider = LangChainCohereProvider(api_key="test")
    provider.rerank_model = FakeCohereRerankModel()
    products = [
        SimpleNamespace(title="Product one", description="First"),
        SimpleNamespace(title="Product two", description="Second"),
    ]

    result = asyncio.run(provider.rerank(products, "wireless headphones"))

    assert result == [products[1], products[0]]


class FakeEmbeddingModel:
    def __init__(self, failures=0):
        self.calls = []
        self.failures = failures

    def embed(self, texts, *, input_type):
        self.calls.append((list(texts), input_type))
        if self.failures:
            self.failures -= 1
            raise TooManyRequestsError("rate limited", headers={})
        return [[float(index)] for index, _ in enumerate(texts)]


def test_embedding_requests_are_batched_at_cohere_limit():
    provider = LangChainCohereProvider(api_key="test")
    provider.embedding_model = FakeEmbeddingModel()
    texts = [f"product {index}" for index in range(97)]

    with patch("stores.llm.providers.LangChainCohereProvider.time.sleep"):
        embeddings = provider.embed_texts(texts, document_type="search_document")

    assert len(embeddings) == 97
    assert [len(call[0]) for call in provider.embedding_model.calls] == [96, 1]
    assert all(call[1] == "search_document" for call in provider.embedding_model.calls)


def test_embedding_retries_rate_limit_using_default_cohere_window():
    provider = LangChainCohereProvider(api_key="test")
    provider.embedding_model = FakeEmbeddingModel(failures=1)

    with patch("stores.llm.providers.LangChainCohereProvider.time.sleep") as sleep:
        result = provider.embed_texts(["query"], document_type="search_query")

    assert len(result) == 1
    assert provider.embedding_model.calls == [
        (["query"], "search_query"),
        (["query"], "search_query"),
    ]
    sleep.assert_called_once_with(60.0)
