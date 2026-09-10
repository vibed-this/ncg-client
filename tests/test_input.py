"""输入编码测试。"""

import pytest

from ncg.core.exceptions import SessionError
from ncg.input.commands import (
    encode_clipboard_pc,
    encode_ctrl_v,
    encode_heartbeat,
    encode_key_down,
    encode_key_tap,
    encode_key_up,
    encode_mobile_key,
    encode_mouse_down,
    encode_mouse_move,
    encode_mouse_up,
    encode_sleep_pc,
    encode_text,
)
from ncg.models.entities import (
    ClipboardText,
    KeyModifiers,
    KeyPress,
    MobileKey,
    MouseClick,
    MouseMove,
    PixelPoint,
    TextStroke,
)


def test_mouse_click_bracketing() -> None:
    """点击应为 1/3 包夹。"""
    assert encode_mouse_down(MouseMove(point=PixelPoint(x=941, y=539))) == "1 941 539 0"
    assert encode_mouse_up(MouseClick(point=PixelPoint(x=941, y=539))) == "3 941 539 0"


def test_mouse_move() -> None:
    """移动应为 2 前缀。"""
    assert encode_mouse_move(MouseMove(point=PixelPoint(x=824, y=686))) == "2 824 686 0"


def test_text_must_be_single_char() -> None:
    """文本必须单字发送。"""
    assert encode_text(TextStroke(char="测")) == "5 测"
    with pytest.raises(SessionError):
        encode_text(TextStroke(char="两个字"))


def _plain_modifiers() -> KeyModifiers:
    """构造无修饰状态。"""
    return KeyModifiers(
        alt=False,
        control=False,
        shift=False,
        num_lock=False,
        caps_lock=False,
        scroll_lock=False,
    )


def test_key_down_up_pair() -> None:
    """回车按下抬起应成对。"""
    key = KeyPress(code=13, name="enter", modifiers=_plain_modifiers())
    assert encode_key_down(key) == "104 13 enter 0"
    assert encode_key_up(key) == "105 13 enter 0"


def test_key_modifiers_state() -> None:
    """Control 修饰应为位 2。"""
    modifiers = KeyModifiers(
        alt=False,
        control=True,
        shift=False,
        num_lock=False,
        caps_lock=False,
        scroll_lock=False,
    )
    assert modifiers.to_state() == 2
    key = KeyPress(code=86, name="v", modifiers=modifiers)
    assert encode_key_down(key) == "104 86 v 2"


def test_key_tap_returns_triplet() -> None:
    """点按应返回按下等待抬起三元组。"""
    key = KeyPress(code=13, name="enter", modifiers=_plain_modifiers())
    down, sleep, up = encode_key_tap(key)
    assert down == "104 13 enter 0"
    assert sleep == "133 16"
    assert up == "105 13 enter 0"


def test_ctrl_v_sequence_length() -> None:
    """粘贴序列应为 8 条。"""
    assert len(encode_ctrl_v()) == 8


def test_mobile_key_rejects_unknown() -> None:
    """移动按键非法值应 fast-fail。"""
    assert encode_mobile_key(MobileKey(code=2)) == "6 2"
    with pytest.raises(SessionError):
        encode_mobile_key(MobileKey(code=5))


def test_clipboard_and_sleep_and_heartbeat() -> None:
    """剪贴板等待保活应符合前缀。"""
    assert encode_clipboard_pc(ClipboardText(text="hi")).startswith("138 ")
    assert encode_sleep_pc(16) == "133 16"
    assert encode_heartbeat(1789038721000) == "0 1789038721000"
