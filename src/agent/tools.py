from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from structlog import get_logger

from .schemas import (
    FilterProductsInput,
    ReadMemoryInput,
    SearchCatalogInput,
    WriteMemoryInput,
)

logger = get_logger(__name__)


def make_search_catalog_tool(retrieval_controller):
    @tool("search_catalog", args_schema=SearchCatalogInput)
    async def search_catalog(query: str, category_name: str, top_k: int = 5) -> str:
        """Search the product catalog semantically and by keyword."""
        query = query.strip()
        if not query:
            return "No valid product search query was provided."

        products = await retrieval_controller.hybrid_search(query, top_k, category_name)
        logger.info("catalog_search_completed", query=query, result_count=len(products))
        if not products:
            return "No matching products found."
        return "\n".join(
            f"- {p.title} (${p.price}, rating {p.average_rating}): {p.description}"
            for p in products
        )

    return search_catalog


def make_filter_products_tool(product_model):
    @tool("filter_products", args_schema=FilterProductsInput)
    async def filter_products(
        category_name: str,
        min_price: float = None,
        max_price: float = None,
        min_rating: float = None,
    ) -> str:
        """Filter products by explicit price and rating constraints."""
        products = await product_model.filter_products(
            category_name=category_name,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
        )
        logger.info(
            "catalog_filter_completed",
            category_name=category_name,
            result_count=len(products),
        )
        if not products:
            return "No products matched those filters."
        return "\n".join(
            f"- {p.title} (${p.price}, rating {p.average_rating})" for p in products
        )

    return filter_products


def make_read_memory_tool(memory_controller):
    @tool("read_memory", args_schema=ReadMemoryInput)
    async def read_memory(config: RunnableConfig) -> str:
        """Read all stored facts for the current user, including their fact IDs."""
        username = config["configurable"]["user_id"]
        facts = await memory_controller.read_facts(username)
        logger.info("memory_read_completed", username=username, fact_count=len(facts))
        if not facts:
            return "No stored facts about this user yet."
        return "\n".join(
            f"- [fact_id={fact.memory_id}] [{fact.fact_type}] "
            f"{fact.content} (confidence {fact.confidence})"
            for fact in facts
        )

    return read_memory


def make_write_memory_tool(memory_controller):
    @tool("write_memory", args_schema=WriteMemoryInput)
    async def write_memory(
        operation: str,
        fact: str,
        fact_type: str,
        confidence: float,
        fact_id: int | None = None,
        config: RunnableConfig = None,
    ) -> str:
        """Add a new fact or modify exactly one existing fact; no reasoning is performed here."""
        username = config["configurable"]["user_id"]
        fact = fact.strip()
        if not fact:
            return "The fact cannot be empty."
        if operation == "modify" and fact_id is None:
            return "A fact_id is required when operation is modify."
        if operation == "add" and fact_id is not None:
            return "fact_id must be omitted when operation is add."

        if operation == "add":
            stored = await memory_controller.add_fact(
                username=username,
                fact_type=fact_type,
                content=fact,
                confidence=confidence,
            )
            logger.info("fact_added", username=username, fact_id=stored.memory_id)
            return f"Added fact_id={stored.memory_id}: {stored.content}"

        updated = await memory_controller.modify_fact(
            username=username,
            fact_id=fact_id,
            fact_type=fact_type,
            content=fact,
            confidence=confidence,
        )
        if updated is None:
            return f"No fact_id={fact_id} was found for this user."
        logger.info("fact_modified", username=username, fact_id=updated.memory_id)
        return f"Modified fact_id={updated.memory_id}: {updated.content}"

    return write_memory
