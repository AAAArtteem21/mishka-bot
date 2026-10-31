from app.services.chunking import split_into_chunks


def test_short_text_is_one_chunk():
    assert split_into_chunks("Крикни тричі при мисливцях") == ["Крикни тричі при мисливцях"]


def test_each_line_is_its_own_chunk():
    text = "Крикни тричі при мисливцях.\nВнесок під дубом — 4 жолуді.\nНе біжи по стежці."
    assert split_into_chunks(text) == [
        "Крикни тричі при мисливцях.",
        "Внесок під дубом — 4 жолуді.",
        "Не біжи по стежці.",
    ]


def test_long_line_is_split_into_sentences():
    line = ("Перше речення про гриби " * 6).strip() + ". Друге речення. Третє речення."
    chunks = split_into_chunks(line, max_chars=100)
    assert chunks[-2:] == ["Друге речення.", "Третє речення."]
    assert all(len(c) <= 100 for c in chunks)


def test_very_long_sentence_is_hard_cut():
    chunks = split_into_chunks("а" * 700, max_chars=300)
    assert [len(c) for c in chunks] == [300, 300, 100]


def test_empty_lines_are_ignored():
    assert split_into_chunks("\n\n  \nПривіт\n\n") == ["Привіт"]