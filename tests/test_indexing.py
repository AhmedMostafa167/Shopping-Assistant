import asyncio
from types import SimpleNamespace

import pytest

from controllers.EmbeddingsController import EmbeddingsController


class FakeCatalogue:
    """Products and the vector table, standing in for ProductModel and pgvector."""

    def __init__(self, product_count, already_embedded=()):
        self.products = [
            SimpleNamespace(product_id=i, title=f"title {i}", description=f"desc {i}")
            for i in range(1, product_count + 1)
        ]
        self.embedded = dict.fromkeys(already_embedded, "old text")
        self.default_vector_size = 3
        self.fail_inserts_after = None
        self.insert_calls = 0
        self.index_requests = []

    # ProductModel side
    async def get_products_without_embedding(self, category_name, vector_table_name, limit):
        missing = [p for p in self.products if p.product_id not in self.embedded]
        return missing[:limit]

    async def count_products_without_embedding(self, category_name, vector_table_name):
        return len([p for p in self.products if p.product_id not in self.embedded])

    # vector store side
    async def create_table(self, table_name, embedding_size):
        self.table_name = table_name

    async def create_vector_index(self, table_name):
        self.index_requests.append(table_name)

    async def insert_many(self, table_name, texts, vectors, record_ids, batch_size):
        self.insert_calls += 1
        if self.fail_inserts_after is not None and self.insert_calls > self.fail_inserts_after:
            raise ConnectionError("database went away")
        self.embedded.update(zip(record_ids, texts))
        return True


class FakeEmbeddingClient:
    def __init__(self):
        self.batches = []

    async def aembed_texts(self, texts, document_type):
        self.batches.append(list(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]


def run_indexing(catalogue, embedding_client, **options):
    controller = EmbeddingsController(catalogue, embedding_client)
    return asyncio.run(
        controller.index_missing_products("phones", catalogue, **options)
    )


def test_only_products_without_an_embedding_are_embedded():
    catalogue = FakeCatalogue(product_count=10, already_embedded=[1, 2, 3])
    embedding_client = FakeEmbeddingClient()

    result = run_indexing(catalogue, embedding_client, batch_size=4)

    assert result == {"embedded": 7, "remaining": 0}
    assert [len(batch) for batch in embedding_client.batches] == [4, 3]
    assert embedding_client.batches[0][0] == "title 4\ndesc 4"
    assert catalogue.embedded[1] == "old text"  # existing embeddings are not redone


def test_a_second_run_has_nothing_left_to_pay_for():
    catalogue = FakeCatalogue(product_count=5)
    run_indexing(catalogue, FakeEmbeddingClient(), batch_size=2)
    second_client = FakeEmbeddingClient()

    result = run_indexing(catalogue, second_client, batch_size=2)

    assert result == {"embedded": 0, "remaining": 0}
    assert second_client.batches == []


def test_max_products_caps_the_run_and_reports_what_remains():
    catalogue = FakeCatalogue(product_count=10)
    embedding_client = FakeEmbeddingClient()

    result = run_indexing(catalogue, embedding_client, max_products=5, batch_size=4)

    assert result == {"embedded": 5, "remaining": 5}
    assert [len(batch) for batch in embedding_client.batches] == [4, 1]


def test_max_products_zero_only_reports_the_remaining_count():
    catalogue = FakeCatalogue(product_count=10, already_embedded=[1])
    embedding_client = FakeEmbeddingClient()

    result = run_indexing(catalogue, embedding_client, max_products=0)

    assert result == {"embedded": 0, "remaining": 9}
    assert embedding_client.batches == []


def test_a_failure_keeps_earlier_batches_and_the_next_run_resumes():
    catalogue = FakeCatalogue(product_count=10)
    catalogue.fail_inserts_after = 2

    with pytest.raises(ConnectionError):
        run_indexing(catalogue, FakeEmbeddingClient(), batch_size=3)

    assert sorted(catalogue.embedded) == [1, 2, 3, 4, 5, 6]  # two batches were saved

    catalogue.fail_inserts_after = None
    resumed_client = FakeEmbeddingClient()
    result = run_indexing(catalogue, resumed_client, batch_size=3)

    assert result == {"embedded": 4, "remaining": 0}
    assert resumed_client.batches[0][0] == "title 7\ndesc 7"


def test_missing_vectors_stop_the_run_instead_of_storing_nothing():
    class BrokenEmbeddingClient:
        async def aembed_texts(self, texts, document_type):
            return None

    catalogue = FakeCatalogue(product_count=3)

    with pytest.raises(RuntimeError):
        run_indexing(catalogue, BrokenEmbeddingClient())

    assert catalogue.embedded == {}


def test_the_search_index_is_requested_after_indexing_but_not_after_a_failure():
    catalogue = FakeCatalogue(product_count=4)
    run_indexing(catalogue, FakeEmbeddingClient(), batch_size=2)
    assert catalogue.index_requests == ["table_3_phones"]

    failing = FakeCatalogue(product_count=4)
    failing.fail_inserts_after = 0
    with pytest.raises(ConnectionError):
        run_indexing(failing, FakeEmbeddingClient(), batch_size=2)
    assert failing.index_requests == []


def test_the_vector_store_is_built_with_a_cosine_index_and_a_numeric_threshold():
    from stores.vectordb.VectorDBProviderFactory import VectorDBProviderFactory

    settings = SimpleNamespace(EMBEDDING_MODEL_SIZE=1024, VECTOR_DB_BACKEND="pgvector")
    provider = VectorDBProviderFactory(config=settings, db_client=None).create("pgvector")

    assert provider.distance_method == "vector_cosine_ops"
    assert isinstance(provider.index_threshold, int)
