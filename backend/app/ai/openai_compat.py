import asyncio
import base64
import json
import logging
import re

import httpx

from app.ai.base import ModelCallError, ModelOutputError, ModelResult
from app.config import get_settings

log = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)

# Retried inside one call: the request never reached the provider (nothing billed),
# or the provider said "busy, try again". A read timeout is NOT retried: the model
# may already have run and charged for it.
_RETRY_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
_RETRY_STATUSES = {429, 502, 503, 504}


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
        connect_timeout: float | None = None,
        attempts: int | None = None,
        retry_backoff: float = 1.0,
    ) -> None:
        settings = get_settings()
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._transport = transport
        self.timeout = httpx.Timeout(
            timeout if timeout is not None else settings.MODEL_TIMEOUT_S,
            connect=connect_timeout if connect_timeout is not None else settings.MODEL_CONNECT_TIMEOUT_S,
        )
        self.attempts = max(1, attempts if attempts is not None else settings.MODEL_CALL_ATTEMPTS)
        self._backoff = retry_backoff

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
        resp = await self._post(payload)
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

    async def _post(self, payload: dict) -> httpx.Response:
        """POST with up to `attempts` tries for connect failures and busy statuses."""
        for attempt in range(1, self.attempts + 1):
            last = attempt == self.attempts
            try:
                async with httpx.AsyncClient(transport=self._transport, timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        json=payload,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                    )
            except _RETRY_ERRORS as e:
                if last:
                    raise ModelCallError(f"{self.provider} request failed: {e!r}") from e
                log.warning("%s connect failed (attempt %s/%s): %r", self.provider, attempt, self.attempts, e)
            except httpx.HTTPError as e:
                raise ModelCallError(f"{self.provider} request failed: {e!r}") from e
            else:
                if resp.status_code < 400:
                    return resp
                if last or resp.status_code not in _RETRY_STATUSES:
                    raise ModelCallError(f"{self.provider} returned HTTP {resp.status_code}: {resp.text[:200]}")
                log.warning("%s returned HTTP %s (attempt %s/%s)", self.provider, resp.status_code,
                            attempt, self.attempts)
            await asyncio.sleep(self._backoff * attempt)
        raise AssertionError("unreachable")