import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models import EMBEDDING_DIM, ScopeLevel, SourceType
from app.repositories.documents import ChunkData, DocumentRepository
from app.repositories.users import UserRepository

async def test_create_and_find_user(session):
    repo = UserRepository(session)
    await repo.create(telegram_id=111, real_name="Зайчик")

    found = await repo.get_by_telegram_id(111)

    assert found is not None
    assert found.real_name  == "Зайчик"
    assert await repo.get_by_telegram_id(999) is None 

async def test_user_document_with_chunks_keeps_uploader(session):
    user = await UserRepository(session).create(telegram_id=1, real_name="Ведмідь")
    repo = DocumentRepository(session)

    doc = await repo.create(
        title="Поради.pdf",
        file_path="data/a.pdf",
        sha256="a" * 64,
        source_type=SourceType.USER,
        uploaded_by=user.id,
    )
    chunks = await repo.add_chunks(
        doc.id,
        [
            ChunkData(
                text="Внесок під дубом — 4 жолуді",
                scope_level=ScopeLevel.GLOVE,
                scope_label="дуб",
                embedding=[0.1] * EMBEDDING_DIM,
            ),
            ChunkData(text="Крикни тричі при мисливцях"),
        ],
    )

    found = await repo.get_by_sha256("a" * 64)
    assert found is not None
    assert found.uploader.real_name == "Ведмідь"
    assert [c.position for c in chunks] == [0, 1]
    assert chunks[1].scope_level is None

async def test_archive_document_has_no_uploader(session):
    repo = DocumentRepository(session)
    await repo.create(
        title="Лісовий архів: Правила",
        file_path="data/archive/r.docx",
        sha256="b" * 64,
        source_type=SourceType.ARCHIVE,
    )

    found = await repo.get_by_sha256("b" * 64)

    assert found is not None
    assert found.uploader is None

async def test_user_document_requires_uploader(session):
    repo = DocumentRepository(session)
    with pytest.raises(IntegrityError):
        await repo.create(
            title="x",
            file_path="x",
            sha256="c" * 64,
            source_type=SourceType.USER,
        )

async def test_duplicate_sha256_is_rejected(session):
    repo = DocumentRepository(session)
    await repo.create(
        title="1", file_path="1", sha256="d" * 64, source_type=SourceType.ARCHIVE
    )
    with pytest.raises(IntegrityError):
        await repo.create(
            title="2", file_path="2", sha256="d" * 64, source_type=SourceType.ARCHIVE
        )
