"""集中管理固定域名与 API 路径。"""


class ApiHosts:
    """网关域名常量。"""

    BASE: str = "https://n.cg.163.com"
    ORIGIN: str = "https://cg.163.com"


class ApiRoutes:
    """API 路由模板。"""

    USERS_ME: str = "/api/v2/users/@me"
    GAME_TIME_REMAIN: str = "/api/v2/game_time_remain"
    MEDIA_SERVERS: str = "/api/v2/media-servers"
    TICKETS: str = "/api/v2/tickets"
    NETWORK_TESTS: str = "/api/v2/network-tests"
    GAMES_PLAYING: str = "/api/v2/users/@me/games-playing/{game_code}"
    YIDUN_ANTI_SPAM_CHECK: str = "/api/v1/yidun/anti_spam_check"


def games_playing_path(game_code: str) -> str:
    """拼接进行中游戏路径。

    :param game_code: 游戏编码
    :returns: 完整 API 路径
    """
    # 路径模板来自 ApiRoutes，保持此处唯一拼接点
    return ApiRoutes.GAMES_PLAYING.format(game_code=game_code)


def full_url(path: str) -> str:
    """拼接完整 URL。

    :param path: API 路径
    :returns: 完整 URL
    """
    return ApiHosts.BASE + path
