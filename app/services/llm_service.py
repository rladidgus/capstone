"""
Ollama LLM 클라이언트 — Qwen 2.5 (7B)
"""
import json
from typing import Any

import httpx
import os


class LLMService:
    def __init__(self):
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    async def generate_text(self, prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
            )
            resp.raise_for_status()
            return resp.json()["response"]

    async def generate_json(self, prompt: str, max_tokens: int = 2048) -> dict[str, Any]:
        """JSON 출력을 보장하는 생성 메서드"""
        system = "항상 유효한 JSON 형식으로만 응답하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요."
        full_prompt = f"{system}\n\n{prompt}"
        text = await self.generate_text(full_prompt, temperature=0.1, max_tokens=max_tokens)
        try:
            # JSON 추출 (앞뒤 불필요한 텍스트 제거)
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError):
            return {"error": "JSON 파싱 실패", "raw": text}

    async def embed(self, text: str) -> list[float]:
        """텍스트 임베딩 벡터 생성"""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
