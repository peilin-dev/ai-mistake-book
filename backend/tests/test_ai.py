import base64
import json

import httpx
import pytest
from sqlalchemy import select

from app.ai.base import ModelCallError, ModelOutputError, ModelResult
from app.ai.fake import FakeModel
from app.ai.openai_compat import OpenAICompatModel
from app.ai.registry import build_model, get_model
from app.ai.usage import record_usage
from app.models import UsageRecord


def _ok(content: str, **extra) -> dict:
    return {"choices": [{"message": {"content": content}}], **extra}


async def test_openai_compat_parses_json_and_usage(mock_transport):
    mock_transport.reply({"choices": [{"message": {"content": '{"a": 1}'}}],
                          "usage": {"prompt_tokens": 100, "completion_tokens": 20}, "model": "qwen-vl-max"})
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "qwen-vl-max", transport=mock_transport)
    r = await m.complete_json("p", [b"img"])
    assert r.data == {"a": 1} and r.input_tokens == 100 and r.output_tokens == 20
    assert r.provider == "qwen" and r.model == "qwen-vl-max"


async def test_request_shape(mock_transport):
    mock_transport.reply(_ok("{}"))
    m = OpenAICompatModel("qwen", "https://x/v1", "secret", "m1", transport=mock_transport)
    await m.complete_json("hello", [b"img1", b"img2"])
    req = mock_transport.requests[0]
    assert req.method == "POST" and str(req.url) == "https://x/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer secret"
    body = mock_transport.last_body
    assert body["model"] == "m1"
    assert body["response_format"] == {"type": "json_object"}
    (msg,) = body["messages"]
    assert msg["role"] == "user"
    assert msg["content"][0] == {"type": "text", "text": "hello"}
    urls = [p["image_url"]["url"] for p in msg["content"][1:]]
    assert urls == ["data:image/jpeg;base64," + base64.b64encode(b).decode() for b in (b"img1", b"img2")]


async def test_fenced_json_is_unwrapped(mock_transport):
    mock_transport.reply(_ok('```json\n{"a": 2}\n```'))
    mock_transport.reply(_ok('```\n{"a": 3}\n```'))
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "m", transport=mock_transport)
    assert (await m.complete_json("p", [])).data == {"a": 2}
    assert (await m.complete_json("p", [])).data == {"a": 3}


async def test_missing_usage_and_model_fallback(mock_transport):
    mock_transport.reply(_ok('{"a": 1}'))
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "cfg-model", transport=mock_transport)
    r = await m.complete_json("p", [])
    assert (r.input_tokens, r.output_tokens, r.model) == (0, 0, "cfg-model")


async def test_non_json_content_raises(mock_transport):
    mock_transport.reply({"choices": [{"message": {"content": "not json"}}], "usage": {}})
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "m", transport=mock_transport)
    with pytest.raises(ModelOutputError):
        await m.complete_json("p", [])


@pytest.mark.parametrize("content", ["[1, 2]", "3", '"s"'])
async def test_non_object_json_raises(mock_transport, content):
    mock_transport.reply(_ok(content))
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "m", transport=mock_transport)
    with pytest.raises(ModelOutputError):
        await m.complete_json("p", [])


async def test_http_error_raises_call_error(mock_transport):
    mock_transport.reply("boom", status=500)
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "m", transport=mock_transport)
    with pytest.raises(ModelCallError) as ei:
        await m.complete_json("p", [])
    assert not isinstance(ei.value, ModelOutputError)


async def test_transport_error_raises_call_error(mock_transport):
    mock_transport.fail(httpx.ConnectError("down"))
    with pytest.raises(ModelCallError):
        await _model(mock_transport).complete_json("p", [])


def _model(transport, **kw) -> OpenAICompatModel:
    return OpenAICompatModel("qwen", "https://x/v1", "k", "m", transport=transport, retry_backoff=0, **kw)


async def test_connect_failures_are_retried_then_succeed(mock_transport):
    mock_transport.fail(httpx.ConnectTimeout("handshake timed out"))
    mock_transport.fail(httpx.ConnectError("reset"))
    mock_transport.reply(_ok('{"a": 1}'))
    r = await _model(mock_transport).complete_json("p", [])
    assert r.data == {"a": 1}
    assert len(mock_transport.requests) == 3


async def test_connect_failures_give_up_after_attempts(mock_transport):
    mock_transport.fail(httpx.ConnectTimeout("handshake timed out"))
    with pytest.raises(ModelCallError):
        await _model(mock_transport, attempts=3).complete_json("p", [])
    assert len(mock_transport.requests) == 3


async def test_read_timeout_is_not_retried(mock_transport):
    # The request reached the provider and may already be billed: never send it twice.
    mock_transport.fail(httpx.ReadTimeout("slow"))
    mock_transport.reply(_ok('{"a": 1}'))
    with pytest.raises(ModelCallError):
        await _model(mock_transport).complete_json("p", [])
    assert len(mock_transport.requests) == 1


@pytest.mark.parametrize("status", [429, 502, 503, 504])
async def test_transient_statuses_are_retried(mock_transport, status):
    mock_transport.reply("busy", status=status)
    mock_transport.reply(_ok('{"a": 1}'))
    assert (await _model(mock_transport).complete_json("p", [])).data == {"a": 1}
    assert len(mock_transport.requests) == 2


@pytest.mark.parametrize("status", [400, 401, 404, 500])
async def test_other_statuses_are_not_retried(mock_transport, status):
    mock_transport.reply("nope", status=status)
    mock_transport.reply(_ok('{"a": 1}'))
    with pytest.raises(ModelCallError):
        await _model(mock_transport).complete_json("p", [])
    assert len(mock_transport.requests) == 1


async def test_retry_waits_with_growing_backoff(mock_transport, monkeypatch):
    waits: list[float] = []

    async def fake_sleep(s: float) -> None:
        waits.append(s)

    monkeypatch.setattr("app.ai.openai_compat.asyncio.sleep", fake_sleep)
    mock_transport.fail(httpx.ConnectError("reset"))
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "m", transport=mock_transport, retry_backoff=1.0)
    with pytest.raises(ModelCallError):
        await m.complete_json("p", [])
    assert waits == [1.0, 2.0]


def test_timeouts_and_attempts_come_from_settings(settings):
    settings.MODEL_CONNECT_TIMEOUT_S = 7
    settings.MODEL_TIMEOUT_S = 90
    settings.MODEL_CALL_ATTEMPTS = 4
    m = OpenAICompatModel("qwen", "https://x/v1", "k", "m")
    assert (m.timeout.connect, m.timeout.read, m.attempts) == (7, 90, 4)


async def test_fake_model_sequence_and_exhaustion():
    boom = RuntimeError("boom")
    f = FakeModel([{"a": 1}, boom])
    r = await f.complete_json("p1", [])
    assert r == ModelResult({"a": 1}, 0, 0, "fake", "fake")
    with pytest.raises(RuntimeError):
        await f.complete_json("p2", [])
    with pytest.raises(AssertionError, match="FakeModel exhausted"):
        await f.complete_json("p3", [])
    assert f.prompts == ["p1", "p2", "p3"]


def test_get_model_by_purpose(settings):
    settings.DASHSCOPE_API_KEY = "dk"
    settings.ARK_API_KEY = "ak"
    settings.MODEL_FOR_GRADING = "qwen:qwen-vl-plus"
    m = get_model("grading")
    assert isinstance(m, OpenAICompatModel)
    assert (m.provider, m.model, m.base_url, m.api_key) == (
        "qwen", "qwen-vl-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1", "dk")
    settings.MODEL_FOR_PRACTICE_VERIFY = "doubao:doubao-vision"
    v = get_model("practice_verify")
    assert (v.provider, v.base_url, v.api_key) == (
        "doubao", "https://ark.cn-beijing.volces.com/api/v3", "ak")


def test_base_url_comes_from_settings(settings):
    settings.QWEN_BASE_URL = "https://ws-abc.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    settings.ARK_BASE_URL = "https://ark.example/api/v3"
    settings.MODEL_FOR_GRADING = "qwen:qwen-vl-max"
    settings.MODEL_FOR_PRACTICE_VERIFY = "doubao:doubao-vision"
    assert get_model("grading").base_url == "https://ws-abc.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    assert get_model("practice_verify").base_url == "https://ark.example/api/v3"


@pytest.mark.parametrize("value", ["nocolon", "openai:gpt", "qwen:", ":m"])
def test_get_model_bad_value(settings, value):
    settings.MODEL_FOR_GRADING = value
    with pytest.raises(ValueError):
        get_model("grading")


def test_deepseek_provider_builds_model(settings):
    settings.DEEPSEEK_API_KEY = "dsk"
    m = build_model("deepseek:deepseek-v4-pro")
    assert isinstance(m, OpenAICompatModel)
    assert (m.provider, m.model, m.base_url, m.api_key) == (
        "deepseek", "deepseek-v4-pro", "https://api.deepseek.com", "dsk")


def test_practice_verify_defaults_to_deepseek(settings):
    settings.DEEPSEEK_API_KEY = "dsk"
    assert get_model("practice_verify").provider == "deepseek"
    assert get_model("practice_generate").provider == "qwen"


def test_practice_verify_same_provider_still_rejected(settings):
    settings.MODEL_FOR_PRACTICE_VERIFY = "deepseek:deepseek-flash"
    settings.MODEL_FOR_PRACTICE_GENERATE = "deepseek:deepseek-v4-pro"
    with pytest.raises(ValueError, match="different"):
        get_model("practice_verify")


def test_verify_must_differ_from_generate(settings):
    settings.MODEL_FOR_PRACTICE_VERIFY = "qwen:qwen-vl-max"
    with pytest.raises(ValueError, match="different"):
        get_model("practice_verify")


async def test_record_usage_cost(db, teacher, settings):
    settings.PRICE_FEN_PER_1K = {"qwen-vl-max": (0.3, 0.9)}
    await record_usage(db, teacher.id, "grading",
                       ModelResult({}, 2000, 1000, "qwen-vl-max", "qwen"))
    row = (await db.execute(select(UsageRecord))).scalar_one()
    assert row.cost_fen == pytest.approx(0.3 * 2 + 0.9 * 1)
    assert (row.provider, row.model, row.purpose, row.input_tokens, row.output_tokens) == (
        "qwen", "qwen-vl-max", "grading", 2000, 1000)


async def test_record_usage_unknown_model_costs_zero(db, teacher, settings):
    await record_usage(db, teacher.id, "grading", ModelResult({}, 5, 5, "fake", "fake"))
    row = (await db.execute(select(UsageRecord))).scalar_one()
    assert row.cost_fen == 0


async def test_record_usage_keeps_four_decimals(db, teacher, settings):
    settings.PRICE_FEN_PER_1K = {"m": (0.0123, 0.0)}
    await record_usage(db, teacher.id, "grading", ModelResult({}, 1000, 0, "m", "qwen"))
    row = (await db.execute(select(UsageRecord))).scalar_one()
    assert float(row.cost_fen) == pytest.approx(0.0123)
