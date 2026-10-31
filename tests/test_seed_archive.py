from sqlalchemy import func, select

from app.db.models import EMBEDDING_DIM, Chunk, Document
from app.scripts.seed_archive import seed_directory


class FakeEmbeddings:
    async def embed(self, texts):
        return [[0.1] * EMBEDDING_DIM for _ in texts]


class FakeLLM:
    async def complete_json(self, system, user):
        return {"items": [{"id": i, "is_advice": True, "level": 3, "label": None} for i in range(20)]}


def make_archive(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "Правила.txt").write_text("Крикни тричі при мисливцях.\nНе вір лисиці.", encoding="utf-8")
    (archive / "empty.txt").write_text("  \n", encoding="utf-8")
    (archive / "~$lock.docx").write_bytes(b"temp")
    (archive / "photo.png").write_bytes(b"png")
    return archive


async def test_archive_documents_have_no_uploader_and_are_not_duplicated(session_factory, tmp_path):
    archive = make_archive(tmp_path)
    args = (str(archive), session_factory, FakeEmbeddings(), FakeLLM(), str(tmp_path / "data"))

    first = await seed_directory(*args)
    second = await seed_directory(*args)

    assert first.added == ["Правила.txt"]
    assert [name for name, _ in first.failed] == ["empty.txt"]
    assert second.added == [] and second.skipped == ["Правила.txt"]

    async with session_factory() as session:
        documents = (await session.execute(select(Document))).unique().scalars().all()
        chunk_count = await session.scalar(select(func.count()).select_from(Chunk))
    assert [(d.title, d.source_type, d.uploaded_by) for d in documents] == [("Правила", "archive", None)]
    assert chunk_count == 2