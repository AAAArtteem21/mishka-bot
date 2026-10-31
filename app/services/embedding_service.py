import asyncio
from fastembed import TextEmbedding
from app.db.models import EMBEDDING_DIM

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

class EmbeddingService:
    def __init__(self, cache_dir: str) -> None:
        self._model = TextEmbedding(MODEL_NAME, cache_dir=cache_dir)
        dim = len(self._embed(["тест"])[0])
        if dim != EMBEDDING_DIM:
            raise RuntimeError(
                f"Модель дає {dim} вимірів, а в БД колонка на {EMBEDDING_DIM}"
            )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return await asyncio.to_thread(self._embed, texts)
