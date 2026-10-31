"""Показує, що знаходить пошук і з якими балами.

Запуск: docker compose exec bot python -m app.scripts.search_debug "питання"
Зірочка * - шматок пройшов пороги релевантності.
"""
import asyncio
import sys

from app.config import get_settings
from app.db.session import make_engine, make_session_factory
from app.services.embedding_service import EmbeddingService
from app.services.search_service import cosine_cutoff, find_candidates, is_relevant

async def main(question: str) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    embeddings = EmbeddingService(cache_dir=f"{settings.data_dir}/models")
    async with make_session_factory(engine)() as session:
        hits = await find_candidates(session, embeddings, question)
    cutoff = cosine_cutoff(hits)
    print(f"поріг cosine = {cutoff:.2f}")
    for hit in hits[:15]:
        mark = "*" if is_relevant(hit, cutoff) else " "
        print(
            f"{mark} L{hit.scope_level} cos={hit.cosine:.2f} trg={hit.trigram:.2f} "
            f"| {hit.document_title}: {hit.text[:70]}"
        )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:])))
