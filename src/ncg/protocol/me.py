"""用户信息与节点解析。"""

import json
import logging
from typing import Any

from ncg.core.exceptions import AuthError, TicketError
from ncg.models.entities import (
    MediaServer,
    TimeRemain,
    UserMe,
    YunxinAccount,
)
from ncg.protocol.crypto import brute_force_decode

logger = logging.getLogger(__name__)


def parse_me(blob: bytes) -> UserMe:
    """解析 @me 响应。

    :param blob: 加密响应原文
    :returns: 当前用户信息
    :raises AuthError: 解析失败
    """
    try:
        raw: Any = json.loads(brute_force_decode(blob))
        if not isinstance(raw, dict):
            raise AuthError("@me 响应不是对象")
        user_id = raw.get("user_id")
        yunxin_raw = raw.get("yunxin_account")
        if not isinstance(user_id, str) or not user_id:
            raise AuthError("@me 缺少 user_id")
        if not isinstance(yunxin_raw, dict):
            raise AuthError("@me 缺少 yunxin_account")
        accid = yunxin_raw.get("accid")
        yunxin_token = yunxin_raw.get("token")
        if not isinstance(accid, str) or not accid:
            raise AuthError("@me 缺少云信 accid")
        if not isinstance(yunxin_token, str) or not yunxin_token:
            raise AuthError("@me 缺少云信 token")
        return UserMe(
            user_id=user_id,
            yunxin=YunxinAccount(accid=accid, token=yunxin_token),
            free_time=_require_int(raw, "free_time"),
            free_time_left=_require_int(raw, "free_time_left"),
            pc_free_time_left=_require_int(raw, "pc_free_time_left"),
            pc_free_time_left_this_week=_require_int(raw, "pc_free_time_left_this_week"),
            pc_vip_time_left=_require_int(raw, "pc_vip_time_left"),
            coins=_require_int(raw, "coins"),
            coins_per_minute=_require_int(raw, "coins_consume_per_minute"),
            is_vip=_require_bool(raw, "is_vip"),
            is_now_daily_vip=_require_bool(raw, "is_now_daily_vip"),
        )
    except AuthError:
        raise
    except Exception as exc:
        logger.exception("解析 @me 失败")
        raise AuthError("解析 @me 失败") from exc


def parse_time_remain(blob: bytes) -> TimeRemain:
    """解析剩余时长响应。

    :param blob: 加密响应原文
    :returns: 剩余时长结果
    :raises AuthError: 解析失败
    """
    try:
        raw: Any = json.loads(brute_force_decode(blob))
        if not isinstance(raw, dict):
            raise AuthError("时长响应不是对象")
        return TimeRemain(
            is_daily_free=_require_bool(raw, "is_daily_free"),
            is_limit_time=_require_bool(raw, "is_limit_time"),
        )
    except AuthError:
        raise
    except Exception as exc:
        logger.exception("解析时长失败")
        raise AuthError("解析时长失败") from exc


def parse_media_servers(blob: bytes) -> tuple[MediaServer, ...]:
    """解析媒体节点列表。

    :param blob: 加密响应原文
    :returns: 节点元组
    :raises TicketError: 解析失败
    """
    try:
        raw: Any = json.loads(brute_force_decode(blob))
        if not isinstance(raw, list):
            raise TicketError("节点响应不是数组")
        servers: list[MediaServer] = []
        for item in raw:
            if not isinstance(item, dict):
                raise TicketError("节点条目不是对象")
            servers.append(
                MediaServer(
                    region=_require_str(item, "region"),
                    game_type=_require_str(item, "game_type"),
                    resolution_type=_require_str(item, "resolution_type"),
                    is_1080=_require_bool(item, "is_1080"),
                    ping_url=_require_str(item, "ping_url"),
                    ping_url1=_require_str(item, "ping_url1"),
                    ping_url2=_require_str(item, "ping_url2"),
                    ping_url3=_require_str(item, "ping_url3"),
                    score_required=_require_int(item, "score_required"),
                    latency_required=_require_int(item, "latency_required"),
                    latency_recommended=_require_int(item, "latency_recommended"),
                    bandwidth_required=_require_int(item, "bandwidth_required"),
                    bandwidth_recommended=_require_int(item, "bandwidth_recommended"),
                    isp=_require_int(item, "isp"),
                    isp_weight=_require_int(item, "isp_weight"),
                    ping_weight=_require_int(item, "ping_weight"),
                    loss_weight=_require_int(item, "loss_weight"),
                    no_latency_block=_require_bool(item, "no_latency_block"),
                )
            )
        return tuple(servers)
    except TicketError:
        raise
    except Exception as exc:
        logger.exception("解析节点失败")
        raise TicketError("解析节点失败") from exc


def _require_str(raw: dict[str, Any], key: str) -> str:
    """提取字符串字段。

    :param raw: 原始对象
    :param key: 字段名
    :returns: 字段值
    :raises AuthError: 缺失或类型错误
    """
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise AuthError(f"缺少字段：{key}")
    return value


def _require_int(raw: dict[str, Any], key: str) -> int:
    """提取整数值字段。

    :param raw: 原始对象
    :param key: 字段名
    :returns: 字段值
    :raises AuthError: 缺失或类型错误
    """
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuthError(f"缺少字段：{key}")
    return value


def _require_bool(raw: dict[str, Any], key: str) -> bool:
    """提取布尔字段。

    :param raw: 原始对象
    :param key: 字段名
    :returns: 字段值
    :raises AuthError: 缺失或类型错误
    """
    value = raw.get(key)
    if not isinstance(value, bool):
        raise AuthError(f"缺少字段：{key}")
    return value
