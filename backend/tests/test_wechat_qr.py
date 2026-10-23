import pytest

from app.auth.wechat import HttpWeChatClient, WeChatQrError

PNG = "PNGDATA"


class DictCache:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self.store[key] = value
        self.ttls[key] = ttl_s

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.store.pop(key, None)


def _urls(transport) -> list[str]:
    return [str(r.url) for r in transport.requests]


async def test_wxacode_fetches_and_caches_access_token(mock_transport):
    mock_transport.reply({"access_token": "TOK", "expires_in": 7200})
    mock_transport.reply(PNG)
    mock_transport.reply(PNG)
    cache = DictCache()
    client = HttpWeChatClient(transport=mock_transport, cache=cache)

    assert await client.wxacode("abc") == PNG.encode()
    assert await client.wxacode("def") == PNG.encode()

    token_calls = [u for u in _urls(mock_transport) if "/cgi-bin/token" in u]
    assert len(token_calls) == 1
    assert "grant_type=client_credential" in token_calls[0]
    assert cache.store["wx:access_token"] == "TOK"
    assert cache.ttls["wx:access_token"] == 7200 - 300


async def test_wxacode_posts_scene_page_env_version(mock_transport):
    mock_transport.reply({"access_token": "TOK", "expires_in": 7200})
    mock_transport.reply(PNG)
    client = HttpWeChatClient(transport=mock_transport, cache=DictCache())

    await client.wxacode("ticket123")

    req = mock_transport.requests[-1]
    assert req.method == "POST"
    assert "/wxa/getwxacodeunlimit" in str(req.url)
    assert "access_token=TOK" in str(req.url)
    assert mock_transport.last_body == {
        "scene": "ticket123",
        "page": "pages/web-login/index",
        "env_version": "trial",
        "check_path": False,
    }


async def test_wxacode_error_json_raises(mock_transport):
    mock_transport.reply({"access_token": "TOK", "expires_in": 7200})
    mock_transport.reply({"errcode": 45009, "errmsg": "reach max api minute quota limit"})
    client = HttpWeChatClient(transport=mock_transport, cache=DictCache())

    with pytest.raises(WeChatQrError, match="45009"):
        await client.wxacode("abc")


async def test_wxacode_40001_clears_cache_and_retries_once(mock_transport):
    mock_transport.reply({"access_token": "OLD", "expires_in": 7200})
    mock_transport.reply({"errcode": 40001, "errmsg": "invalid credential"})
    mock_transport.reply({"access_token": "NEW", "expires_in": 7200})
    mock_transport.reply(PNG)
    cache = DictCache()
    client = HttpWeChatClient(transport=mock_transport, cache=cache)

    assert await client.wxacode("abc") == PNG.encode()

    assert "wx:access_token" in cache.deleted
    assert cache.store["wx:access_token"] == "NEW"
    assert "access_token=NEW" in _urls(mock_transport)[-1]


async def test_wxacode_40001_twice_raises(mock_transport):
    mock_transport.reply({"access_token": "T", "expires_in": 7200})
    mock_transport.reply({"errcode": 40001, "errmsg": "invalid credential"})
    mock_transport.reply({"access_token": "T2", "expires_in": 7200})
    mock_transport.reply({"errcode": 40001, "errmsg": "invalid credential"})
    client = HttpWeChatClient(transport=mock_transport, cache=DictCache())

    with pytest.raises(WeChatQrError, match="40001"):
        await client.wxacode("abc")
    # token, code, token, code: exactly one retry
    assert len(mock_transport.requests) == 4


async def test_wxacode_token_error_raises(mock_transport):
    mock_transport.reply({"errcode": 40013, "errmsg": "invalid appid"})
    client = HttpWeChatClient(transport=mock_transport, cache=DictCache())

    with pytest.raises(WeChatQrError, match="40013"):
        await client.wxacode("abc")
