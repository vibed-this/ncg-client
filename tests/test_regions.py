"""地域优选测试。"""

import pytest

from ncg.core.exceptions import TicketError
from ncg.models.entities import MediaServer, PingSample
from ncg.protocol.regions import filter_and_sort, pick_best, to_ticket_regions


def _server(region: str, required: int, blocked: bool) -> MediaServer:
    """构造节点。"""
    return MediaServer(
        region=region,
        game_type="mobile",
        resolution_type="1920*1080",
        is_1080=True,
        ping_url="https://example.invalid/ping",
        ping_url1="https://example.invalid/ping",
        ping_url2="https://example.invalid/ping",
        ping_url3="https://example.invalid/ping",
        score_required=100,
        latency_required=required,
        latency_recommended=50,
        bandwidth_required=2,
        bandwidth_recommended=20,
        isp=0,
        isp_weight=100,
        ping_weight=600,
        loss_weight=100,
        no_latency_block=blocked,
    )


def test_filter_and_sort_orders_by_delay() -> None:
    """过滤应剔除超限并按延迟升序。"""
    samples = (
        PingSample(region="shzwh4", delay=37, expire=0, server=_server("shzwh4", 200, False)),
        PingSample(region="shdsx4", delay=2000, expire=0, server=_server("shdsx4", 200, False)),
        PingSample(region="tghbtj", delay=142, expire=0, server=_server("tghbtj", 1000, True)),
    )
    ordered = filter_and_sort(samples)
    assert to_ticket_regions(ordered) == ("shzwh4", "tghbtj")
    assert pick_best(ordered).region == "shzwh4"


def test_filter_and_sort_rejects_empty() -> None:
    """空样本应 fast-fail。"""
    with pytest.raises(TicketError):
        filter_and_sort(())
    with pytest.raises(TicketError):
        pick_best(())
