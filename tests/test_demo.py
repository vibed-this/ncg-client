"""演示坐标换算测试。"""

import pytest

from ncg.core.exceptions import SessionError
from ncg.demo.player import display_to_game, pick_display_size


def test_pick_display_size_caps_width() -> None:
    """大窗口应等比缩小。"""
    assert pick_display_size(1920, 1080, 960) == (960, 540)


def test_pick_display_size_keeps_small() -> None:
    """小窗口应保持原尺寸。"""
    assert pick_display_size(800, 600, 960) == (800, 600)


def test_display_to_game_roundtrip() -> None:
    """展示中心应映射回游戏中心。"""
    point = display_to_game(480, 270, 960, 540, 1920, 1080)
    assert (point.x, point.y) == (960, 540)


def test_display_to_game_clamps() -> None:
    """越界坐标应钳制。"""
    point = display_to_game(-10, 9999, 960, 540, 1920, 1080)
    assert (point.x, point.y) == (0, 1080)


def test_rejects_bad_sizes() -> None:
    """非法尺寸应 fast-fail。"""
    with pytest.raises(SessionError):
        pick_display_size(0, 1080, 960)
    with pytest.raises(SessionError):
        display_to_game(1, 1, 0, 540, 1920, 1080)
