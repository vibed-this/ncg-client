"""纯视频 WebRTC。"""

import asyncio
import logging
import time
from collections.abc import Callable

from aiortc import MediaStreamError, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack
from aiortc.rtcrtpreceiver import RTCRtpReceiver
from aiortc.stats import RTCInboundRtpStreamStats
from av.video.frame import VideoFrame

from ncg.core.exceptions import SessionError
from ncg.models.entities import StreamStats, loss_percent

logger = logging.getLogger(__name__)

#: 视频 RTP 时钟频率，抖动单位换算用
VIDEO_CLOCK_RATE = 90000


def jitter_to_ms(jitter: int, clock_rate: int = VIDEO_CLOCK_RATE) -> float:
    """RTP 抖动单位换算为毫秒。

    :param jitter: aiortc 上报的抖动（RTP 时间戳单位）
    :param clock_rate: 时钟频率，视频为 90000
    :returns: 抖动毫秒
    :raises SessionError: 参数非法
    """
    if clock_rate <= 0:
        raise SessionError("时钟频率非法")
    return jitter * 1000.0 / clock_rate


class VideoOnlyPeer:
    """只订阅视频的端点。

    :param on_frame: 视频帧回调，消费慢时由调用方丢帧
    """

    def __init__(self, on_frame: Callable[[VideoFrame], None] | None = None) -> None:
        self._peer = RTCPeerConnection()
        self._on_frame = on_frame
        self._receiver: RTCRtpReceiver | None = None
        self._frames_decoded = 0
        self._last_sample: tuple[float, int, int, int] | None = None
        self._peer.on("track", self._on_track)
        self._peer.on("connectionstatechange", self._on_connection_state)

    def _on_connection_state(self) -> None:
        """记录连接态跃迁。"""
        # 区分网没了还是对端拆台，全程静默不利于验尸
        logger.info("连接态：%s", self._peer.connectionState)

    def _on_track(self, track: MediaStreamTrack) -> None:
        """处理远端轨道。

        :param track: 媒体轨道
        """
        # 只保留视频，音频直接丢弃以省带宽
        if track.kind != "video":
            track.stop()
            logger.info("已丢弃非视频轨道")
            return
        logger.info("收到视频轨道 id=%s", track.id)
        for receiver in self._peer.getReceivers():
            if receiver.track is track:
                self._receiver = receiver
        if self._on_frame is not None:
            asyncio.get_running_loop().create_task(self._consume(track))

    async def _consume(self, track: MediaStreamTrack) -> None:
        """拉取视频帧并回调。

        :param track: 视频轨道
        """
        # 消费循环随对端结束而退出，异常仅记日志
        start_count = self._frames_decoded
        while True:
            try:
                frame = await track.recv()
            except MediaStreamError:
                logger.info(
                    "视频轨道结束 id=%s 共解%d帧", track.id, self._frames_decoded - start_count
                )
                return
            if isinstance(frame, VideoFrame):
                self._frames_decoded += 1
                self._deliver(frame)

    def _deliver(self, frame: VideoFrame) -> None:
        """投递单帧。

        :param frame: 视频帧
        """
        assert self._on_frame is not None
        try:
            self._on_frame(frame)
        except Exception:
            logger.exception("帧回调失败")

    async def answer_for(self, offer_sdp: str) -> str:
        """根据 offer 生成 answer。

        :param offer_sdp: 远端 SDP
        :returns: 本地 SDP
        :raises SessionError: 协商失败
        """
        if not offer_sdp:
            raise SessionError("缺少 offer SDP")
        try:
            await self._peer.setRemoteDescription(RTCSessionDescription(offer_sdp, "offer"))
            answer = await self._peer.createAnswer()
            # 服务端要求被动模式
            patched = answer.sdp.replace("a=setup:active", "a=setup:passive")
            await self._peer.setLocalDescription(RTCSessionDescription(patched, answer.type))
            local = self._peer.localDescription
            if not local.sdp:
                raise SessionError("本地 SDP 为空")
            return local.sdp
        except SessionError:
            raise
        except Exception as exc:
            logger.exception("视频协商失败")
            raise SessionError("视频协商失败") from exc

    async def collect_stats(self, delay_ms: float | None = None) -> StreamStats:
        """采集推流统计快照（与网页端同口径）。

        :param delay_ms: 网关测速延迟毫秒，调用方后台采样传入
        :returns: 统计快照，loss/fps 为窗口差分，首个窗口记零
        """
        # recvonly 端只有 inbound-rtp；aiortc 无 candidate-pair，RTT 由网关 ping 提供
        packets_received = 0
        packets_lost = 0
        if self._receiver is not None:
            try:
                report = await self._receiver.getStats()
            except Exception:
                logger.exception("采集统计失败")
                report = None
            if report is not None:
                for stats in report.values():
                    if isinstance(stats, RTCInboundRtpStreamStats):
                        packets_received = stats.packetsReceived
                        packets_lost = stats.packetsLost
                        break
        now = time.monotonic()
        loss = 0.0
        fps = 0.0
        if self._last_sample is not None:
            prev_at, prev_recv, prev_lost, prev_frames = self._last_sample
            elapsed = now - prev_at
            if elapsed > 0:
                # 计数器回绕时钳零，避免负增量抛错
                loss = loss_percent(
                    max(packets_lost - prev_lost, 0),
                    max(packets_received - prev_recv, 0),
                )
                fps = max(self._frames_decoded - prev_frames, 0) / elapsed
        self._last_sample = (now, packets_received, packets_lost, self._frames_decoded)
        return StreamStats(
            delay_ms=delay_ms,
            loss_percent=loss,
            fps=fps,
            packets_received=packets_received,
            packets_lost=packets_lost,
            frames_decoded=self._frames_decoded,
        )

    async def close(self) -> None:
        """关闭端点。"""
        try:
            await self._peer.close()
        except Exception:
            logger.exception("关闭视频端点失败")


def answer_for_offer(offer_sdp: str) -> str:
    """同步包装的协商入口。

    :param offer_sdp: 远端 SDP
    :returns: 本地 SDP
    """
    peer = VideoOnlyPeer()
    try:
        return asyncio.run(peer.answer_for(offer_sdp))
    finally:
        asyncio.run(peer.close())
