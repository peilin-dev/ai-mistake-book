from app.ai.base import ModelResult


class FakeModel:
    """Test double: replays `responses` in order; Exception entries are raised."""

    provider = "fake"

    def __init__(self, responses: list[dict | Exception]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def complete_json(self, prompt: str, images: list[bytes]) -> ModelResult:
        self.prompts.append(prompt)
        if len(self.prompts) > len(self._responses):
            raise AssertionError("FakeModel exhausted")
        item = self._responses[len(self.prompts) - 1]
        if isinstance(item, Exception):
            raise item
        return ModelResult(item, 0, 0, "fake", "fake")