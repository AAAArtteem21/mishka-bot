import asyncio
import json
import logging

import httpx

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class LLMError(Exception):
    """LLM недоступна або повернула відповідь, яку не вдалося розібрати."""


class GroqClient:
    def __init__(
            self,
            api_key: str,
            model: str,
            *,
            transport: httpx.AsyncBaseTransport | None = None,
            retry_delay: float = 2.0,
    ) -> None:
        self._model = model
        self._retry_delay = retry_delay
        self._client = httpx.AsyncClient(
            base_url=GROQ_BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete_json(self, system: str, user:str) -> dict:
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            for attempt in range(3):
                response = await self._client.post("/chat/completions", json=payload)
                if response.status_code == 429 and attempt < 2:
                    logger.warning("Groq 429, повтор через %s с", self._retry_delay * (attempt + 1))
                    await asyncio.sleep(self._retry_delay * (attempt + 1))
                    continue
                if response.is_error:
                    logger.error(
                        "Groq API error: status=%s body=%s",
                        response.status_code,
                        response.text[:1000],
                    )
                response.raise_for_status()
                break
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError(f"Помилка запиту до Groq: {exc!r}") from exc
        if not isinstance(data, dict):
            raise LLMError("Groq повернув не JSON-об'єкт")
        return data 
