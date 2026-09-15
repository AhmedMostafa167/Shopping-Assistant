from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from .schemas import SearchCatalogInput, FilterProductsInput, ReadMemoryInput, WriteMemoryInput


def make_search_catalog_tool(retrieval_controller):
    @tool("search_catalog", args_schema=SearchCatalogInput)
    async def search_catalog(query: str, category_name: str, top_k: int = 5) -> str:
        """Search the product catalog semantically and by keyword for products matching the query."""
        products = await retrieval_controller.hybrid_search(query, top_k, category_name)
        if not products:
            return "No matching products found."
        return "\n".join(
            f"- {p.title} (${p.price}, rating {p.average_rating}): {p.description}"
            for p in products
        )

    return search_catalog


def make_filter_products_tool(product_model):
    @tool("filter_products", args_schema=FilterProductsInput)
    async def filter_products(category_name: str, min_price: float = None,
                               max_price: float = None, min_rating: float = None) -> str:
        """Filter products by structured criteria (price range, rating) when the user gives fixed
        constraints rather than a semantic description — e.g. 'under $50', 'rated above 4 stars'."""
        products = await product_model.filter_products(
            category_name=category_name, min_price=min_price, max_price=max_price, min_rating=min_rating
        )
        if not products:
            return "No products matched those filters."
        return "\n".join(f"- {p.title} (${p.price}, rating {p.average_rating})" for p in products)

    return filter_products


def make_read_memory_tool(memory_controller):
    @tool("read_memory", args_schema=ReadMemoryInput)
    async def read_memory(query: str, config: RunnableConfig) -> str:
        """Recall stored facts (preferences, constraints, history) about the current user."""
        username = config["configurable"]["user_id"]
        facts = await memory_controller.read_facts(username)
        if not facts:
            return "No stored facts about this user yet."
        return "\n".join(f"- [{f.fact_type}] {f.content} (confidence {f.confidence})" for f in facts)

    return read_memory


def make_write_memory_tool(memory_controller):
    @tool("write_memory", args_schema=WriteMemoryInput)
    async def write_memory(message: str, config: RunnableConfig) -> str:
        """Extract and store any preferences, constraints, or history from the user's message."""
        username = config["configurable"]["user_id"]
        actions = await memory_controller.resolve_and_write(username, message)
        if not actions:
            return "Nothing worth storing found in that message."
        return "; ".join(actions)

    return write_memory