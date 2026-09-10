"""地域测速优选。"""

import logging

from ncg.core.exceptions import TicketError
from ncg.models.entities import PingSample

logger = logging.getLogger(__name__)


def filter_and_sort(samples: tuple[PingSample, ...]) -> tuple[PingSample, ...]:
    """过滤并按延迟升序排序。

    :param samples: 测速样本
    :returns: 候选样本
    :raises TicketError: 样本为空或无候选
    """
    # 规则来自 chunk-common：no_latency_block 恒过，否则需 delay < latency_required
    if not samples:
        raise TicketError("缺少测速样本")
    candidates: list[PingSample] = []
    for sample in samples:
        required = sample.server.latency_required
        if sample.server.no_latency_block or sample.delay < required:
            candidates.append(sample)
    if not candidates:
        logger.error("测速样本全被门限剔除")
        raise TicketError("无可用地域")
    ordered = tuple(sorted(candidates, key=lambda item: item.delay))
    logger.debug("优选地域：%s", [item.region for item in ordered])
    return ordered


def to_ticket_regions(ordered: tuple[PingSample, ...]) -> tuple[str, ...]:
    """转换为票据地域列表。

    :param ordered: 已排序样本
    :returns: 地域元组
    :raises TicketError: 输入为空
    """
    if not ordered:
        raise TicketError("缺少已排序样本")
    return tuple(item.region for item in ordered)


def pick_best(ordered: tuple[PingSample, ...]) -> PingSample:
    """选取最优样本。

    :param ordered: 已排序样本
    :returns: 首个样本
    :raises TicketError: 输入为空
    """
    if not ordered:
        raise TicketError("缺少已排序样本")
    return ordered[0]
