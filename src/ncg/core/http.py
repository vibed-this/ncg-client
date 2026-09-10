"""项目唯一的 HTTP 请求体系。"""

import logging
import time
from types import TracebackType
from typing import Self
from urllib.parse import urlencode

import httpx

from ncg.core._paths import ApiHosts
from ncg.core.exceptions import AuthError

logger = logging.getLogger(__name__)


class NcgHttpClient:
    """网易云游戏 HTTP 客户端。

    :param bearer: 用户 Bearer 票据
    """

    def __init__(self, bearer: str) -> None:
        if not bearer:
            raise AuthError("缺少 Bearer 票据")
        self._bearer: str = bearer
        self._client: httpx.Client | None = None

    def open(self) -> Self:
        """打开底层连接。

        :returns: 自身
        """
        # 固定请求头收敛在此一处，避免散落
        self._client = httpx.Client(
            headers=httpx.Headers(
                {
                    "Origin": ApiHosts.ORIGIN,
                    "Referer": ApiHosts.ORIGIN + "/",
                    "X-Platform": "0",
                    "Authorization": "Bearer " + self._bearer,
                }
            ),
            timeout=15.0,
        )
        return self

    def close(self) -> None:
        """关闭底层连接。"""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> Self:
        return self.open()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def get(self, url: str, params: tuple[tuple[str, str], ...] | None = None) -> httpx.Response:
        """发送 GET 请求。

        :param url: 完整 URL
        :param params: 查询参数元组
        :returns: 响应
        :raises AuthError: 客户端未打开
        """
        client = self._require_client()
        # httpx 对 list 泛型不变，改用 urlencode 拼查询串以通过 strict 类型检查
        target = url if params is None else url + "?" + urlencode(params)
        response = client.get(target)
        logger.debug("GET %s -> %s len=%d", url, response.status_code, len(response.content))
        return response

    def post_octet(self, url: str, payload: bytes) -> httpx.Response:
        """发送二进制 POST 请求。

        :param url: 完整 URL
        :param payload: 加密后载荷
        :returns: 响应
        :raises AuthError: 客户端未打开
        """
        client = self._require_client()
        response = client.post(
            url, content=payload, headers=httpx.Headers({"Content-Type": "application/octet-stream"})
        )
        logger.debug("POST %s -> %s len=%d", url, response.status_code, len(response.content))
        return response

    def patch(self, url: str) -> httpx.Response:
        """发送 PATCH 请求。

        :param url: 完整 URL
        :returns: 响应
        :raises AuthError: 客户端未打开
        """
        client = self._require_client()
        response = client.patch(url)
        logger.debug("PATCH %s -> %s", url, response.status_code)
        return response

    def delete(self, url: str) -> httpx.Response:
        """发送 DELETE 请求。

        :param url: 完整 URL
        :returns: 响应
        :raises AuthError: 客户端未打开
        """
        client = self._require_client()
        response = client.delete(url)
        logger.debug("DELETE %s -> %s", url, response.status_code)
        return response

    def ping_once(self, url: str, timeout_s: float = 1.5) -> float | None:
        """单次测速（短超时，失败返回空）。

        :param url: 测速地址
        :param timeout_s: 超时秒
        :returns: 延迟毫秒，失败为空
        :raises AuthError: 参数非法
        """
        # 测速突发与保活无关，失败隔离并切换下一 host
        if not url or timeout_s <= 0:
            raise AuthError("测速参数非法")
        client = self._require_client()
        start = time.perf_counter()
        try:
            response = client.get(url, params=httpx.QueryParams({"t": str(int(start * 1000))}))
            if response.status_code != 200:
                logger.warning("测速失败 %s -> %d", url, response.status_code)
                return None
            return (time.perf_counter() - start) * 1000.0
        except httpx.HTTPError:
            logger.warning("测速异常 %s", url)
            return None

    def _require_client(self) -> httpx.Client:
        """获取已打开的客户端。

        :returns: 底层客户端
        :raises AuthError: 尚未打开
        """
        if self._client is None:
            raise AuthError("HTTP 客户端尚未打开")
        return self._client
