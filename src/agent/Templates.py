EXTRACTION_PROMPT = """Extract candidate facts about the user's preferences, constraints, or history
from their message. Each fact has:
- fact_type: one of "preference", "constraint", "history"
- content: the fact itself, as a short standalone statement
- confidence: 0.0-1.0, reflecting how directly and explicitly the user stated it.
  A direct statement ("I hate X") should score high; a hedge or inference ("maybe I'd prefer X")
  should score lower.

If nothing is extractable, return an empty list.
Respond with ONLY a JSON object matching this shape, no other text:
{{"facts": [{{"fact_type": "...", "content": "...", "confidence": 0.0}}]}}

User message: {message}
"""

CONFLICT_PROMPT = """A user has these existing stored facts of type "{fact_type}":
{existing_facts}

A new candidate fact of the same type was just extracted: "{new_content}"

Does the new fact contradict, update, or refine any existing fact above? If so, respond with the
existing fact's id. If the new fact is unrelated to all of them (a genuinely separate fact), respond
with -1.
Respond with ONLY a JSON object: {{"conflicting_memory_id": <id or -1>}}
"""

AGENT_SYSTEM_PROMPT = """
You are a helpful shopping assistant.

Your responsibilities:
- Help users find suitable products from the available catalog.
- Use search_catalog for semantic product searches.
- Use filter_products when the user provides explicit constraints such as price or rating.
- Use read_memory when stored user preferences or constraints may improve the answer.
- Use write_memory when the user's message contains a useful preference, constraint, or personal shopping history.
- Do not invent products, prices, ratings, or catalog details.
- Use the category "electronics_cellphones" unless the user or application provides another valid category.
- When searching the catalog, always provide a meaningful non-empty search query.
- Answer clearly and briefly based on the tool results.
"""
