from langfuse import get_client

from .BaseController import BaseController
from .EmbeddingsController import EmbeddingsController
from models.enums import DataBaseEnums
from models import ProductModel
from utils import rrf
from stores.llm.LLMEnums import DocumentTypeEnum


def scored_ids(results) -> list[dict]:
    """Compact trace output for search results: which products, with what score."""
    return [{"product_id": r.product_id, "score": float(r.score)} for r in results]


class RetrievalController(BaseController):
    def __init__(self, embedding_client, vectordb_client, db_client, reranking_client=None):
        super().__init__()

        self.embedding_client = embedding_client
        self.vectordb_client = vectordb_client
        self.db_client = db_client
        self.reranking_client = reranking_client
        self.product_model = None
         
    @classmethod
    async def create_instance(cls, embedding_client, vectordb_client, db_client, reranking_client=None):
        controller = cls(embedding_client, vectordb_client, db_client, reranking_client)
        controller.product_model = await ProductModel.create_instance(db_client=db_client)
        return controller

    async def keyword_search(self, query: str, top_k: int = 10,
                             category_name: str = DataBaseEnums.DEFAULT_CATEGORY_NAME.value,
                             limits: dict | None = None):
        with get_client().start_as_current_observation(
            as_type="retriever",
            name="keyword-search",
            input={"query": query, "top_k": top_k, "category_name": category_name, "limits": limits},
        ) as observation:
            products = await self.product_model.keyword_search(
                query, top_k, limits, category_name=category_name
            )
            products = sorted(products, key=lambda x: x.score, reverse=True)
            observation.update(output=scored_ids(products))

            return products

    async def vector_search(self, query: str, top_k: int = 10,
                             category_name: str = DataBaseEnums.DEFAULT_CATEGORY_NAME.value,
                             limits: dict | None = None):

        langfuse = get_client()
        with langfuse.start_as_current_observation(
            as_type="retriever",
            name="vector-search",
            input={"query": query, "top_k": top_k, "category_name": category_name, "limits": limits},
        ) as observation:
            with langfuse.start_as_current_observation(
                as_type="embedding",
                name="embed-query",
                input=query,
                model=getattr(self.embedding_client, "embedding_model_id", None),
            ) as embedding:
                query_embedding = await self.embedding_client.aembed_texts(
                    texts=[query], document_type=DocumentTypeEnum.QUERY.value, batch_size=1
                )
                # The vector itself is noise in a trace; its size is enough.
                embedding.update(output={"dimensions": len(query_embedding[0])})

            embeddings_controller = EmbeddingsController(self.vectordb_client, self.embedding_client)
            table_name = embeddings_controller.create_table_name(category_name)
            products = await self.vectordb_client.search_by_vector(
                table_name=table_name,
                vector=query_embedding[0],
                limit=top_k,
                category_name=category_name,
                limits=limits,
            )
            products = sorted(products, key=lambda x: x.score, reverse=True)
            observation.update(output=scored_ids(products))
            return products

    def reranking(self, vector_results, keyword_results, k=60):
        with get_client().start_as_current_observation(
            as_type="span",
            name="fuse-results",
            input={
                "vector_result_count": len(vector_results),
                "keyword_result_count": len(keyword_results),
                "k": k,
            },
        ) as observation:
            fused = rrf(vector_results, keyword_results, k=k)
            observation.update(
                output=[{"product_id": pid, "score": score} for pid, score in fused]
            )
            return fused

    async def rerank_results(self, products, query: str):
        """Rerank products with Cohere when configured, otherwise preserve order."""
        if not products or self.reranking_client is None:
            return products
        rerank = getattr(self.reranking_client, "rerank", None)
        if rerank is None:
            return products
        with get_client().start_as_current_observation(
            as_type="span",
            name="rerank-results",
            input={"query": query, "product_ids": [p.product_id for p in products]},
            metadata={"model": getattr(self.reranking_client, "reranking_model_id", None)},
        ) as observation:
            reranked = await rerank(products, query)
            products = products if reranked is None else reranked
            observation.update(output={"product_ids": [p.product_id for p in products]})
            return products

    async def get_products_by_ids(self, product_ids: list[int]):
        return await self.product_model.get_products_by_ids(product_ids)

    async def hybrid_search(self, query: str, top_k: int = 10,
                             category_name: str = DataBaseEnums.DEFAULT_CATEGORY_NAME.value,
                             rerank: bool = True, limits: dict | None = None):
        """Vector and keyword search fused, then reranked.

        limits (min_price, max_price, min_rating) are applied inside both searches, so only
        products within them are ranked. rerank=False returns the fused order as is;
        evaluation uses it to measure what the paid rerank step adds.
        """
        with get_client().start_as_current_observation(
            as_type="retriever",
            name="hybrid-search",
            input={"query": query, "top_k": top_k, "category_name": category_name, "rerank": rerank,
                   "limits": limits},
        ) as observation:
            vector_results = await self.vector_search(query, top_k, category_name, limits)
            keyword_results = await self.keyword_search(query, top_k, category_name, limits)

            fused = self.reranking(vector_results, keyword_results)
            fused_ids = [pid for pid, _ in fused][:top_k]

            if not fused_ids:
                observation.update(output=[])
                return []

            products = await self.get_products_by_ids(fused_ids)

            order = {pid: i for i, pid in enumerate(fused_ids)}
            products = sorted(products, key=lambda p: order.get(p.product_id, len(order)))
            if rerank:
                products = await self.rerank_results(products, query)
            observation.update(
                output=[{"product_id": p.product_id, "title": p.title} for p in products]
            )
            return products
