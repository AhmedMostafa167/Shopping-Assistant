import math

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from structlog import get_logger

from helpers.tracing import record_guardrail
from .guardrails import MAX_FACTS_PER_USER, instruction_in_fact
from .schemas import (
    FilterProductsInput,
    ReadMemoryInput,
    SearchCatalogInput,
    WriteMemoryInput,
)

logger = get_logger(__name__)


def format_recommendation_score(product) -> str:
    score = product.recommendation_score
    if score is None:
        return "no ratings yet"
    # Spelled out so the model does not present it as the product's star rating.
    return f"recommendation score {score}/5 (adjusted for number of reviews; not the average rating)"


def format_price(product) -> str:
    price = product.price
    if price is None or math.isnan(price):
        return "price not listed"
    return f"${price}"


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
            f"- {p.title} ({format_price(p)}, {format_recommendation_score(p)}) "
            f"[Image URL: {p.image}]: {p.description}"
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
            f"- {p.title} ({format_price(p)}, {format_recommendation_score(p)}) "
            f"[Image URL: {p.image}]"
            for p in products
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

        blocked_reason = instruction_in_fact(fact)
        if (blocked_reason is None and operation == "add"
                and await memory_controller.count_facts(username) >= MAX_FACTS_PER_USER):
            blocked_reason = f"the user already has {MAX_FACTS_PER_USER} stored facts"
        record_guardrail(
            "memory-write-guard",
            input={"operation": operation, "fact": fact},
            blocked_reason=blocked_reason,
        )
        if blocked_reason:
            logger.warning("fact_blocked", username=username, reason=blocked_reason)
            return (
                f"Not stored: {blocked_reason}. Only facts that describe the user are stored; "
                "to change a fact the user already has, modify it instead."
            )

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
