"""Завантажує документи Лісового архіву в базу.

Запуск: docker compose exec bot python -m app.scripts.seed_archive /archive
Безпечно запускати повторно: файли, що вже є в базі (за sha256), пропускаються.
"""
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import SourceType
from app.db.session import make_engine, make_session_factory
from app.repositories.documents import ChunkData, DocumentRepository
from app.services.chunking import split_into_chunks
from app.services.document_service import ALLOWED_EXTENSIONS, save_file, sha256_of
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import ExtractionError, extract_text
from app.services.llm_client import GroqClient, LLMError
from app.services.scope_service import tag_chunks


@dataclass
class SeedReport:
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def _archive_files(directory: str) -> list[Path]:
    return sorted(
        path
        for path in Path(directory).rglob("*")
        if path.is_file()
        and path.suffix.lower() in ALLOWED_EXTENSIONS
        and not path.name.startswith(("~$", "."))
    )


async def seed_directory(
    directory: str,
    session_factory: async_sessionmaker[AsyncSession],
    embeddings,
    llm,
    data_dir: str,
) -> SeedReport:
    report = SeedReport()
    for path in _archive_files(directory):
        data = path.read_bytes()
        sha256 = sha256_of(data)

        async with session_factory() as session:
            documents = DocumentRepository(session)
            if await documents.get_by_sha256(sha256):
                report.skipped.append(path.name)
                continue

            saved = save_file(data, sha256, path.name, data_dir)
            try:
                text = await asyncio.to_thread(extract_text, saved)
                chunks = split_into_chunks(text)
                vectors = await embeddings.embed(chunks)
                tags = await tag_chunks(llm, path.stem, chunks)
            except ExtractionError as exc:
                Path(saved).unlink(missing_ok=True)
                report.failed.append((path.name, exc.user_message))
                continue
            except LLMError:
                Path(saved).unlink(missing_ok=True)
                report.failed.append((path.name, "Groq недоступний, спробуй ще раз"))
                continue

            document = await documents.create(
                title=path.stem,
                file_path=saved,
                sha256=sha256,
                source_type=SourceType.ARCHIVE,
            )
            await documents.add_chunks(
                document.id,
                [
                    ChunkData(
                        text=c, scope_level=t.level, scope_label=t.label, embedding=v
                    )
                    for c, v, t in zip(chunks, vectors, tags, strict=True)
                ],
            )
            await session.commit()
            report.added.append(path.name)
    return report


async def main(directory: str) -> None:
    if not Path(directory).is_dir():
        sys.exit(f"Папку {directory} не знайдено")
    settings = get_settings()
    engine = make_engine(settings.database_url)
    embeddings = EmbeddingService(cache_dir=f"{settings.data_dir}/models")
    llm = GroqClient(settings.groq_api_key, settings.groq_model)
    try:
        report = await seed_directory(
            directory, make_session_factory(engine), embeddings, llm, settings.data_dir
        )
    finally:
        await llm.aclose()
        await engine.dispose()

    print(f"Додано: {len(report.added)}, пропущено (вже є): {len(report.skipped)}, помилок: {len(report.failed)}")
    for name, reason in report.failed:
        print(f"  ✗ {name}: {reason}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "/archive"))