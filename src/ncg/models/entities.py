"""数据模型。"""

import attrs

from ncg.core.exceptions import SessionError


@attrs.frozen
class Credentials:
    """用户凭证。"""

    bearer: str  # Bearer 票据
    user_id: str  # 用户标识


@attrs.frozen
class VideoSpec:
    """视频规格。"""

    width: int  # 宽度像素
    height: int  # 高度像素
    fps: str  # 帧率
    quality: str  # 档位
    platform: int  # 平台，PC 为 0


@attrs.frozen
class GatewayTicket:
    """网关票据。"""

    gateway_url: str  # 网关地址
    region: str  # 地域
    game_code: str  # 游戏编码


@attrs.frozen
class PixelPoint:
    """像素坐标。"""

    x: int  # 横坐标
    y: int  # 纵坐标


@attrs.frozen
class MouseClick:
    """鼠标点击。"""

    point: PixelPoint  # 点击位置


@attrs.frozen
class MouseMove:
    """鼠标移动。"""

    point: PixelPoint  # 目标位置


@attrs.frozen
class TextStroke:
    """单字文本。"""

    char: str  # 单个字符


@attrs.frozen
class ApkDecoder:
    """解码器信息。"""

    model: str  # 机型
    decoder: tuple[str, ...]  # 解码器列表


@attrs.frozen
class TicketExtra:
    """票据扩展字段。"""

    ali_input: str  # 输入模式，HAR 实测 local_insert
    yidun_game_ticket: str  # 易盾游戏票据，每局新鲜
    network_test_info_list: tuple[str, ...]  # 测速信息列表


@attrs.frozen
class TicketRequest:
    """票据申请明文（HAR #437 offset=24 实测结构）."""

    regions: tuple[str, ...]  # 候选地域
    game_code: str  # 游戏编码
    codecs: tuple[str, ...]  # 编码列表
    extra: TicketExtra  # 扩展字段
    width: int  # 请求宽度
    height: int  # 请求高度
    apk_decoder: ApkDecoder  # 解码器信息


@attrs.frozen
class LockDetail:
    """锁定节点详情。"""

    region: str  # 地域
    width: int  # 锁定宽度
    height: int  # 锁定高度
    ip: str  # 节点 IP
    port: int  # 节点端口


@attrs.frozen
class TicketResponse:
    """票据响应摘要（HAR #437 全字段）。"""

    gateway_url: str  # 网关地址
    region: str  # 地域
    game_code: str  # 游戏编码
    game_type: str  # 游戏类型
    non_vip_queue_len: int  # 非会员排队长度
    non_vip_queue_time: int  # 非会员排队时间
    vip_queue_len: int  # 会员排队长度
    vip_queue_time: int  # 会员排队时间
    time_left: int  # 剩余时长
    user_type: str  # 用户类型
    fast_created: bool  # 是否快速创建
    preboot: bool  # 是否预启动
    play_id: str  # 对局标识
    expires: int  # 过期时间戳
    lock_detail: LockDetail | None  # 锁定节点详情


@attrs.frozen
class YunxinAccount:
    """云信账号。"""

    accid: str  # 账号标识
    token: str  # 账号票据


@attrs.frozen
class UserMe:
    """当前用户信息（HAR #16 @me 明文）。"""

    user_id: str  # 用户标识
    yunxin: YunxinAccount  # 云信账号
    free_time: int  # 总免费时长
    free_time_left: int  # 剩余免费时长
    pc_free_time_left: int  # PC 剩余时长
    pc_free_time_left_this_week: int  # 本周 PC 剩余时长
    pc_vip_time_left: int  # PC 会员剩余时长
    coins: int  # 硬币余额
    coins_per_minute: int  # 每分钟消耗
    is_vip: bool  # 是否会员
    is_now_daily_vip: bool  # 是否当日会员


@attrs.frozen
class TimeRemain:
    """剩余时长查询结果。"""

    is_daily_free: bool  # 是否每日免费
    is_limit_time: bool  # 是否限时


@attrs.frozen
class MediaServer:
    """媒体节点（HAR #202 明文）。"""

    region: str  # 地域
    game_type: str  # 游戏类型
    resolution_type: str  # 分辨率类型
    is_1080: bool  # 是否 1080P
    ping_url: str  # 测速地址
    ping_url1: str  # 电信测速地址
    ping_url2: str  # 联通测速地址
    ping_url3: str  # 移动测速地址
    score_required: int  # 准入门限
    latency_required: int  # 延迟上限
    latency_recommended: int  # 延迟推荐值
    bandwidth_required: int  # 带宽下限
    bandwidth_recommended: int  # 带宽推荐值
    isp: int  # 运营商
    isp_weight: int  # 运营商权重
    ping_weight: int  # 延迟权重
    loss_weight: int  # 丢包权重
    no_latency_block: bool  # 是否跳过延迟门限


@attrs.frozen
class PingSample:
    """单地域测速样本。"""

    region: str  # 地域
    delay: int  # 延迟毫秒
    expire: int  # 过期时间戳
    server: MediaServer  # 所属节点


@attrs.frozen
class KeyModifiers:
    """修饰键状态（chunk-common getKeyboardState 位表）。"""

    alt: bool  # Alt 是否按下
    control: bool  # Control 是否按下
    shift: bool  # Shift 是否按下
    num_lock: bool  # NumLock 是否生效
    caps_lock: bool  # CapsLock 是否生效
    scroll_lock: bool  # ScrollLock 是否生效

    def to_state(self) -> int:
        """转换为状态位掩码。

        :returns: 状态整数（Alt1|Control2|Shift4|NumLock8|CapsLock16|ScrollLock32）
        """
        state = 0
        if self.alt:
            state |= 1
        if self.control:
            state |= 2
        if self.shift:
            state |= 4
        if self.num_lock:
            state |= 8
        if self.caps_lock:
            state |= 16
        if self.scroll_lock:
            state |= 32
        return state


@attrs.frozen
class KeyPress:
    """单键按下或抬起。"""

    code: int  # DOM keyCode，如回车 13
    name: str  # e.key 小写，空格必须为 space
    modifiers: KeyModifiers  # 修饰状态


@attrs.frozen
class MobileKey:
    """移动端 IME 按键。"""

    code: int  # 仅允许 1/2/3/4：退格、回车、左、右


@attrs.frozen
class ClipboardText:
    """剪贴板原文。"""

    text: str  # 非空原文，编码函数内部转 base64


@attrs.frozen
class StreamStats:
    """推流统计快照（与网页端同口径）。"""

    delay_ms: float | None  # 网关测速延迟毫秒，失败为空
    loss_percent: float  # 窗口丢包率百分比
    fps: float  # 窗口解出帧率
    packets_received: int  # 累计收包
    packets_lost: int  # 累计丢包
    frames_decoded: int  # 累计解出帧数


def loss_percent(lost_delta: int, received_delta: int) -> float:
    """计算窗口丢包率。

    :param lost_delta: 窗口丢包增量
    :param received_delta: 窗口收包增量
    :returns: 丢包率百分比，无流量为 0
    :raises SessionError: 参数非法
    """
    # 与网页 se() 一致：dLost/(dLost+dRecv)*100
    if lost_delta < 0 or received_delta < 0:
        raise SessionError("丢包增量非法")
    total = lost_delta + received_delta
    if total == 0:
        return 0.0
    return lost_delta / total * 100.0
