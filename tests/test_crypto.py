"""加解密测试。"""

from ncg.protocol.crypto import brute_force_decode, offset_decode, offset_encode


def test_offset_roundtrip() -> None:
    """偏移编解码应互逆。"""
    text = '{"op":"auth","data":{"game_code":"cywlbfwt"}}'
    assert offset_decode(24, offset_encode(24, text)) == text


def test_brute_force_finds_offset() -> None:
    """暴力破解应找回偏移 24 的明文。"""
    text = '{"op":"offer","data":{"sdp":"v=0"}}'
    blob = offset_encode(24, text)
    assert brute_force_decode(blob) == text
