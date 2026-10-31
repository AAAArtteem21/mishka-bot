import logging
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

from app.services.scope_service import JsonLLM
from app.services.search_service import SearchHit

logger = logging.getLogger(__name__)

KYIV = ZoneInfo("Europe/Kyiv")

NO_ANSWER_TEXT = (
    "У документах я не знайшла відповіді на це запитання."
    "Вигадувати пораду не буду."
)

SYSTEM_PROMPT = """You answer questions of forest animals using ONLY the numbered pieces of advice below. Never use outside knowledge.
Each piece has a scope: "glove" (one concrete object), "forest part" (a type of forest or a place), "whole forest" (general) or "unknown".
Rules:
1. Find the pieces that really answer the question and ignore the rest. A specific piece applies only if the question is about that very object or part of the forest; advice about a different object is NOT applicable.
2. The most specific applicable advice is the MAIN one. General advice may go to "supplement" only if it does NOT contradict the main advice.
3. If two applicable pieces of the SAME specificity contradict each other, put both into "main" and set "conflict" to true. Do not pick a winner and do not prefer newer documents.
4. If the pieces answer only a part of the question, give that part and describe in "missing" what is not covered.
5. If nothing answers the question, return status "none".
6. Write every "advice" in Ukrainian, short and natural, strictly based on its piece. Do not add facts.
Answer ONLY with JSON:
{"status": "answer" | "partial" | "none", "main": [{"source": 0, "advice": "..."}], "supplement": [{"source": 1, "advice": "..."}], "conflict": false, "missing": null}"""

_SCOPE_NAMES = {1: "glove", 2: "forest part", 3: "whole forest"}

@dataclass
class AnswerItem:
    hit: SearchHit
    advice: str 


@dataclass
class Answer:
    status: str = "none"
    main: list[AnswerItem] = field(default_factory=list)
    supplement: list[AnswerItem] = field(default_factory=list)
    conflict: bool = False
    missing: str | None = None


def _level(hit: SearchHit) -> int:
    return hit.scope_level or 3


def build_user_prompt(question: str, hits: list[SearchHit]) -> str:
    parts = [f"Question: {question}", "", "Pieces:"]
    for index, hit in enumerate(hits):
        scope = _SCOPE_NAMES.get(hit.scope_level, "unknown")
        label = f', "{hit.scope_label}"' if hit.scope_label else ""
        parts.append(f"[{index}] (scope: {scope}{label}) {hit.text}")
    return "\n".join(parts)


def _parse_items(raw: object, hits: list[SearchHit]) -> list[AnswerItem]:
    items: list[AnswerItem] = []
    seen: set[int] = set()
    if not isinstance(raw, list):
        return items
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        source, advice = entry.get("source"), entry.get("advice")
        if type(source) is not int or not 0 <= source < len(hits) or source in seen:
            continue
        if not isinstance(advice, str) or not advice.strip():
            continue
        seen.add(source)
        items.append(AnswerItem(hits[source], advice.strip()))
    return items


def parse_answer(data: dict, hits: list[SearchHit]) -> Answer:
    """Розбирає відповідь LLM і примусово застосовує правила пріоритету в коді."""
    status = data.get("status")
    if status not in ("answer", "partial", "none"):
        return Answer()

    main = _parse_items(data.get("main"), hits)
    supplement = _parse_items(data.get("supplement"), hits)
    if not main and supplement:
        main, supplement = supplement, []
    if status == "none" or not main:
        return Answer()

    missing = data.get("missing")
    missing = missing.strip() if isinstance(missing, str) and missing.strip() else None 
    conflict = data.get("conflict") is True

    best = min(_level(item.hit) for item in main)
    demoted = [item for item in main if _level(item.hit) != best]
    main = [item for item in main if _level(item.hit) == best]
    if not conflict:
        supplement = demoted + supplement

    main_ids = {item.hit.chunk_id for item in main}
    supplement = [
        item
        for item in supplement
        if item.hit.chunk_id not in main_ids and _level(item.hit) >= best
    ]
    return Answer(
        status=status,
        main=main,
        supplement=supplement,
        conflict=conflict and len(main) >= 2,
        missing=missing,
    )

async def build_answer(llm: JsonLLM, question: str, hits: list[SearchHit]) -> Answer:
    if not hits:
        return Answer()
    data = await llm.complete_json(SYSTEM_PROMPT, build_user_prompt(question, hits))
    return parse_answer(data, hits)

def source_line(hit: SearchHit) -> str:
    if hit.source_type == "archive":
        return f"Лісовий архів, «{hit.document_title}»"
    when = hit.uploaded_at.astimezone(KYIV).strftime("%d.%m.%Y %H:%M")
    return f"«{hit.document_title}» — {hit.uploader_name}, {when}"

def _block(item: AnswerItem, number: int | None = None) -> str:
    prefix = f"{number}. " if number else ""
    return f"{prefix}{item.advice}\nДжерело: {source_line(item.hit)}"

def format_answer(answer: Answer) -> str:
    if answer.status == "none" or not answer.main:
        return NO_ANSWER_TEXT

    blocks: list[str] = []
    if answer.conflict:
        blocks.append("Документи суперечать одне одному:")
        blocks.extend(_block(item, n) for n, item in enumerate(answer.main, start=1))
    else:
        blocks.extend(_block(item) for item in answer.main)

    if answer.supplement:
        blocks.append("Додатково (загальніша порада):")
        blocks.extend(_block(item) for item in answer.supplement)
    if answer.missing:
        blocks.append(f"У документах не знайшла: {answer.missing}")
    return "\n\n".join(blocks)
