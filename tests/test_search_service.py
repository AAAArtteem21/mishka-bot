from app.db.models import EMBEDDING_DIM, SourceType
from app.repositories.documents import ChunkData, DocumentRepository
from app.repositories.users import UserRepository
from app.services.search_service import (
    SearchHit,
    fuse_rankings,
    prioritize,
    search,
)


def one_hot(index: int) -> list[float]:
    return [1.0 if i == index else 0.0 for i in range(EMBEDDING_DIM)]


def blend(*indexes: int) -> list[float]:
    return [1.0 if i in indexes else 0.0 for i in range(EMBEDDING_DIM)]


class FakeEmbeddings:
    def __init__(self, vector):
        self._vector = vector

    async def embed(self, texts):
        return [self._vector for _ in texts]


MUSHROOMS = "У хвойному лісі гриби з’являються на 2–3 день після дощу."
OAK = "Внесок під дубом — 4 жолуді."
HUNTERS = "Крикни тричі при мисливцях."


async def seed(session):
    user = await UserRepository(session).create(telegram_id=1, real_name="Ведмідь")
    repo = DocumentRepository(session)
    doc = await repo.create(
        title="Поради.txt",
        file_path="x",
        sha256="a" * 64,
        source_type=SourceType.USER,
        uploaded_by=user.id,
    )
    archive = await repo.create(
        title="Лісовий архів: Правила",
        file_path="y",
        sha256="b" * 64,
        source_type=SourceType.ARCHIVE,
    )
    await repo.add_chunks(
        doc.id,
        [
            ChunkData(MUSHROOMS, 2, "хвойний ліс", one_hot(0)),
            ChunkData(OAK, 1, "дуб", one_hot(1)),
        ],
    )
    await repo.add_chunks(archive.id, [ChunkData(HUNTERS, 3, None, one_hot(2))])
    await session.commit()


async def test_vector_search_returns_only_relevant_chunk(session):
    await seed(session)
    hits = await search(session, FakeEmbeddings(one_hot(0)), "Коли з’являються гриби?")
    assert [h.text for h in hits] == [MUSHROOMS]
    assert hits[0].uploader_name == "Ведмідь"
    assert hits[0].document_title == "Поради.txt"


async def test_archive_hit_has_no_uploader(session):
    await seed(session)
    hits = await search(session, FakeEmbeddings(one_hot(2)), "Що робити при мисливцях?")
    assert hits[0].source_type == "archive"
    assert hits[0].uploader_name is None


async def test_trigram_finds_chunk_when_vector_does_not(session):
    await seed(session)
    unrelated_vector = one_hot(200)
    hits = await search(
        session, FakeEmbeddings(unrelated_vector), "гриби у хвойному лісі після дощу"
    )
    assert MUSHROOMS in [h.text for h in hits]


async def test_nothing_relevant_returns_empty(session):
    await seed(session)
    hits = await search(session, FakeEmbeddings(one_hot(300)), "ксилофон")
    assert hits == []


async def test_more_specific_advice_comes_first(session):
    await seed(session)
    hits = await search(session, FakeEmbeddings(blend(0, 1, 2)), "порада")
    assert [h.scope_level for h in hits] == [1, 2, 3]


async def test_weak_neighbour_is_dropped_when_there_is_a_clear_best_match(session):
    await seed(session)
    vector = [0.0] * EMBEDDING_DIM
    vector[0], vector[1] = 0.9, 0.55  # гриби — явний збіг, дуб — випадковий сусід
    hits = await search(session, FakeEmbeddings(vector), "ксилофон")
    assert [h.text for h in hits] == [MUSHROOMS]


def make_hit(level, score):
    return SearchHit(
        chunk_id=0, text="", scope_level=level, scope_label=None,
        document_title="d", source_type="user", uploader_name=None,
        uploaded_at=None, cosine=1.0, trigram=1.0, score=score,
    )


def test_prioritize_orders_by_level_then_score_and_treats_none_as_general():
    hits = [make_hit(None, 0.9), make_hit(3, 0.5), make_hit(2, 0.1), make_hit(1, 0.2), make_hit(3, 0.8)]
    ordered = prioritize(hits)
    assert [(h.scope_level, h.score) for h in ordered] == [
        (1, 0.2), (2, 0.1), (None, 0.9), (3, 0.8), (3, 0.5),
    ]


def test_fuse_rankings_rewards_chunks_found_by_both_lists():
    scores = fuse_rankings([1, 2, 3], [3, 1])
    assert scores[1] > scores[2]
    assert scores[3] > scores[2]