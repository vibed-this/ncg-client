"""会话生命周期。"""

import logging
import time
from collections.abc import Callable

from ncg.api.client import NcgApi
from ncg.core.exceptions import SessionError
from ncg.models.entities import TicketResponse
from ncg.signaling.gateway import GatewaySocket

logger = logging.getLogger(__name__)


class GameSession:
    """单局游戏会话。

    :param api: 业务 API
    :param gateway: 网关套接字
    :param game_code: 游戏编码
    """

    def __init__(self, api: NcgApi, gateway: GatewaySocket, game_code: str) -> None:
        if not game_code:
            raise SessionError("缺少游戏编码")
        self._api = api
        self._gateway = gateway
        self._game_code = game_code
        self._playing = False

    @property
    def playing(self) -> bool:
        """是否已标记开局。

        :returns: 是否计费中
        """
        return self._playing

    def mark_started(self) -> None:
        """标记开局。

        :raises SessionError: 标记失败
        """
        self._api.mark_playing(self._game_code)
        self._playing = True
        logger.info("会话已开始：%s", self._game_code)

    def stop(self) -> None:
        """结束会话（幂等，必须调用以止损）。

        :raises SessionError: 结束失败
        """
        # 先关媒体再调 HTTP，确保任何分支都不漏计费标记
        try:
            self._gateway.close()
        except Exception:
            logger.exception("关闭网关失败")
        try:
            self._api.mark_stopped(self._game_code)
        except Exception as exc:
            logger.exception("标记结束失败")
            raise SessionError("标记结束失败") from exc
        finally:
            self._playing = False
        logger.info("会话已结束：%s", self._game_code)

    def wait_for_queue(
        self,
        ticket: TicketResponse,
        poll_push: Callable[[], str],
        timeout_s: float = 120.0,
    ) -> None:
        """等待排队进入 running。

        :param ticket: 票据响应摘要
        :param poll_push: 推送状态轮询函数
        :param timeout_s: 超时秒
        :raises SessionError: 超时或参数非法
        """
        # queue_len 为 0 直接返回；否则按 queue_time 退避等待 starting/running
        if timeout_s <= 0:
            raise SessionError("等待超时参数非法")
        queue_len = ticket.non_vip_queue_len + ticket.vip_queue_len
        if queue_len <= 0:
            return
        wait_s = max(ticket.non_vip_queue_time, ticket.vip_queue_time, 1)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status = poll_push()
            if status in ("starting", "running"):
                logger.info("排队进入：%s", status)
                return
            time.sleep(wait_s)
        logger.error("排队等待超时")
        raise SessionError("排队等待超时")

    def on_push_status(self, status: str) -> None:
        """处理推送状态变更。

        :param status: 推送状态
        :raises SessionError: 状态非法
        """
        # exiting 意味着服务端正在结束，按顶号/被动结束做幂等止损
        if status not in ("starting", "running", "exiting"):
            raise SessionError(f"未知推送状态：{status}")
        logger.info("推送状态：%s", status)
        if status == "exiting":
            self.handle_kicked(status, None)

    def on_wss_close(self, code: int) -> None:
        """处理网关关闭。

        :param code: 关闭码，0 为有序关闭
        """
        if code != 0:
            logger.warning("网关异常关闭：%d", code)
            self.handle_kicked("abnormal", code)
        else:
            logger.info("网关有序关闭")

    def handle_kicked(self, status: str, wss_code: int | None) -> None:
        """处理被顶号或被动结束。

        :param status: 状态描述
        :param wss_code: 网关关闭码
        """
        # 顶号确切码未知，按任何被动结束做幂等止损，不抛异常
        logger.warning("被动结束 status=%s code=%s，执行止损", status, wss_code)
        try:
            self.stop()
        except SessionError:
            logger.exception("止损失败")
