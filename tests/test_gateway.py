"""网关连接测试。"""

import json
import time
from typing import Any
from unittest.mock import MagicMock, patch

from websockets.exceptions import ConnectionClosedOK
from websockets.frames import Close

from ncg.models.entities import GatewayTicket
from ncg.protocol.crypto import offset_encode
from ncg.signaling.gateway import GatewaySocket


def _ticket() -> GatewayTicket:
    """构造测试票据。"""
    return GatewayTicket(
        gateway_url="wss://gw-yd-shzwh-03.cg.163.com:6443/ws",
        region="shzwh4",
        game_code="cywlbfwt",
    )


def test_connect_disables_protocol_keepalive() -> None:
    """连接必须关闭 WS 协议级保活，网关不回 pong 会误杀长会话。"""
    socket = MagicMock()
    offer = json.dumps({"id": "1", "op": "offer", "data": {"sdp": "v=0"}})
    socket.recv.return_value = offer
    with patch(
        "ncg.signaling.gateway.ws_sync.connect", return_value=socket
    ) as connect_mock:
        gateway = GatewaySocket(_ticket())
        assert gateway.connect('{"op":"auth"}') == "v=0"
    assert connect_mock.call_args.kwargs["ping_interval"] is None
    assert connect_mock.call_args.kwargs["ping_timeout"] is None


def _closed() -> ConnectionClosedOK:
    """构造正常关闭异常。"""
    return ConnectionClosedOK(Close(1000, "ok"), Close(1000, "ok"), True)


def test_reader_dispatches_and_matches_echo() -> None:
    """reader 应分发下行并配对保活回显。"""
    now_ms = int(time.time() * 1000)
    echo = json.dumps({"id": "9", "op": "input", "data": {"cmd": f"0 {now_ms - 50}"}})
    socket = MagicMock()
    socket.recv.side_effect = [
        '{"id":"1","op":"result","data":[]}',
        offset_encode(24, echo).decode("ascii"),
        _closed(),
    ]
    gateway = GatewaySocket(_ticket())
    object.__setattr__(gateway, "_socket", socket)
    object.__setattr__(gateway, "_last_keepalive_ts", str(now_ms - 50))
    got: list[dict[str, Any]] = []
    thread = gateway.start_reader(got.append)
    thread.join(timeout=5.0)
    assert not thread.is_alive()
    assert [env["op"] for env in got] == ["result", "input"]
    assert gateway.last_echo_rtt_ms is not None
    assert 0 <= gateway.last_echo_rtt_ms < 5000


def test_reader_ignores_stale_echo() -> None:
    """非本次保活的回显不应刷新 RTT。"""
    socket = MagicMock()
    stale = json.dumps({"id": "9", "op": "input", "data": {"cmd": "0 123"}})
    socket.recv.side_effect = [stale, _closed()]
    gateway = GatewaySocket(_ticket())
    object.__setattr__(gateway, "_socket", socket)
    object.__setattr__(gateway, "_last_keepalive_ts", "999")
    got: list[dict[str, Any]] = []
    thread = gateway.start_reader(got.append)
    thread.join(timeout=5.0)
    assert len(got) == 1
    assert gateway.last_echo_rtt_ms is None
