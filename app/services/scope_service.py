import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You label pieces of text taken from documents of a forest community (the text is Ukrainian).
Each piece is either practical knowledge for people who live in or visit the forest, or it is something else.

"is_advice" is true for any practical knowledge useful to someone in the forest: a recommendation, warning, prohibition, rule of conduct, tip, or a practical observation stated as a fact (for example "У хвойному лісі гриби з'являються на 2–3 день після дощу" is advice). Proverb-like or figurative admonitions to the reader are advice too.
"is_advice" is false ONLY for text that clearly contains nothing of this kind: headings, contacts, boilerplate, and text that is not about the forest at all (résumés, skill lists, technical descriptions, lab instructions, code, tables). A phrase that merely sounds like a recommendation inside such text (for example "захист від IDOR" in a skills list) is NOT advice.
When in doubt between "advice" and "not advice" for text that is about the forest, choose is_advice true.
When is_advice is false, level and label are null.

For every piece with is_advice true, decide how specific it is, i.e. who or what it applies to:
- level 1: ONE concrete object or "glove" (e.g. "Внесок під дубом — 4 жолуді": applies to one oak).
- level 2: a PART of the forest, a type of forest or a place (e.g. "У хвойному лісі гриби з'являються на 2–3 день після дощу").
- level 3: the WHOLE forest, general advice for everyone, with no particular object or place (e.g. "Крикни тричі при мисливцях").
- level null: it is advice, but it points to something unspecified and you cannot tell what it applies to (e.g. "Там гриби краще брати зранку": where is "там"?). Do NOT guess, use null when unclear.
If a piece mixes several levels, give the most specific level present.

"label" is a short Ukrainian noun phrase naming the object or part of the forest the advice is about (e.g. "дуб", "хвойний ліс"). Use null for level 3 and when the level is null.

Answer ONLY with JSON: {"items": [{"id": 0, "is_advice": true, "level": 2, "label": "хвойний ліс"}, ...]} with one item per piece."""

class JsonLLM(Protocol):
    async def complete_json(self, system: str, user: str) -> dict: ...


@dataclass
class ScopeTag:
    level: int | None = None
    label: int | None = None
    needs_clarification: bool = False


def build_user_prompt(title: str, chunks: list[str]) -> str:
    parts = [f"Document title: {title}", ""]
    for index, text in enumerate(chunks):
        parts.append(f"[{index}]")
        parts.append(text)
        parts.append("")
    return "\n".join(parts)


def parse_scope_response(data: dict, count: int) -> list[ScopeTag]:
    items = data.get("items")
    by_id: dict[int, dict] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and type(item.get("id")) is int:
                by_id[item["id"]] = item

    tags = []
    for index in range(count):
        item = by_id.get(index)
        if item is None:
            logger.warning("LLM не повернула мітку для шматка %s", index)
        tags.append(_parse_item(item))
    return tags


def _parse_item(item: dict | None) -> ScopeTag:
    if item is None or item.get("is_advice") is False:
        return ScopeTag()

    level = item.get("level")
    if type(level) is not int or level not in (1,2,3):
        return ScopeTag(needs_clarification=True)

    label = item.get("label")
    label = label.strip()[:255] or None if isinstance(label, str) else None
    return ScopeTag(level=level, label=label)

async def tag_chunks(
    llm: JsonLLM, title: str, chunks: list[str], batch_size: int = 8
) -> list[ScopeTag]:
    """Розмічає шматки порціями. Якщо LLM недоступна, кидає LLMError."""
    tags: list[ScopeTag] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        data = await llm.complete_json(SYSTEM_PROMPT, build_user_prompt(title, batch))
        tags.extend(parse_scope_response(data, len(batch)))

    return tags
