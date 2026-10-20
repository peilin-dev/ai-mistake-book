import base64
import json
import re

import httpx

from app.ai.base import ModelCallError, ModelOutputError, ModelResult
from app.config import get_settings

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def _parse_object(content: str) -> dict:
    text = content.strip()
    m = _FENCE.match(text)
    if m:
        text = m.group(1)
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ModelOutputError(f"model content is not JSON: {e}") from e
    if not isinstance(data, dict):
        raise ModelOutputError("model JSON is not an object")
    return data


class OpenAICompatModel:
    """Vision model behind an OpenAI-compatible /chat/completions endpoint."""

    def __init__(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._transport = transport
        self._timeout = timeout if timeout is not None else get_settings().MODEL_TIMEOUT_S

    async def complete_json(self, prompt: str, images: list[bytes]) -> ModelResult:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = base64.b64encode(img).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
        }
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
        except httpx.HTTPError as e:
            raise ModelCallError(f"{self.provider} request failed: {e!r}") from e
        if resp.status_code >= 400:
            raise ModelCallError(f"{self.provider} returned HTTP {resp.status_code}: {resp.text[:200]}")
        try:
            body = resp.json()
            text = body["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise ModelOutputError(f"unexpected response shape: {e!r}") from e
        if not isinstance(text, str):
            raise ModelOutputError("message content is not a string")
        data = _parse_object(text)
        usage = body.get("usage") or {}
        return ModelResult(
            data=data,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            model=body.get("model") or self.model,
            provider=self.provider,
        )