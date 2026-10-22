from typing import Literal

from app.ai.base import VisionModel
from app.ai.openai_compat import OpenAICompatModel
from app.config import Settings, get_settings

Purpose = Literal["grading", "answer_key", "practice_generate", "practice_verify", "analysis"]

# provider -> (base URL setting, API key setting)
_PROVIDERS = {
    "qwen": ("QWEN_BASE_URL", "DASHSCOPE_API_KEY"),
    "doubao": ("ARK_BASE_URL", "ARK_API_KEY"),
    "deepseek": ("DEEPSEEK_BASE_URL", "DEEPSEEK_API_KEY"),
}


def _parse(value: str) -> tuple[str, str]:
    provider, sep, model = value.partition(":")
    if not sep or not model or provider not in _PROVIDERS:
        raise ValueError(f"invalid model setting {value!r}; expected '<provider>:<model>' with provider one of {sorted(_PROVIDERS)}")
    return provider, model


def _setting(settings: Settings, purpose: str) -> str:
    try:
        return getattr(settings, f"MODEL_FOR_{purpose.upper()}")
    except AttributeError:
        raise ValueError(f"unknown purpose {purpose!r}") from None


def build_model(spec: str) -> VisionModel:
    """Build a model from a "provider:model" spec."""
    provider, model = _parse(spec)
    url_attr, key_attr = _PROVIDERS[provider]
    settings = get_settings()
    return OpenAICompatModel(provider, getattr(settings, url_attr), getattr(settings, key_attr), model)


def get_model(purpose: Purpose) -> VisionModel:
    settings = get_settings()
    provider, _ = _parse(_setting(settings, purpose))
    if purpose == "practice_verify":
        gen_provider, _ = _parse(_setting(settings, "practice_generate"))
        if provider == gen_provider:
            raise ValueError("practice_verify must use a different provider than practice_generate")
    return build_model(_setting(settings, purpose))

