from typing import Literal

from app.ai.base import VisionModel
from app.ai.openai_compat import OpenAICompatModel
from app.config import Settings, get_settings

Purpose = Literal["grading", "answer_key", "practice_generate", "practice_verify"]

_PROVIDERS = {
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "doubao": ("https://ark.cn-beijing.volces.com/api/v3", "ARK_API_KEY"),
}


def _parse(value: str) -> tuple[str, str]:
    provider, sep, model = value.partition(":")
    if not sep or not model or provider not in _PROVIDERS:
        raise ValueError(f"invalid model setting {value!r}; expected 'qwen:<model>' or 'doubao:<model>'")
    return provider, model


def _setting(settings: Settings, purpose: str) -> str:
    try:
        return getattr(settings, f"MODEL_FOR_{purpose.upper()}")
    except AttributeError:
        raise ValueError(f"unknown purpose {purpose!r}") from None


def get_model(purpose: Purpose) -> VisionModel:
    settings = get_settings()
    provider, model = _parse(_setting(settings, purpose))
    if purpose == "practice_verify":
        gen_provider, _ = _parse(_setting(settings, "practice_generate"))
        if provider == gen_provider:
            raise ValueError("practice_verify must use a different provider than practice_generate")
    base_url, key_attr = _PROVIDERS[provider]
    return OpenAICompatModel(provider, base_url, getattr(settings, key_attr), model)