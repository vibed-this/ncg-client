"""用户信息与节点解析测试。"""

import json

import pytest

from ncg.core.exceptions import AuthError
from ncg.protocol.crypto import offset_encode
from ncg.protocol.me import parse_me, parse_media_servers, parse_time_remain


def _me_text() -> str:
    """构造 @me 明文。"""
    return json.dumps(
        {
            "user_id": "5fafd9142e0942f8032dc1c0",
            "yunxin_account": {"accid": "5fafd9142e0942f8032dc1c0", "token": "yunxin-token"},
            "free_time": 1800,
            "free_time_left": 1698,
            "pc_free_time_left": 0,
            "pc_free_time_left_this_week": 0,
            "pc_vip_time_left": 0,
            "coins": 0,
            "coins_consume_per_minute": 3,
            "is_vip": False,
            "is_now_daily_vip": False,
        }
    )


def test_parse_me() -> None:
    """解析 @me 应提取用户标识。"""
    me = parse_me(offset_encode(24, _me_text()))
    assert me.user_id == "5fafd9142e0942f8032dc1c0"
    assert me.yunxin.accid == me.user_id
    assert me.free_time_left == 1698


def test_parse_me_rejects_missing() -> None:
    """缺 user_id 应 fast-fail。"""
    with pytest.raises(AuthError):
        parse_me(offset_encode(24, json.dumps({"yunxin_account": {}})))


def test_parse_time_remain() -> None:
    """解析时长应提取标记。"""
    remain = parse_time_remain(
        offset_encode(24, json.dumps({"is_daily_free": False, "is_limit_time": False}))
    )
    assert remain.is_daily_free is False


def test_parse_media_servers() -> None:
    """解析节点应提取地域。"""
    text = json.dumps(
        [
            {
                "region": "shzwh4",
                "game_type": "mobile",
                "resolution_type": "1920*1080",
                "is_1080": True,
                "ping_url": "https://gw-dx-shzwh-03.cg.163.com:6443/ping",
                "ping_url1": "https://gw-dx-shzwh-03.cg.163.com:6443/ping",
                "ping_url2": "https://gw-lt-shzwh-03.cg.163.com:6443/ping",
                "ping_url3": "https://gw-yd-shzwh-03.cg.163.com:6443/ping",
                "score_required": 100,
                "latency_required": 200,
                "latency_recommended": 50,
                "bandwidth_required": 2,
                "bandwidth_recommended": 20,
                "isp": 0,
                "isp_weight": 100,
                "ping_weight": 600,
                "loss_weight": 100,
                "no_latency_block": False,
            }
        ]
    )
    servers = parse_media_servers(offset_encode(24, text))
    assert len(servers) == 1
    assert servers[0].region == "shzwh4"
