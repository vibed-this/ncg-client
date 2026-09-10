"""票据载荷测试。"""

import json

import pytest

from ncg.core.exceptions import TicketError
from ncg.protocol.crypto import brute_force_decode, offset_encode
from ncg.protocol.tickets import build_ticket_payload, parse_ticket_response


def _full_response_text() -> str:
    """构造完整票据响应明文。"""
    return json.dumps(
        {
            "gateway_url": "wss://gw-yd-shzwh-03.cg.163.com:6443/ws",
            "region": "shzwh4",
            "game_code": "cywlbfwt",
            "game_type": "mobile",
            "non_vip_queue_len": 0,
            "non_vip_queue_time": 1,
            "vip_queue_len": 0,
            "vip_queue_time": 1,
            "time_left": 24,
            "user_type": "restart",
            "fast_created": True,
            "preboot": False,
            "play_id": "6aa2907eeb9513db624bcf26",
            "expires": 1789038744,
            "lock_detail": {
                "width": 1920,
                "height": 1080,
                "ip": "10.85.97.141",
                "port": 10000,
            },
        }
    )


def test_build_ticket_payload_roundtrip() -> None:
    """构造的载荷解码后应含关键字段。"""
    regions = ("shzwh4", "shnkpl4")
    blob = build_ticket_payload(regions, "cywlbfwt", "yidun-test-ticket")
    text = brute_force_decode(blob)
    assert "cywlbfwt" in text
    assert "shzwh4" in text
    assert "yidun-test-ticket" in text


def test_build_ticket_payload_rejects_empty() -> None:
    """缺参应 fast-fail。"""
    with pytest.raises(TicketError):
        build_ticket_payload((), "cywlbfwt", "t")
    with pytest.raises(TicketError):
        build_ticket_payload(("shzwh4",), "", "t")
    with pytest.raises(TicketError):
        build_ticket_payload(("shzwh4",), "cywlbfwt", "")


def test_parse_ticket_response() -> None:
    """解析响应应提取网关地址与排队字段。"""
    response = parse_ticket_response(offset_encode(24, _full_response_text()))
    assert response.gateway_url.endswith("/ws")
    assert response.region == "shzwh4"
    assert response.non_vip_queue_len == 0
    assert response.lock_detail is not None
    assert response.lock_detail.width == 1920


def test_parse_ticket_response_rejects_missing_queue() -> None:
    """缺排队字段应 fast-fail。"""
    text = json.dumps(
        {
            "gateway_url": "wss://gw-yd-shzwh-03.cg.163.com:6443/ws",
            "region": "shzwh4",
            "game_code": "cywlbfwt",
            "game_type": "mobile",
        }
    )
    with pytest.raises(TicketError):
        parse_ticket_response(offset_encode(24, text))
