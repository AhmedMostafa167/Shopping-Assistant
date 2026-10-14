"""Run-time checks on what the agent stores. Pure functions: no database, no API calls."""
import re

# read_memory returns at most this many facts; one beyond it would be stored but never read.
MAX_FACTS_PER_USER = 50
MAX_FACT_CHARACTERS = 200

# A stored fact is replayed into every later conversation, so a fact that reads like an
# instruction to the assistant would act as one. These patterns catch the plain forms
# only; a paraphrased instruction gets through.
INSTRUCTION_PATTERNS = {
    "it addresses the assistant": re.compile(
        r"\b(assistant|ai|bot|agent|you)\s+(must|should|shall|will|needs? to|has to|have to"
        r"|is to|are to|always|never)\b",
        re.IGNORECASE,
    ),
    "it tells the assistant to ignore its instructions": re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b.{0,40}\b(instructions?|rules?|prompts?"
        r"|guidelines?)\b",
        re.IGNORECASE,
    ),
    "it mentions the system prompt": re.compile(r"\bsystem prompt\b", re.IGNORECASE),
    # A link replayed in every conversation is a way to get the assistant to show it.
    "it contains a link": re.compile(r"https?://|\bwww\.", re.IGNORECASE),
}


def instruction_in_fact(fact: str) -> str | None:
    """Why the fact reads like an instruction to the assistant, or None if it does not."""
    for reason, pattern in INSTRUCTION_PATTERNS.items():
        if pattern.search(fact):
            return reason
    return None
