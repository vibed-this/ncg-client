"""会话止损测试。"""

import httpx

from ncg.api.client import NcgApi
from ncg.core.http import NcgHttpClient
from ncg.models.entities import GatewayTicket
from ncg.session.manager import GameSession
from ncg.signaling.gateway import GatewaySocket


def _ok_transport() -> httpx.MockTransport:
    """构造全 200 的模拟传输。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"k5Ui")

    return httpx.MockTransport(handler)


def test_stop_is_idempotent_and_clears_flag(monkeypatch: object) -> None:
    """结束应幂等并清除计费旗。"""
    transport = _ok_transport()
    client = httpx.Client(transport=transport)
    http = NcgHttpClient("token")
    object.__setattr__(http, "_client", client)
    api = NcgApi(http)
    gateway = GatewaySocket(
        GatewayTicket(
            gateway_url="wss://gw-yd-shzwh-03.cg.163.com:6443/ws",
            region="shzwh4",
            game_code="cywlbfwt",
        )
    )
    session = GameSession(api, gateway, "cywlbfwt")
    session.mark_started()
    assert session.playing
    session.stop()
    assert not session.playing
    session.stop()
    assert not session.playing
