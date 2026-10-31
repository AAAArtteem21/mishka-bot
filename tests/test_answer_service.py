from datetime import UTC, datetime

from app.services.answer_service import (
    NO_ANSWER_TEXT,
    Answer,
    build_answer,
    format_answer,
    parse_answer,
)
from app.services.search_service import SearchHit


def make_hit(chunk_id, level, text="текст", source="user", title="Поради.txt", uploader="Ведмідь"):
    return SearchHit(
        chunk_id=chunk_id,
        text=text,
        scope_level=level,
        scope_label=None,
        document_title=title,
        source_type=source,
        uploader_name=uploader if source == "user" else None,
        uploaded_at=datetime(2026, 10, 29, 10, 6, tzinfo=UTC),
        cosine=1.0,
        trigram=1.0,
    )


def item(source, advice="порада"):
    return {"source": source, "advice": advice}


def test_specific_advice_is_main_and_general_goes_to_supplement():
    hits = [make_hit(1, 2), make_hit(2, 3)]
    data = {"status": "answer", "main": [item(0), item(1)], "supplement": [], "conflict": False}
    answer = parse_answer(data, hits)
    assert [i.hit.chunk_id for i in answer.main] == [1]
    assert [i.hit.chunk_id for i in answer.supplement] == [2]


def test_general_advice_is_dropped_when_it_contradicts():
    hits = [make_hit(1, 2), make_hit(2, 3)]
    data = {"status": "answer", "main": [item(0), item(1)], "conflict": True}
    answer = parse_answer(data, hits)
    assert [i.hit.chunk_id for i in answer.main] == [1]
    assert answer.supplement == []
    assert answer.conflict is False


def test_same_level_conflict_keeps_both():
    hits = [make_hit(1, 2), make_hit(2, 2)]
    data = {"status": "answer", "main": [item(0), item(1)], "conflict": True}
    answer = parse_answer(data, hits)
    assert len(answer.main) == 2 and answer.conflict is True


def test_supplement_more_specific_than_main_is_dropped():
    hits = [make_hit(1, 3), make_hit(2, 1)]
    data = {"status": "answer", "main": [item(0)], "supplement": [item(1)]}
    assert parse_answer(data, hits).supplement == []


def test_invalid_sources_and_garbage_are_ignored():
    hits = [make_hit(1, 2)]
    data = {"status": "answer", "main": [item(5), item(True), {"source": 0}, item(0, "  ")], "supplement": "x"}
    assert parse_answer(data, hits).status == "none"


def test_none_status_and_unknown_status_give_no_answer():
    hits = [make_hit(1, 2)]
    assert parse_answer({"status": "none", "main": [item(0)]}, hits).status == "none"
    assert parse_answer({"status": "maybe", "main": [item(0)]}, hits).status == "none"


def test_answer_only_in_supplement_is_promoted():
    hits = [make_hit(1, 3)]
    answer = parse_answer({"status": "answer", "supplement": [item(0)]}, hits)
    assert [i.hit.chunk_id for i in answer.main] == [1]


def test_format_user_source_has_name_and_kyiv_time():
    hits = [make_hit(1, 2)]
    text = format_answer(parse_answer({"status": "answer", "main": [item(0, "Гриби на 2–3 день.")]}, hits))
    assert text == "Гриби на 2–3 день.\nДжерело: «Поради.txt» — Ведмідь, 29.10.2026 12:06"


def test_format_archive_source_has_no_uploader():
    hits = [make_hit(1, 3, source="archive", title="Правила")]
    text = format_answer(parse_answer({"status": "answer", "main": [item(0, "Кричи.")]}, hits))
    assert "Джерело: Лісовий архів, «Правила»" in text
    assert "Ведмідь" not in text


def test_format_conflict_and_missing():
    hits = [make_hit(1, 2, title="А.txt"), make_hit(2, 2, title="Б.txt", uploader="Заєць")]
    data = {"status": "partial", "main": [item(0, "Так."), item(1, "Ні.")], "conflict": True, "missing": "час доби"}
    text = format_answer(parse_answer(data, hits))
    assert text.startswith("Документи суперечать одне одному:")
    assert "1. Так." in text and "2. Ні." in text
    assert text.endswith("У документах не знайшла: час доби")


def test_format_no_answer():
    assert format_answer(Answer()) == NO_ANSWER_TEXT


class FakeLLM:
    def __init__(self, data):
        self.data, self.calls = data, []

    async def complete_json(self, system, user):
        self.calls.append(user)
        return self.data


async def test_build_answer_sends_pieces_with_scope_and_parses():
    llm = FakeLLM({"status": "answer", "main": [item(0, "Гриби.")]})
    hits = [make_hit(1, 2, text="У хвойному лісі гриби.")]
    answer = await build_answer(llm, "Коли гриби?", hits)
    assert answer.main[0].advice == "Гриби."
    assert "Question: Коли гриби?" in llm.calls[0]
    assert "[0] (scope: forest part)" in llm.calls[0]


async def test_build_answer_without_hits_does_not_call_llm():
    llm = FakeLLM({})
    assert (await build_answer(llm, "?", [])).status == "none"
    assert llm.calls == []