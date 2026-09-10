"""路径集中管理测试。"""

from ncg.core._paths import full_url, games_playing_path


def test_games_playing_path_centralized() -> None:
    """进行中路径应唯一拼接。"""
    path = games_playing_path("cywlbfwt")
    assert path == "/api/v2/users/@me/games-playing/cywlbfwt"
    assert full_url(path) == "https://n.cg.163.com" + path
