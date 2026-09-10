"""业务 API 客户端。"""

import json
import logging

from ncg.core._paths import ApiRoutes, full_url, games_playing_path
from ncg.core.exceptions import AuthError, SessionError, TicketError
from ncg.core.http import NcgHttpClient
from ncg.models.entities import MediaServer, TicketResponse, TimeRemain, UserMe
from ncg.protocol.me import parse_me, parse_media_servers, parse_time_remain
from ncg.protocol.tickets import parse_ticket_response

logger = logging.getLogger(__name__)


class NcgApi:
    """只读与生命周期 API。

    :param http: 项目唯一的 HTTP 客户端
    """

    def __init__(self, http: NcgHttpClient) -> None:
        self._http = http

    def check_me(self) -> UserMe:
        """校验登录态（只读，不计费）。

        :returns: 当前用户信息
        :raises AuthError: 票据无效
        """
        response = self._http.get(full_url(ApiRoutes.USERS_ME))
        if response.status_code == 401:
            raise AuthError("Bearer 无效")
        if response.status_code != 200:
            raise AuthError(f"校验失败：{response.status_code}")
        return parse_me(response.content)

    def query_time_remain(self, game_code: str) -> TimeRemain | None:
        """查询剩余时长（只读，不计费）。

        :param game_code: 游戏编码
        :returns: 剩余时长结果，204 表示无变更
        :raises AuthError: 请求失败
        """
        if not game_code:
            raise AuthError("缺少游戏编码")
        params = (("game_code", game_code),)
        response = self._http.get(full_url(ApiRoutes.GAME_TIME_REMAIN), params=params)
        if response.status_code == 204:
            return None
        if response.status_code != 200:
            raise AuthError(f"查询时长失败：{response.status_code}")
        return parse_time_remain(response.content)

    def list_media_servers(self, game_code: str) -> tuple[MediaServer, ...]:
        """列出媒体节点（只读，不计费）。

        :param game_code: 游戏编码
        :returns: 节点元组
        :raises AuthError: 请求失败
        """
        if not game_code:
            raise AuthError("缺少游戏编码")
        params = (("game_code", game_code),)
        response = self._http.get(full_url(ApiRoutes.MEDIA_SERVERS), params=params)
        if response.status_code != 200:
            raise AuthError(f"查询节点失败：{response.status_code}")
        return parse_media_servers(response.content)

    def check_anti_spam(self, scene: int = 1) -> bool:
        """查询是否需要反作弊票据（只读，不计费）。

        :param scene: 场景编号，开局为 1
        :returns: 是否需要票据
        :raises AuthError: 请求失败
        """
        # 门控来自 chunk-common checkYiDun：false 时可不带 yidun_game_ticket
        # 该接口返回明文 JSON，无需混淆解码
        params = (("anti_spam_scene", str(scene)),)
        response = self._http.get(full_url(ApiRoutes.YIDUN_ANTI_SPAM_CHECK), params=params)
        if response.status_code != 200:
            raise AuthError(f"查询反作弊失败：{response.status_code}")
        try:
            raw = json.loads(response.content.decode("utf-8"))
        except Exception as exc:
            logger.exception("解析反作弊响应失败")
            raise AuthError("解析反作弊响应失败") from exc
        if not isinstance(raw, dict) or "need_anti_spam" not in raw:
            raise AuthError("反作弊响应缺少 need_anti_spam")
        need = raw["need_anti_spam"]
        if not isinstance(need, bool):
            raise AuthError("反作弊响应字段类型错误")
        return need

    def mark_playing(self, game_code: str) -> None:
        """标记开局（计费起点，调用前必须二次确认）。

        :param game_code: 游戏编码
        :raises SessionError: 标记失败
        """
        if not game_code:
            raise SessionError("缺少游戏编码")
        response = self._http.patch(full_url(games_playing_path(game_code)))
        if response.status_code != 200:
            logger.error("标记开局失败：%d", response.status_code)
            raise SessionError(f"标记开局失败：{response.status_code}")

    def mark_stopped(self, game_code: str) -> None:
        """标记结束（必须调用，否则持续计费）。

        :param game_code: 游戏编码
        :raises SessionError: 标记失败
        """
        if not game_code:
            raise SessionError("缺少游戏编码")
        response = self._http.delete(full_url(games_playing_path(game_code)))
        if response.status_code != 200:
            logger.error("标记结束失败：%d", response.status_code)
            raise SessionError(f"标记结束失败：{response.status_code}")
        logger.info("已标记结束：%s", game_code)

    def request_ticket(self, payload: bytes) -> TicketResponse:
        """申请网关票据（计费链路入口）。

        :param payload: 加密后请求体
        :returns: 票据响应摘要
        :raises TicketError: 申请失败
        """
        if not payload:
            raise TicketError("缺少票据请求载荷")
        response = self._http.post_octet(full_url(ApiRoutes.TICKETS), payload)
        if response.status_code != 200:
            logger.error("申请票据失败：%d", response.status_code)
            raise TicketError(f"申请票据失败：{response.status_code}")
        return parse_ticket_response(response.content)
