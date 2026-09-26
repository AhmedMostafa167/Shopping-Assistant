import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

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
