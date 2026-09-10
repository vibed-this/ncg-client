"""命令行入口。"""

import asyncio
import logging
import os

import click

from ncg.api.client import NcgApi
from ncg.core.exceptions import NcgError
from ncg.core.http import NcgHttpClient
from ncg.input.commands import encode_key_tap, encode_mouse_up, encode_text
from ncg.media.video import VideoOnlyPeer
from ncg.models.entities import (
    Credentials,
    GatewayTicket,
    KeyModifiers,
    KeyPress,
    LockDetail,
    MouseClick,
    PixelPoint,
    TextStroke,
    VideoSpec,
)
from ncg.session.manager import GameSession
from ncg.signaling.gateway import GatewaySocket, build_auth_envelope

logger = logging.getLogger(__name__)


def _read_bearer(explicit: str) -> str:
    """读取 Bearer 票据。

    :param explicit: 命令行传入值
    :returns: 票据原文
    :raises NcgError: 缺少票据
    """
    # 优先级：显式参数高于环境变量，避免票据落盘
    token = explicit or os.environ.get("NCG_BEARER", "")
    if not token:
        raise NcgError("缺少 Bearer，请传参或设置 NCG_BEARER")
    return token


@click.group()
def main() -> None:
    """网易云游戏三方客户端。"""
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s][%(levelname)s][%(name)s] %(message)s",
    )


@main.command()
@click.option("--bearer", default="", help="Bearer 票据")
@click.option("--game-code", default="cywlbfwt", help="游戏编码")
def check(bearer: str, game_code: str) -> None:
    """只读校验（不计费）。

    :param bearer: 票据
    :param game_code: 游戏编码
    """
    token = _read_bearer(bearer)
    try:
        with NcgHttpClient(token) as http:
            api = NcgApi(http)
            me = api.check_me()
            remain = api.query_time_remain(game_code)
            servers = api.list_media_servers(game_code)
            need = api.check_anti_spam(1)
            logger.info(
                "校验通过 user=%s free_left=%d coins=%d remain=%s servers=%d need_spam=%s",
                me.user_id,
                me.free_time_left,
                me.coins,
                remain,
                len(servers),
                need,
            )
    except NcgError as exc:
        logger.exception("校验失败")
        raise SystemExit(1) from exc


@main.command()
@click.option("--bearer", default="", help="Bearer 票据")
@click.option("--user-id", default="", help="用户标识，为空则自动填充")
@click.option("--gateway-url", required=True, help="票据中的网关地址")
@click.option("--region", default="shzwh4", help="地域")
@click.option("--game-code", default="cywlbfwt", help="游戏编码")
@click.option("--lock-width", default=1920, help="锁定宽度")
@click.option("--lock-height", default=1080, help="锁定高度")
@click.option("--confirm-billing", is_flag=True, help="确认开始计费")
def start(
    bearer: str,
    user_id: str,
    gateway_url: str,
    region: str,
    game_code: str,
    lock_width: int,
    lock_height: int,
    confirm_billing: bool,
) -> None:
    """启动一局（计费，需二次确认）。

    :param bearer: 票据
    :param user_id: 用户标识
    :param gateway_url: 网关地址
    :param region: 地域
    :param game_code: 游戏编码
    :param lock_width: 锁定宽度
    :param lock_height: 锁定高度
    :param confirm_billing: 计费确认旗
    """
    if not confirm_billing:
        raise SystemExit("拒绝执行：必须显式传入 --confirm-billing 才会开始计费")
    token = _read_bearer(bearer)
    ticket = GatewayTicket(gateway_url=gateway_url, region=region, game_code=game_code)
    spec = VideoSpec(width=1920, height=1080, fps="30", quality="high", platform=0)
    lock = LockDetail(region=region, width=lock_width, height=lock_height, ip="", port=0)
    gateway = GatewaySocket(ticket)
    try:
        with NcgHttpClient(token) as http:
            api = NcgApi(http)
            resolved_user = user_id or api.check_me().user_id
            credentials = Credentials(bearer=token, user_id=resolved_user)
            session = GameSession(api, gateway, game_code)
            offer = gateway.connect(build_auth_envelope(credentials, ticket, spec, lock))

            async def _run() -> None:
                peer = VideoOnlyPeer()
                try:
                    answer = await peer.answer_for(offer)
                    gateway.send_answer(answer)
                    gateway.start_keepalive()
                    session.mark_started()
                    logger.info("已开局，发送一次点击以验证输入链路")
                    gateway.send_input(
                        encode_mouse_up(MouseClick(point=PixelPoint(x=960, y=540)))
                    )
                finally:
                    await peer.close()

            asyncio.run(_run())
    except NcgError as exc:
        logger.exception("启动失败，尝试结束以止损")
        try:
            with NcgHttpClient(token) as http:
                NcgApi(http).mark_stopped(game_code)
        except Exception:
            logger.exception("止损失败")
        raise SystemExit(1) from exc


@main.command()
@click.option("--bearer", default="", help="Bearer 票据")
@click.option("--game-code", default="cywlbfwt", help="游戏编码")
def stop(bearer: str, game_code: str) -> None:
    """结束一局（必须调用以止损）。

    :param bearer: 票据
    :param game_code: 游戏编码
    """
    token = _read_bearer(bearer)
    try:
        with NcgHttpClient(token) as http:
            NcgApi(http).mark_stopped(game_code)
    except NcgError as exc:
        logger.exception("结束失败")
        raise SystemExit(1) from exc


@main.command(name="encode-demo")
def encode_demo() -> None:
    """演示输入编码（离线，不计费）。"""
    click.echo(encode_mouse_up(MouseClick(point=PixelPoint(x=960, y=540))))
    click.echo(encode_text(TextStroke(char="测")))
    modifiers = KeyModifiers(
        alt=False, control=False, shift=False, num_lock=False, caps_lock=False,
        scroll_lock=False,
    )
    down, sleep, up = encode_key_tap(KeyPress(code=13, name="enter", modifiers=modifiers))
    click.echo(down)
    click.echo(sleep)
    click.echo(up)
