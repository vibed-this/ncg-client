"""推流统计测试。"""

import pytest

from ncg.core.exceptions import SessionError, SignalingError
from ncg.media.video import jitter_to_ms
from ncg.models.entities import StreamStats, loss_percent
from ncg.signaling.gateway import gateway_ping_url


def test_jitter_to_ms_video_clock() -> None:
    """90单位抖动在90k时钟下应为1毫秒。"""
    assert jitter_to_ms(90) == pytest.approx(1.0)


def test_jitter_to_ms_rejects_bad_clock() -> None:
    """非法时钟频率应 fast-fail。"""
    with pytest.raises(SessionError):
        jitter_to_ms(90, 0)


def test_loss_percent_matches_web_formula() -> None:
    """丢包率应与网页 se() 公式一致。"""
    assert loss_percent(5, 95) == pytest.approx(5.0)
    assert loss_percent(0, 0) == pytest.approx(0.0)


def test_loss_percent_rejects_negative() -> None:
    """负增量应 fast-fail。"""
    with pytest.raises(SessionError):
        loss_percent(-1, 10)


def test_gateway_ping_url() -> None:
    """WSS 地址应推导出同 host 测速地址。"""
    assert (
        gateway_ping_url("wss://gw-lt-shzwh-02.cg.163.com:6443/ws")
        == "https://gw-lt-shzwh-02.cg.163.com:6443/ping"
    )


def test_gateway_ping_url_rejects_bad_scheme() -> None:
    """非 WSS 地址应 fast-fail。"""
    with pytest.raises(SignalingError):
        gateway_ping_url("https://gw-lt-shzwh-02.cg.163.com:6443/ws")


def test_stream_stats_fields() -> None:
    """快照字段应原样保留。"""
    stats = StreamStats(
        delay_ms=37.0,
        loss_percent=0.5,
        fps=30.0,
        packets_received=100,
        packets_lost=1,
        frames_decoded=60,
    )
    assert stats.delay_ms == pytest.approx(37.0)
    assert stats.loss_percent == pytest.approx(0.5)
