import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent.memory_controller import MemoryController
from controllers.RetrievalController import RetrievalController
from routes.schemas.Chat import ChatRequest
from utils.rrf import reciprocal_rank_fusion


class FakeEmbeddingClient:
    def embed_texts(self, *, texts, document_type, batch_size):
        assert texts == ["wireless noise cancelling headphones"]
        return [[0.1, 0.2, 0.3]]


class FakeVectorDB:
    default_vector_size = 3

    async def search_by_vector(self, *, table_name, vector, limit, category_name):
        assert table_name == "table_3_electronics"
        assert category_name == "electronics"
        return [SimpleNamespace(product_id=101, score=0.99)]


class FakeProductModel:
    async def keyword_search(self, query, top_k):
        assert query == "wireless noise cancelling headphones"
        assert top_k == 5
        return [SimpleNamespace(product_id=101, score=1.0)]

    async def get_products_by_ids(self, product_ids):
        return [SimpleNamespace(product_id=product_ids[0], title="QuietSound Headphones")]


def test_hybrid_retrieval_returns_expected_product_for_known_query():
    controller = RetrievalController(
        embedding_client=FakeEmbeddingClient(),
        vectordb_client=FakeVectorDB(),
        db_client=None,
    )
    controller.product_model = FakeProductModel()

    products = asyncio.run(
        controller.hybrid_search(
            "wireless noise cancelling headphones",
            top_k=5,
            category_name="electronics",
        )
    )

    assert [product.product_id for product in products] == [101]
    assert products[0].title == "QuietSound Headphones"


def test_rrf_fusion_keeps_results_unique_to_each_signal():
    vector_results = [
        SimpleNamespace(product_id=10),
        SimpleNamespace(product_id=20),
    ]
    keyword_results = [
        SimpleNamespace(product_id=30),
        SimpleNamespace(product_id=10),
    ]

    fused = reciprocal_rank_fusion(vector_results, keyword_results, k=60)
    fused_ids = [product_id for product_id, _score in fused]

    assert set(fused_ids) == {10, 20, 30}
    assert fused_ids[0] == 10
    assert fused_ids.index(20) > fused_ids.index(10)
    assert fused_ids.index(30) > fused_ids.index(10)


class FakeProfileModel:
    async def get_profile_or_create_one(self, username):
        return SimpleNamespace(profile_id=7, username=username)

    async def get_profile_by_username(self, username):
        return SimpleNamespace(profile_id=7, username=username)


class FakeMemoryModel:
    def __init__(self):
        self.memories = []
        self.next_id = 1

    async def create_memory(self, memory):
        memory.memory_id = self.next_id
        self.next_id += 1
        self.memories.append(memory)
        return memory

    async def update_memory(self, memory_id, content, confidence, *, profile_id, fact_type):
        matches = [
            memory
            for memory in self.memories
            if memory.memory_id == memory_id and memory.profile_id == profile_id
        ]
        if not matches:
            return None
        memory = matches[0]
        memory.content = content
        memory.confidence = confidence
        memory.fact_type = fact_type
        return memory


def test_memory_conflict_resolution_overwrites_existing_fact_without_duplicate():
    memory_model = FakeMemoryModel()
    controller = MemoryController(memory_model, FakeProfileModel())

    original = asyncio.run(
        controller.add_fact(
            "alice",
            fact_type="preference",
            content="prefers Android phones",
            confidence=0.8,
        )
    )
    updated = asyncio.run(
        controller.modify_fact(
            "alice",
            fact_id=original.memory_id,
            fact_type="preference",
            content="prefers iPhone phones",
            confidence=0.95,
        )
    )

    assert updated is original
    assert updated.content == "prefers iPhone phones"
    assert updated.confidence == 0.95
    assert len(memory_model.memories) == 1
    assert memory_model.memories[0].memory_id == original.memory_id


def test_chat_request_rejects_empty_message():
    with pytest.raises(ValidationError):
        ChatRequest(
            username="alice",
            conversation_id=uuid4(),
            message="",
        )
