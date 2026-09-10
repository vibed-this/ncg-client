"""键鼠与文本输入编码。"""

import base64
import logging

from ncg.core.exceptions import SessionError
from ncg.models.entities import (
    ClipboardText,
    KeyPress,
    MobileKey,
    MouseClick,
    MouseMove,
    TextStroke,
)

logger = logging.getLogger(__name__)


def encode_mouse_down(move: MouseMove) -> str:
    """编码鼠标按下。

    :param move: 移动目标
    :returns: 命令原文
    :raises SessionError: 坐标非法
    """
    _require_point(move.point.x, move.point.y)
    return f"1 {move.point.x} {move.point.y} 0"


def encode_mouse_move(move: MouseMove) -> str:
    """编码鼠标移动。

    :param move: 移动目标
    :returns: 命令原文
    :raises SessionError: 坐标非法
    """
    _require_point(move.point.x, move.point.y)
    return f"2 {move.point.x} {move.point.y} 0"


def encode_mouse_up(click: MouseClick) -> str:
    """编码鼠标抬起。

    :param click: 点击位置
    :returns: 命令原文
    :raises SessionError: 坐标非法
    """
    _require_point(click.point.x, click.point.y)
    return f"3 {click.point.x} {click.point.y} 0"


def encode_text(stroke: TextStroke) -> str:
    """编码单字文本。

    :param stroke: 单字
    :returns: 命令原文
    :raises SessionError: 文本非法
    """
    # HAR 实证逐字发送，整串必须拆开发送
    if len(stroke.char) != 1:
        raise SessionError(f"必须单字发送，实际长度：{len(stroke.char)}")
    return f"5 {stroke.char}"


def _require_point(x: int, y: int) -> None:
    """校验像素坐标。

    :param x: 横坐标
    :param y: 纵坐标
    :raises SessionError: 坐标非法
    """
    if x < 0 or y < 0:
        raise SessionError(f"坐标非法：{x},{y}")


def encode_key_down(key: KeyPress) -> str:
    """编码按键按下（PC 104 前缀）。

    :param key: 按键描述
    :returns: 命令原文
    :raises SessionError: 按键非法
    """
    state = _require_key(key)
    return f"104 {key.code} {key.name} {state}"


def encode_key_up(key: KeyPress) -> str:
    """编码按键抬起（PC 105 前缀）。

    :param key: 按键描述
    :returns: 命令原文
    :raises SessionError: 按键非法
    """
    state = _require_key(key)
    return f"105 {key.code} {key.name} {state}"


def encode_key_tap(key: KeyPress, hold_ms: int = 16) -> tuple[str, str, str]:
    """编码一次点按（按下、等待、抬起）。

    :param key: 按键描述
    :param hold_ms: 按住毫秒数
    :returns: 按下、等待、抬起三元组
    :raises SessionError: 参数非法
    """
    if hold_ms < 0 or hold_ms > 1000:
        raise SessionError(f"按住时长非法：{hold_ms}")
    _require_key(key)
    state = key.modifiers.to_state()
    return (f"104 {key.code} {key.name} {state}", f"133 {hold_ms}", f"105 {key.code} {key.name} {state}")


def encode_ctrl_v() -> tuple[str, ...]:
    """编码粘贴组合键（run.js 实证序列）。

    :returns: 8 条命令元组
    """
    # 粘贴实证：104 17 control 2 → 133 16 → 104 86 v 2 → 133 16 → 105 … → 133 16
    return (
        "104 17 control 2",
        "133 16",
        "104 86 v 2",
        "133 16",
        "105 17 control 0",
        "133 16",
        "105 86 v 0",
        "133 16",
    )


def encode_mobile_key(key: MobileKey) -> str:
    """编码移动端 IME 按键（6 前缀）。

    :param key: 按键枚举值
    :returns: 命令原文
    :raises SessionError: 取值非法
    """
    # 1 退格、2 回车、3 左、4 右；上下无映射
    if key.code not in (1, 2, 3, 4):
        raise SessionError(f"移动按键非法：{key.code}")
    return f"6 {key.code}"


def encode_sleep_pc(ms: int) -> str:
    """编码 PC 等待（133 前缀）。

    :param ms: 毫秒数
    :returns: 命令原文
    :raises SessionError: 参数非法
    """
    if ms < 0 or ms > 60000:
        raise SessionError(f"等待时长非法：{ms}")
    return f"133 {ms}"


def encode_sleep_mobile(ms: int) -> str:
    """编码移动端等待（17 前缀）。

    :param ms: 毫秒数
    :returns: 命令原文
    :raises SessionError: 参数非法
    """
    if ms < 0 or ms > 60000:
        raise SessionError(f"等待时长非法：{ms}")
    return f"17 {ms}"


def encode_clipboard_pc(clip: ClipboardText) -> str:
    """编码 PC 剪贴板（138 前缀）。

    :param clip: 剪贴板原文
    :returns: 命令原文
    :raises SessionError: 文本为空
    """
    if not clip.text:
        raise SessionError("剪贴板文本为空")
    encoded = base64.b64encode(clip.text.encode("utf-8")).decode("ascii")
    return f"138 {encoded}"


def encode_clipboard_mobile(clip: ClipboardText) -> str:
    """编码移动端剪贴板（29 前缀）。

    :param clip: 剪贴板原文
    :returns: 命令原文
    :raises SessionError: 文本为空
    """
    if not clip.text:
        raise SessionError("剪贴板文本为空")
    return f"29 {clip.text}"


def encode_heartbeat(now_ms: int) -> str:
    """编码保活帧（0 前缀）。

    :param now_ms: 毫秒时间戳
    :returns: 命令原文
    :raises SessionError: 参数非法
    """
    if now_ms <= 0:
        raise SessionError(f"时间戳非法：{now_ms}")
    return f"0 {now_ms}"


def _require_key(key: KeyPress) -> int:
    """校验按键并返回状态位。

    :param key: 按键描述
    :returns: 状态整数
    :raises SessionError: 按键非法
    """
    if key.code < 0 or key.code > 255:
        raise SessionError(f"键码非法：{key.code}")
    if not key.name or key.name != key.name.lower():
        raise SessionError(f"键名必须小写：{key.name}")
    state = key.modifiers.to_state()
    if state < 0 or state > 63:
        raise SessionError(f"状态位非法：{state}")
    return state
