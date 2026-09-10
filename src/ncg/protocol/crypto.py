"""混淆编解码。"""

import base64
import logging

from ncg.core.exceptions import CryptoError

logger = logging.getLogger(__name__)

_PLAINTEXT_PREFIXES: tuple[bytes, ...] = (b'{"', b'[{"')


def offset_encode(offset: int, plaintext: str) -> bytes:
    """编码明文 JSON。

    :param offset: 偏移量（0-255）
    :param plaintext: 明文 JSON
    :returns: base64 编码后的字节
    :raises CryptoError: 编码失败
    """
    # 与 chunk-common offsetEn 等价：base64((b+offset)%256)
    try:
        raw = plaintext.encode("utf-8")
        shifted = bytes((b + offset) % 256 for b in raw)
        return base64.b64encode(shifted)
    except Exception as exc:
        logger.exception("编码失败")
        raise CryptoError("编码失败") from exc


def offset_decode(offset: int, blob: bytes) -> str:
    """解码混淆载荷。

    :param offset: 偏移量（0-255）
    :param blob: base64 载荷
    :returns: 明文 JSON
    :raises CryptoError: 解码失败
    """
    try:
        raw = base64.b64decode(blob)
        shifted = bytes((b - offset) % 256 for b in raw)
        return shifted.decode("utf-8")
    except Exception as exc:
        # 暴力破解时错误偏移是预期内分支，此处不打日志，由调用方汇总
        raise CryptoError("解码失败") from exc


def brute_force_decode(blob: bytes) -> str:
    """暴力破解偏移量并解码。

    :param blob: base64 载荷
    :returns: 明文 JSON
    :raises CryptoError: 无可用偏移量
    """
    # HAR 实测 WSS 会话偏移为 24，逐个试 0-255 直到出现 JSON 头
    last_error: CryptoError | None = None
    for offset in range(256):
        try:
            text = offset_decode(offset, blob)
            encoded = text.encode("utf-8")
            if encoded.startswith(_PLAINTEXT_PREFIXES):
                logger.debug("命中偏移 %d", offset)
                return text
        except CryptoError as exc:
            last_error = exc
    logger.error("暴力破解偏移失败")
    if last_error is not None:
        raise CryptoError("无可用偏移量") from last_error
    raise CryptoError("无可用偏移量")
