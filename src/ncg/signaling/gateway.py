"""网关 WSS 信令。"""

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import attrs
import cattrs
import websockets.sync.client as ws_sync
from websockets.exceptions import ConnectionClosed
from websockets.typing import Origin

from ncg.core._paths import ApiHosts
from ncg.core.exceptions import SignalingError
from ncg.models.entities import Credentials, GatewayTicket, LockDetail, VideoSpec
from ncg.protocol.crypto import brute_force_decode, offset_encode

logger = logging.getLogger(__name__)


@attrs.frozen
class AuthFrame:
    """鉴权帧载荷。"""

    user_id: str  # 用户标识
    token: str  # JWT
    game_code: str  # 游戏编码
    w: int  # 宽度
    h: int  # 高度
    quality: str  # 档位
    fps: str  # 帧率
    platform: int  # 平台


@attrs.frozen
class SignalEnvelope:
    """信令包络。"""

    id: str  # 毫秒时间戳
    op: str  # 操作码
    data: AuthFrame | str  # 载荷


def build_auth_envelope(
    credentials: Credentials,
    ticket: GatewayTicket,
    spec: VideoSpec,
    lock: LockDetail | None,
) -> str:
    """构造鉴权帧明文。

    :param credentials: 用户凭证
    :param ticket: 网关票据
    :param spec: 视频规格
    :param lock: 锁定节点详情，移动端时宽高取锁定值
    :returns: JSON 明文
    :raises SignalingError: 缺少锁定详情
    """
    # 首包必须明文发送，后续帧才走混淆；移动端 w/h 取 lock_detail
    if lock is None:
        raise SignalingError("缺少锁定节点详情")
    frame = AuthFrame(
        user_id=credentials.user_id,
        token=credentials.bearer,
        game_code=ticket.game_code,
        w=lock.width,
        h=lock.height,
        quality=spec.quality,
        fps=spec.fps,
        platform=spec.platform,
    )
    envelope = SignalEnvelope(id=str(int(time.time() * 1000)), op="auth", data=frame)
    return json.dumps(cattrs.unstructure(envelope))


def gateway_ping_url(gateway_url: str) -> str:
    """由 WSS 网关地址推导测速地址。

    :param gateway_url: WSS 地址，如 wss://gw-lt-shzwh-02.cg.163.com:6443/ws
    :returns: HTTPS 测速地址，如 https://gw-lt-shzwh-02.cg.163.com:6443/ping
    :raises SignalingError: 地址非法
    """
    # 测速与 WSS 同 host 同端口，仅换协议与路径，与网页 ping.html 一致
    if not gateway_url.startswith("wss://"):
        raise SignalingError(f"网关地址非法：{gateway_url}")
    rest = gateway_url[len("wss://"):]
    host = rest.split("/", 1)[0]
    if not host:
        raise SignalingError(f"网关地址非法：{gateway_url}")
    return f"https://{host}/ping"


class GatewaySocket:
    """游戏网关套接字。

    :param ticket: 网关票据
    """

    def __init__(self, ticket: GatewayTicket) -> None:
        if not ticket.gateway_url.startswith("wss://"):
            raise SignalingError("网关地址非法")
        self._ticket = ticket
        self._socket: ws_sync.ClientConnection | None = None
        self._offset = 24
        self._keepalive_stop: threading.Event | None = None
        self._keepalive_thread: threading.Thread | None = None
        self._reader_stop: threading.Event | None = None
        self._reader_thread: threading.Thread | None = None
        self._last_keepalive_ts: str | None = None
        self.last_echo_rtt_ms: float | None = None

    def connect(self, auth_json: str) -> str:
        """连接并鉴权，返回 offer 明文。

        :param auth_json: 鉴权帧明文
        :returns: offer 的 SDP 明文
        :raises SignalingError: 信令失败
        """
        if not auth_json:
            raise SignalingError("缺少鉴权帧")
        try:
            # 网关不回 WS 协议 pong，库默认 20s 保活会误杀长会话；保活只走应用层 0 now
            socket = ws_sync.connect(
                self._ticket.gateway_url,
                origin=Origin(ApiHosts.ORIGIN),
                ping_interval=None,
                ping_timeout=None,
            )
            self._socket = socket
            socket.send(auth_json)
            logger.info("已发送鉴权帧")
            raw = socket.recv(timeout=15)
            if isinstance(raw, bytes):
                raise SignalingError("网关返回了二进制首包")
            text = self._decode_frame(raw)
            envelope = json.loads(text)
            if not isinstance(envelope, dict) or envelope.get("op") != "offer":
                raise SignalingError("首包不是 offer")
            data = envelope.get("data")
            if not isinstance(data, dict) or "sdp" not in data:
                raise SignalingError("offer 缺少 sdp")
            sdp = data["sdp"]
            if not isinstance(sdp, str) or not sdp:
                raise SignalingError("offer 缺少 sdp")
            return sdp
        except SignalingError:
            raise
        except Exception as exc:
            logger.exception("网关连接失败")
            raise SignalingError("网关连接失败") from exc

    def send_input(self, cmd: str) -> None:
        """发送操控指令。

        :param cmd: 输入命令原文
        :raises SignalingError: 发送失败
        """
        socket = self._require_socket()
        if not cmd:
            raise SignalingError("缺少输入命令")
        payload = json.dumps({"id": str(int(time.time() * 1000)), "op": "input", "data": {"cmd": cmd}})
        try:
            socket.send(offset_encode(self._offset, payload).decode("ascii"))
        except Exception as exc:
            logger.exception("发送输入失败")
            raise SignalingError("发送输入失败") from exc

    def send_answer(self, sdp: str) -> None:
        """发送 answer。

        :param sdp: 本地 SDP
        :raises SignalingError: 发送失败
        """
        socket = self._require_socket()
        if not sdp:
            raise SignalingError("缺少 answer SDP")
        payload = json.dumps({"id": str(int(time.time() * 1000)), "op": "answer", "data": {"sdp": sdp}})
        try:
            socket.send(offset_encode(self._offset, payload).decode("ascii"))
            logger.info("已发送 answer")
        except Exception as exc:
            logger.exception("发送 answer 失败")
            raise SignalingError("发送 answer 失败") from exc

    def close(self) -> None:
        """关闭连接。"""
        self.stop_keepalive()
        self.stop_reader()
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                logger.exception("关闭网关连接失败")
            finally:
                self._socket = None

    def send_keepalive(self) -> str:
        """发送保活帧。

        :returns: 保活标识
        :raises SignalingError: 发送失败
        """
        # HAR #525 实证：send {"op":"input","cmd":"0 {now}"} 后回同样 cmd
        now = str(int(time.time() * 1000))
        self.send_input("0 " + now)
        self._last_keepalive_ts = now
        return now

    def start_reader(self, on_message: Callable[[dict[str, Any]], None]) -> threading.Thread:
        """启动下行读取线程。

        :param on_message: 消息回调，参数为解码后包络
        :returns: 读取线程
        :raises SignalingError: 已在运行
        """
        # 连接后只读一次 offer 是盲区：重协商、kick、close 全走下行
        if self._reader_thread is not None and self._reader_thread.is_alive():
            raise SignalingError("读取已在运行")
        socket = self._require_socket()
        self._reader_stop = threading.Event()
        stop_event = self._reader_stop

        def _loop() -> None:
            while not stop_event.is_set():
                try:
                    raw = socket.recv(timeout=1.0)
                except TimeoutError:
                    continue
                except (ConnectionClosed, OSError):
                    logger.warning("下行通道已断开")
                    return
                if isinstance(raw, bytes):
                    logger.warning("收到二进制下行帧，已忽略")
                    continue
                try:
                    envelope = json.loads(self._decode_frame(raw))
                except Exception:
                    logger.exception("下行解码失败")
                    continue
                if not isinstance(envelope, dict):
                    continue
                logger.info("收到下行 %s", self._summarize(envelope))
                self._match_echo(envelope)
                try:
                    on_message(envelope)
                except Exception:
                    logger.exception("下行回调失败")

        thread = threading.Thread(target=_loop, name="ncg-reader", daemon=True)
        self._reader_thread = thread
        thread.start()
        return thread

    def stop_reader(self) -> None:
        """停止下行读取线程。"""
        if self._reader_stop is not None:
            self._reader_stop.set()
            self._reader_stop = None
        self._reader_thread = None

    @staticmethod
    def _summarize(envelope: dict[str, Any]) -> str:
        """压缩下行包络为单行摘要。

        :param envelope: 解码后包络
        :returns: 摘要字符串
        """
        op = envelope.get("op")
        data = envelope.get("data")
        if isinstance(data, dict):
            if "cmd" in data:
                return f"op={op} cmd={data['cmd']}"[:80]
            if "sdp" in data:
                return f"op={op} sdp_len={len(data['sdp'])}"
            return f"op={op} keys={','.join(sorted(data.keys()))}"[:80]
        return f"op={op} data={data}"[:80]

    def _match_echo(self, envelope: dict[str, Any]) -> None:
        """配对保活回显并记录 RTT。

        :param envelope: 解码后包络
        """
        # 服务端原样回显 0 {ts}，配对即得应用层往返延迟
        data = envelope.get("data")
        if not isinstance(data, dict):
            return
        cmd = data.get("cmd")
        if not isinstance(cmd, str) or not cmd.startswith("0 "):
            return
        echoed = cmd[2:]
        if echoed != self._last_keepalive_ts:
            return
        try:
            rtt = int(time.time() * 1000) - int(echoed)
        except ValueError:
            return
        self.last_echo_rtt_ms = float(rtt)
        logger.info("保活回显 rtt=%dms", rtt)


    def start_keepalive(
        self,
        interval_s: float = 3.0,
        timeout_s: float = 2.0,
        max_misses: int = 3,
        on_miss: Callable[[int], None] | None = None,
    ) -> threading.Thread:
        """启动保活线程。

        :param interval_s: 发送间隔秒
        :param timeout_s: 单次等待秒（保留参数，同步套接字不阻塞收包）
        :param max_misses: 最大连续失败次数
        :param on_miss: 失败回调，参数为连续失败次数
        :returns: 保活线程
        :raises SignalingError: 参数非法或已在运行
        """
        if interval_s <= 0 or timeout_s <= 0 or max_misses <= 0:
            raise SignalingError("保活参数非法")
        if self._keepalive_thread is not None and self._keepalive_thread.is_alive():
            raise SignalingError("保活已在运行")
        self._keepalive_stop = threading.Event()
        stop_event = self._keepalive_stop
        misses = 0

        def _loop() -> None:
            # 失败计数由发送异常驱动，超时回包判定留待后续版本
            nonlocal misses
            while not stop_event.wait(interval_s):
                try:
                    self.send_keepalive()
                    misses = 0
                except SignalingError:
                    misses += 1
                    logger.warning("保活失败 %d 次", misses)
                    if on_miss is not None:
                        on_miss(misses)
                    if misses >= max_misses:
                        logger.error("保活连续失败，退出线程")
                        return

        thread = threading.Thread(target=_loop, name="ncg-keepalive", daemon=True)
        self._keepalive_thread = thread
        thread.start()
        return thread

    def stop_keepalive(self) -> None:
        """停止保活线程。"""
        if self._keepalive_stop is not None:
            self._keepalive_stop.set()
            self._keepalive_stop = None
        self._keepalive_thread = None

    def _decode_frame(self, raw: str) -> str:
        """解码网关帧。

        :param raw: 原始帧
        :returns: 明文 JSON
        :raises SignalingError: 解码失败
        """
        # 首包可能是明文 offer，也可能是混淆包
        stripped = raw.strip()
        if stripped.startswith("{"):
            return stripped
        if stripped.startswith('"') and stripped.endswith('"'):
            stripped = json.loads(stripped)
        try:
            return brute_force_decode(stripped.encode("ascii"))
        except Exception as exc:
            logger.exception("解码网关帧失败")
            raise SignalingError("解码网关帧失败") from exc

    def _require_socket(self) -> ws_sync.ClientConnection:
        """获取已连接套接字。

        :returns: 套接字
        :raises SignalingError: 尚未连接
        """
        if self._socket is None:
            raise SignalingError("网关尚未连接")
        return self._socket
