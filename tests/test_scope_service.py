from app.services.scope_service import ScopeTag, parse_scope_response, tag_chunks


def test_valid_items_are_parsed():
    data = {
        "items": [
            {"id": 0, "is_advice": True, "level": 1, "label": "дуб"},
            {"id": 1, "is_advice": True, "level": 3, "label": None},
        ]
    }
    assert parse_scope_response(data, 2) == [ScopeTag(1, "дуб"), ScopeTag(3, None)]


def test_not_advice_needs_no_clarification():
    data = {"items": [{"id": 0, "is_advice": False, "level": None, "label": None}]}
    assert parse_scope_response(data, 1) == [ScopeTag()]


def test_unclear_advice_needs_clarification():
    data = {"items": [{"id": 0, "is_advice": True, "level": None, "label": None}]}
    assert parse_scope_response(data, 1) == [ScopeTag(needs_clarification=True)]


def test_garbage_level_is_treated_as_unclear():
    for bad in (0, 4, "2", True, 2.0):
        data = {"items": [{"id": 0, "is_advice": True, "level": bad, "label": "x"}]}
        assert parse_scope_response(data, 1) == [ScopeTag(needs_clarification=True)], bad


def test_missing_item_is_untagged_without_question():
    assert parse_scope_response({"items": []}, 2) == [ScopeTag(), ScopeTag()]
    assert parse_scope_response({}, 1) == [ScopeTag()]


def test_label_is_trimmed_and_limited():
    data = {"items": [{"id": 0, "is_advice": True, "level": 2, "label": "  " + "а" * 300}]}
    assert len(parse_scope_response(data, 1)[0].label) == 255


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def complete_json(self, system, user):
        self.calls.append(user)
        items = [{"id": i, "is_advice": True, "level": 3, "label": None} for i in range(8)]
        return {"items": items}


async def test_chunks_are_tagged_in_batches():
    llm = FakeLLM()
    tags = await tag_chunks(llm, "Doc", [f"порада {i}" for i in range(20)], batch_size=8)
    assert len(tags) == 20
    assert len(llm.calls) == 3
    assert "Document title: Doc" in llm.calls[0]
    assert "[7]" in llm.calls[0] and "[8]" not in llm.calls[0]