import re 

_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_into_chunks(text: str, max_chars: int = 300) -> list[str]:
    """Одна порада = один шматок.

    Кожен непорожній рядок стає окремим шматком. Рядок довший за max_chars
    ріжеться на речення (кожне речення — окремий шматок), а задовге речення
    різеться жорстко.
    """
    chunks: list[str] = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if not line:
            continue
        if len(line) <= max_chars:
            chunks.append(line)
            continue
        for sentence in _SENTENCE_END.split(line):
            for start in range(0, len(sentence), max_chars):
                chunks.append(sentence[start : start + max_chars])
    return chunks
