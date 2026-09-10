"""票据载荷构造与解析。"""

import json
import logging
from typing import Any

import cattrs

from ncg.core.exceptions import TicketError
from ncg.models.entities import (
    ApkDecoder,
    GatewayTicket,
    LockDetail,
    TicketExtra,
    TicketRequest,
    TicketResponse,
)
from ncg.protocol.crypto import brute_force_decode, offset_encode

logger = logging.getLogger(__name__)

#: HAR #437 实测编码列表
DEFAULT_CODECS: tuple[str, ...] = (
    "vp8",
    "rtx",
    "vp9",
    "vp9",
    "vp9",
    "vp9",
    "h264",
    "h264",
    "h264",
    "h264",
    "h264",
    "h264",
    "h264",
    "h264",
    "av1",
    "av1",
    "h264",
    "h264",
    "h265",
    "h265",
    "red",
    "ulpfec",
    "flexfec-03",
)

#: HAR 实测偏移
TICKET_OFFSET = 24


def build_ticket_payload(
    regions: tuple[str, ...],
    game_code: str,
    yidun_game_ticket: str,
    width: int = 1280,
    height: int = 720,
) -> bytes:
    """构造票据申请载荷。

    :param regions: 候选地域
    :param game_code: 游戏编码
    :param yidun_game_ticket: 易盾游戏票据，实测短 TTL 内可复用
    :param width: 请求宽度
    :param height: 请求高度
    :returns: 加密后字节
    :raises TicketError: 参数缺失
    """
    # 明文结构来自 HAR #437 offset=24 解码，不可臆造字段
    if not regions:
        raise TicketError("缺少候选地域")
    if not game_code:
        raise TicketError("缺少游戏编码")
    if not yidun_game_ticket:
        raise TicketError("缺少易盾游戏票据")
    request = TicketRequest(
        regions=regions,
        game_code=game_code,
        codecs=DEFAULT_CODECS,
        extra=TicketExtra(
            ali_input="local_insert",
            yidun_game_ticket=yidun_game_ticket,
            network_test_info_list=(),
        ),
        width=width,
        height=height,
        apk_decoder=ApkDecoder(model="", decoder=()),
    )
    plaintext = json.dumps(cattrs.unstructure(request))
    return offset_encode(TICKET_OFFSET, plaintext)


def parse_ticket_response(blob: bytes) -> TicketResponse:
    """解析票据响应。

    :param blob: 加密响应原文
    :returns: 票据响应摘要
    :raises TicketError: 解析失败
    """
    try:
        text = brute_force_decode(blob)
        raw: Any = json.loads(text)
        if not isinstance(raw, dict):
            raise TicketError("票据响应不是对象")
        gateway_url = raw.get("gateway_url")
        region = raw.get("region")
        game_code = raw.get("game_code")
        game_type = raw.get("game_type")
        if not isinstance(gateway_url, str) or not gateway_url:
            raise TicketError("票据响应缺少 gateway_url")
        if not isinstance(region, str) or not region:
            raise TicketError("票据响应缺少 region")
        if not isinstance(game_code, str) or not game_code:
            raise TicketError("票据响应缺少 game_code")
        if not isinstance(game_type, str) or not game_type:
            raise TicketError("票据响应缺少 game_type")
        lock_raw = raw.get("lock_detail")
        lock: LockDetail | None = None
        if isinstance(lock_raw, dict):
            lock_width = lock_raw.get("width")
            lock_height = lock_raw.get("height")
            lock_ip = lock_raw.get("ip")
            lock_port = lock_raw.get("port")
            if (
                isinstance(lock_width, int)
                and isinstance(lock_height, int)
                and isinstance(lock_ip, str)
                and isinstance(lock_port, int)
            ):
                lock = LockDetail(
                    region=region, width=lock_width, height=lock_height, ip=lock_ip, port=lock_port
                )
        return TicketResponse(
            gateway_url=gateway_url,
            region=region,
            game_code=game_code,
            game_type=game_type,
            non_vip_queue_len=_require_queue_int(raw, "non_vip_queue_len"),
            non_vip_queue_time=_require_queue_int(raw, "non_vip_queue_time"),
            vip_queue_len=_require_queue_int(raw, "vip_queue_len"),
            vip_queue_time=_require_queue_int(raw, "vip_queue_time"),
            time_left=_require_queue_int(raw, "time_left"),
            user_type=_require_user_type(raw),
            fast_created=_require_flag(raw, "fast_created"),
            preboot=_require_flag(raw, "preboot"),
            play_id=_require_play_id(raw),
            expires=_require_queue_int(raw, "expires"),
            lock_detail=lock,
        )
    except TicketError:
        raise
    except Exception as exc:
        logger.exception("解析票据响应失败")
        raise TicketError("解析票据响应失败") from exc


def to_gateway_ticket(response: TicketResponse) -> GatewayTicket:
    """转换为网关票据。

    :param response: 票据响应摘要
    :returns: 网关票据
    """
    return GatewayTicket(
        gateway_url=response.gateway_url, region=response.region, game_code=response.game_code
    )


def _require_queue_int(raw: dict[str, Any], key: str) -> int:
    """提取排队整数字段。

    :param raw: 原始对象
    :param key: 字段名
    :returns: 字段值
    :raises TicketError: 缺失或类型错误
    """
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TicketError(f"票据响应缺少字段：{key}")
    return value


def _require_user_type(raw: dict[str, Any]) -> str:
    """提取用户类型。

    :param raw: 原始对象
    :returns: 用户类型
    :raises TicketError: 缺失或类型错误
    """
    value = raw.get("user_type")
    if not isinstance(value, str) or not value:
        raise TicketError("票据响应缺少 user_type")
    return value


def _require_flag(raw: dict[str, Any], key: str) -> bool:
    """提取布尔标记。

    :param raw: 原始对象
    :param key: 字段名
    :returns: 字段值
    :raises TicketError: 缺失或类型错误
    """
    value = raw.get(key)
    if not isinstance(value, bool):
        raise TicketError(f"票据响应缺少字段：{key}")
    return value


def _require_play_id(raw: dict[str, Any]) -> str:
    """提取对局标识。

    :param raw: 原始对象
    :returns: 对局标识
    :raises TicketError: 缺失或类型错误
    """
    value = raw.get("play_id")
    if not isinstance(value, str) or not value:
        raise TicketError("票据响应缺少 play_id")
    return value
