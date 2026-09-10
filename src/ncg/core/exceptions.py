"""语义化异常体系。"""


class NcgError(Exception):
    """客户端根异常。"""


class AuthError(NcgError):
    """认证失败。"""


class TicketError(NcgError):
    """票据分配失败。"""


class SignalingError(NcgError):
    """信令交互失败。"""


class SessionError(NcgError):
    """会话生命周期失败。"""


class CryptoError(NcgError):
    """加解密失败。"""
