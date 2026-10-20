from dataclasses import dataclass
from typing import Protocol


class ModelError(Exception):
    """Base class for adapter failures."""


class ModelOutputError(ModelError):
    """The model answered, but its content is not a JSON object."""


class ModelCallError(ModelError):
    """The call itself failed: HTTP status >= 400 or a transport error."""


@dataclass
class ModelResult:
    data: dict
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


class VisionModel(Protocol):
    provider: str

    async def complete_json(self, prompt: str, images: list[bytes]) -> ModelResult: ...