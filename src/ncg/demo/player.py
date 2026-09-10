"""pygame 最小可交互演示。"""

import asyncio
import logging
import os
import queue
import threading
import time
from typing import Any

import click
import pygame
from av.video.frame import VideoFrame

from ncg.api.client import NcgApi
from ncg.core.exceptions import NcgError, SessionError, SignalingError
from ncg.core.http import NcgHttpClient
from ncg.input.commands import (
    encode_key_tap,
    encode_mouse_down,
    encode_mouse_move,
    encode_mouse_up,
    encode_text,
)
from ncg.media.video import VideoOnlyPeer
from ncg.models.entities import (
    Credentials,
    KeyModifiers,
    KeyPress,
    MouseClick,
    MouseMove,
    PixelPoint,
    TextStroke,
    VideoSpec,
)
from ncg.protocol.tickets import build_ticket_payload, to_gateway_ticket
from ncg.session.manager import GameSession
from ncg.signaling.gateway import (
    GatewaySocket,
    build_auth_envelope,
    gateway_ping_url,
)

logger = logging.getLogger(__name__)

#: 展示窗口最大宽度，避免过大
MAX_DISPLAY_WIDTH = 960

#: 默认游戏编码
GAME_CODE = "cywlbfwt"

#: 票据候选地域
REGIONS = ("shzwh4", "shnkpl4", "sxncq4", "tgxncq", "shbtj4", "tghbtj")


def pick_display_size(game_width: int, game_height: int, max_width: int) -> tuple[int, int]:
    """计算自适应展示尺寸。

    :param game_width: 游戏宽度
    :param game_height: 游戏高度
    :param max_width: 最大展示宽度
    :returns: 展示宽高二元组
    :raises SessionError: 参数非法
    """
    # 等比缩小，保证窗口不大
    if game_width <= 0 or game_height <= 0 or max_width <= 0:
        raise SessionError("尺寸参数非法")
    if game_width <= max_width:
        return (game_width, game_height)
    height = game_height * max_width // game_width
    return (max_width, height)


def display_to_game(
    dx: int, dy: int, display_width: int, display_height: int, game_width: int, game_height: int
) -> PixelPoint:
    """展示坐标映射回游戏像素坐标。

    :param dx: 展示横坐标
    :param dy: 展示纵坐标
    :param display_width: 展示宽度
    :param display_height: 展示高度
    :param game_width: 游戏宽度
    :param game_height: 游戏高度
    :returns: 游戏像素坐标
    :raises SessionError: 参数非法
    """
    if display_width <= 0 or display_height <= 0 or game_width <= 0 or game_height <= 0:
        raise SessionError("尺寸参数非法")
    x = min(max(dx, 0), display_width) * game_width // display_width
    y = min(max(dy, 0), display_height) * game_height // display_height
    return PixelPoint(x=x, y=y)


def _plain_modifiers() -> KeyModifiers:
    """构造无修饰状态。

    :returns: 修饰状态
    """
    return KeyModifiers(
        alt=False,
        control=False,
        shift=False,
        num_lock=False,
        caps_lock=False,
        scroll_lock=False,
    )


def _key_name(event_key: int, unicode: str) -> str:
    """映射 pygame 键名为协议键名。

    :param event_key: pygame 键码
    :param unicode: 可打印字符
    :returns: 协议键名
    :raises SessionError: 无法映射
    """
    # 单字符直接小写，空格固定为 space
    if unicode == " ":
        return "space"
    if len(unicode) == 1:
        return unicode.lower()
    names = {
        pygame.K_RETURN: "enter",
        pygame.K_BACKSPACE: "backspace",
        pygame.K_UP: "arrowup",
        pygame.K_DOWN: "arrowdown",
        pygame.K_LEFT: "arrowleft",
        pygame.K_RIGHT: "arrowright",
    }
    name = names.get(event_key, "")
    if not name:
        raise SessionError(f"不支持的按键：{event_key}")
    return name


def _dom_code(event_key: int, unicode: str) -> int:
    """映射 pygame 键码为 DOM keyCode。

    :param event_key: pygame 键码
    :param unicode: 可打印字符
    :returns: DOM 键码
    :raises SessionError: 无法映射
    """
    if len(unicode) == 1:
        return ord(unicode.upper())
    codes = {
        pygame.K_RETURN: 13,
        pygame.K_BACKSPACE: 8,
        pygame.K_UP: 38,
        pygame.K_DOWN: 40,
        pygame.K_LEFT: 37,
        pygame.K_RIGHT: 39,
    }
    code = codes.get(event_key, 0)
    if code == 0:
        raise SessionError(f"不支持的按键：{event_key}")
    return code


@click.command()
@click.option("--minutes", default=3, help="最长游玩分钟数")
@click.option("--confirm-billing", is_flag=True, help="确认开始计费")
def main(minutes: int, confirm_billing: bool) -> None:
    """运行可交互演示。

    :param minutes: 最长游玩分钟数
    :param confirm_billing: 计费确认旗
    """
    if not confirm_billing:
        raise SystemExit("拒绝执行：必须显式传入 --confirm-billing 才会开始计费")
    if minutes <= 0 or minutes > 10:
        raise SystemExit("时长必须在 1-10 分钟内")
    bearer = os.environ.get("NCG_BEARER", "")
    yidun = os.environ.get("NCG_YIDUN", "")
    if not bearer or not yidun:
        raise SystemExit("缺少 NCG_BEARER 或 NCG_YIDUN")
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s][%(levelname)s][%(name)s] %(message)s",
    )
    # aiortc 起播前无关键帧是常态，解码器试错警告会刷屏，压到 ERROR
    logging.getLogger("aiortc.codecs.h264").setLevel(logging.ERROR)
    logging.getLogger("aioice.ice").setLevel(logging.WARNING)
    # 测速采样每 5 秒 3 条 INFO 刷屏，失败路径 ping_once 内部已有 warning
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        _run(bearer, yidun, minutes * 60.0)
    except NcgError as exc:
        logger.exception("演示失败")
        raise SystemExit(1) from exc


def _run(bearer: str, yidun: str, budget_s: float) -> None:
    """执行演示主流程。

    :param bearer: 票据
    :param yidun: 易盾票据
    :param budget_s: 时间预算秒
    :raises NcgError: 演示失败
    """
    frames: queue.Queue[tuple[int, int, bytes]] = queue.Queue(maxsize=2)

    def on_frame(frame: VideoFrame) -> None:
        """接收视频帧。

        :param frame: 视频帧
        """
        # 消费慢则丢旧帧，保证实时性
        payload = (frame.width, frame.height, frame.to_ndarray(format="rgb24").tobytes())
        try:
            frames.put_nowait(payload)
        except queue.Full:
            try:
                frames.get_nowait()
            except queue.Empty:
                pass
            frames.put_nowait(payload)

    with NcgHttpClient(bearer) as http:
        api = NcgApi(http)
        me = api.check_me()
        logger.info("user=%s free_left=%d", me.user_id, me.free_time_left)
        ticket_resp = api.request_ticket(build_ticket_payload(REGIONS, GAME_CODE, yidun))
        if ticket_resp.lock_detail is None:
            raise SessionError("缺少 lock_detail")
        lock = ticket_resp.lock_detail
        ticket = to_gateway_ticket(ticket_resp)
        credentials = Credentials(bearer=bearer, user_id=me.user_id)
        spec = VideoSpec(width=1920, height=1080, fps="30", quality="high", platform=0)
        gateway = GatewaySocket(ticket)
        session = GameSession(api, gateway, GAME_CODE)
        net_state: dict[str, object] = {}
        try:
            offer = gateway.connect(build_auth_envelope(credentials, ticket, spec, lock))

            def _net_main() -> None:
                # 网络线程自带事件循环，协商完成后发 answer 并通知主线程
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                peer = VideoOnlyPeer(on_frame=on_frame)
                net_state["peer"] = peer
                net_state["loop"] = loop
                try:
                    try:
                        answer = loop.run_until_complete(peer.answer_for(offer))
                        gateway.send_answer(answer)
                        net_state["ready"] = True
                        loop.run_forever()
                    except Exception:
                        logger.exception("网络线程异常退出")
                        raise
                finally:
                    loop.run_until_complete(peer.close())

            def _on_server_message(envelope: dict[str, Any]) -> None:
                """处理服务端下行，重协商 offer 则在网络循环里应答。

                :param envelope: 解码后包络
                """
                # 载入切换等场景服务端会重发 offer；不回 answer 几秒后被拆线
                op = envelope.get("op")
                if op == "close":
                    logger.warning("服务端下发 close，准备结束")
                    net_state["server_closed"] = True
                    return
                if op != "offer":
                    return
                data = envelope.get("data")
                if not isinstance(data, dict) or not data.get("sdp"):
                    return
                peer_obj = net_state.get("peer")
                loop_obj = net_state.get("loop")
                if not isinstance(peer_obj, VideoOnlyPeer) or not isinstance(
                    loop_obj, asyncio.AbstractEventLoop
                ):
                    return
                asyncio.run_coroutine_threadsafe(
                    _renegotiate(peer_obj, gateway, str(data["sdp"])), loop_obj
                )

            worker = threading.Thread(target=_net_main, name="ncg-net", daemon=True)
            worker.start()
            deadline = time.monotonic() + 30.0
            while "ready" not in net_state and time.monotonic() < deadline:
                time.sleep(0.2)
            if "ready" not in net_state:
                raise SessionError("视频协商超时")
            gateway.start_keepalive()
            gateway.start_reader(_on_server_message)
            session.mark_started()
            peer = net_state.get("peer")
            loop_obj = net_state.get("loop")
            if not isinstance(peer, VideoOnlyPeer) or not isinstance(
                loop_obj, asyncio.AbstractEventLoop
            ):
                raise SessionError("网络线程未就绪")
            _pump_pygame(
                frames, gateway, peer, loop_obj, http,
                gateway_ping_url(ticket.gateway_url),
                lock.width, lock.height, budget_s, net_state,
            )
        finally:
            loop_obj = net_state.get("loop")
            if isinstance(loop_obj, asyncio.AbstractEventLoop):
                try:
                    loop_obj.call_soon_threadsafe(loop_obj.stop)
                except RuntimeError:
                    pass
            try:
                session.stop()
            except SessionError:
                logger.exception("结束失败，重试一次")
                api.mark_stopped(GAME_CODE)


async def _renegotiate(peer: VideoOnlyPeer, gateway: GatewaySocket, sdp: str) -> None:
    """应答服务端重协商。

    :param peer: 视频端点
    :param gateway: 网关套接字
    :param sdp: 新 offer 的 SDP
    """
    # 复用同一 PC，失败仅记日志，不掀桌
    try:
        answer = await peer.answer_for(sdp)
        gateway.send_answer(answer)
        logger.info("已应答重协商")
    except Exception:
        logger.exception("重协商应答失败")


def _pump_pygame(
    frames: queue.Queue[tuple[int, int, bytes]],
    gateway: GatewaySocket,
    peer: VideoOnlyPeer,
    net_loop: asyncio.AbstractEventLoop,
    http: NcgHttpClient,
    ping_url: str,
    game_width: int,
    game_height: int,
    budget_s: float,
    net_state: dict[str, object],
) -> None:
    """运行 pygame 主循环。

    :param frames: 帧队列
    :param gateway: 网关套接字
    :param peer: 视频端点，用于采集统计
    :param net_loop: 网络线程事件循环
    :param http: HTTP 客户端，用于网关测速
    :param ping_url: 网关测速地址
    :param game_width: 游戏宽度
    :param game_height: 游戏高度
    :param budget_s: 时间预算秒
    :param net_state: 网络共享状态，含服务端 close 标记
    :raises SessionError: 演示失败
    """
    display_width, display_height = pick_display_size(game_width, game_height, MAX_DISPLAY_WIDTH)
    screen = pygame.display.set_mode((display_width, display_height))
    pygame.display.set_caption("netease-cloud-game demo（ESC 退出）")
    clock = pygame.time.Clock()
    deadline = time.monotonic() + budget_s
    delay_state: dict[str, float | None] = {"delay_ms": None}
    sampler = threading.Thread(
        target=_sample_delay, args=(http, ping_url, delay_state), name="ncg-delay", daemon=True
    )
    sampler.start()
    next_stats_at = 0.0
    mouse_down = False
    running = True
    reason = "timeout"

    def _send(cmd: str) -> bool:
        """发送单条指令，断线返回假。

        :param cmd: 输入命令原文
        :returns: 发送是否成功
        """
        # 连接已死时不断言、不抛，调用方结束主循环走正常止损
        try:
            gateway.send_input(cmd)
        except SignalingError:
            logger.warning("连接已断开，结束演示")
            return False
        return True

    while running and time.monotonic() < deadline:
        if time.monotonic() >= next_stats_at:
            next_stats_at = time.monotonic() + 2.0
            _refresh_caption(peer, net_loop, gateway, delay_state.get("delay_ms"))
        if net_state.get("server_closed"):
            reason = "server closed"
            running = False
            break
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                reason = "user quit"
                running = False
            elif event.type == pygame.MOUSEMOTION and mouse_down:
                point = display_to_game(
                    event.pos[0], event.pos[1], display_width, display_height,
                    game_width, game_height,
                )
                if not _send(encode_mouse_move(MouseMove(point=point))):
                    reason = "disconnected"
                    running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse_down = True
                point = display_to_game(
                    event.pos[0], event.pos[1], display_width, display_height,
                    game_width, game_height,
                )
                if not _send(encode_mouse_down(MouseMove(point=point))):
                    reason = "disconnected"
                    running = False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                mouse_down = False
                point = display_to_game(
                    event.pos[0], event.pos[1], display_width, display_height,
                    game_width, game_height,
                )
                if not _send(encode_mouse_up(MouseClick(point=point))):
                    reason = "disconnected"
                    running = False
            elif event.type == pygame.KEYDOWN and (
                event.key == pygame.K_ESCAPE or not _send_key(gateway, event.key, event.unicode)
            ):
                reason = "user quit" if event.key == pygame.K_ESCAPE else "disconnected"
                running = False
        try:
            width, height, raw = frames.get_nowait()
            surface = pygame.image.frombuffer(raw, (width, height), "RGB")
            scaled = pygame.transform.scale(surface, (display_width, display_height))
            screen.blit(scaled, (0, 0))
            pygame.display.flip()
        except queue.Empty:
            pass
        clock.tick(30)
    logger.info("演示结束：%s", reason)
    pygame.quit()


def _sample_delay(
    http: NcgHttpClient, ping_url: str, state: dict[str, float | None]
) -> None:
    """后台循环采样网关延迟。

    :param http: HTTP 客户端
    :param ping_url: 网关测速地址
    :param state: 共享状态，写入 delay_ms
    """
    # 与网页 getDelay 一致：多采样均值；常驻后台，不阻塞渲染
    while True:
        samples = [
            sample
            for _ in range(3)
            if (sample := http.ping_once(ping_url, timeout_s=1.0)) is not None
        ]
        state["delay_ms"] = sum(samples) / len(samples) if samples else None
        time.sleep(5.0)


def _refresh_caption(
    peer: VideoOnlyPeer,
    net_loop: asyncio.AbstractEventLoop,
    gateway: GatewaySocket,
    delay_ms: float | None,
) -> None:
    """刷新标题栏延迟信息。

    :param peer: 视频端点
    :param net_loop: 网络线程事件循环
    :param gateway: 网关套接字，提供保活回显 RTT
    :param delay_ms: 网关测速延迟毫秒，兜底用
    """
    # 保活回显是同通道真往返，优先于测速采样
    effective = gateway.last_echo_rtt_ms if gateway.last_echo_rtt_ms is not None else delay_ms
    # 跨线程取数，失败则保留旧标题
    try:
        future = asyncio.run_coroutine_threadsafe(peer.collect_stats(effective), net_loop)
        stats = future.result(timeout=5.0)
    except Exception:
        logger.exception("采集延迟信息失败")
        return
    delay_text = f"{stats.delay_ms:.0f}ms" if stats.delay_ms is not None else "--"
    pygame.display.set_caption(
        f"delay={delay_text} loss={stats.loss_percent:.1f}% "
        f"fps={stats.fps:.0f}（ESC 退出）"
    )


def _send_key(gateway: GatewaySocket, event_key: int, unicode: str) -> bool:
    """处理单次按键，断线返回假。

    :param gateway: 网关套接字
    :param event_key: pygame 键码
    :param unicode: 可打印字符
    :returns: 发送是否成功
    """
    # 可打印单字走文本通道，其余走 PC 键盘通道
    try:
        if len(unicode) == 1 and unicode.isprintable():
            gateway.send_input(encode_text(TextStroke(char=unicode)))
            return True
        name = _key_name(event_key, unicode)
        code = _dom_code(event_key, unicode)
        key = KeyPress(code=code, name=name, modifiers=_plain_modifiers())
        down, sleep, up = encode_key_tap(key)
        gateway.send_input(down)
        gateway.send_input(sleep)
        gateway.send_input(up)
    except (SessionError, SignalingError):
        logger.warning("连接已断开，结束演示")
        return False
    return True
