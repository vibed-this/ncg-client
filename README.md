# ncg-client

网易云游戏（https://cg.163.com/）三方客户端：PC 键鼠文本操控 + 纯视频串流。

## 安装

核心库零重依赖（`attrs/cattrs/click/httpx/websockets/aiortc`），demo 依赖为可选项：

```powershell
uv sync                       # 本地开发：核心 + demo + dev 全装
pip install ncg-client        # 只装核心
pip install "ncg-client[demo]"  # 加装 pygame 可交互 demo
```

## 鉴权数据获取

开局需要两样东西，都从已登录的 `cg.163.com` 页面拿：

1. **Bearer**：F12 → Network 过滤 `users/@me` → Headers 复制 `Authorization` 去掉
   `Bearer ` 前缀后的 JWT，设为环境变量 `NCG_BEARER`。
2. **易盾票据**：同页控制台执行以下脚本，输出的 hex 即票据（短 TTL 内可复用，
   稳妥起见每次开局取新），设为 `NCG_YIDUN`：

```js
await new Promise((resolve, reject) => {
  const run = (w) => w.getToken("a0d6550c04264134bb648b5113a00e63", resolve, reject);
  if (window.__ncgWatchman) return run(window.__ncgWatchman);
  window.initWatchman({
    productNumber: "YD00830395613452",
    onload: (w) => { window.__ncgWatchman = w; run(w); },
    onerror: reject,
  });
  setTimeout(() => reject(new Error("watchman 超时")), 15000);
}).then(t => { console.log(t); copy(t); return t; });
```

## CLI 用法

```powershell
$env:NCG_BEARER='<Bearer>'; $env:NCG_YIDUN='<易盾票>'

uv run ncg check --game-code cywlbfwt          # 只读：用户/余量/节点/反作弊门控，不计费
uv run ncg start --gateway-url <票据网关> --confirm-billing  # 计费开局（需配合 tickets 流程）
uv run ncg stop --game-code cywlbfwt           # 结束计费，幂等
uv run ncg encode-demo                         # 输入编码自检，不联网
```

## 库用法

```python
from ncg.api.client import NcgApi
from ncg.core.http import NcgHttpClient
from ncg.protocol.tickets import build_ticket_payload

with NcgHttpClient(bearer) as http:
    api = NcgApi(http)
    me = api.check_me()                                   # 用户与免费余量
    servers = api.list_media_servers()                    # 按延迟排序选路
    ticket = api.request_ticket(                          # 申请串流票据
        build_ticket_payload(("shzwh4", "shnkpl4"), "cywlbfwt", yidun)
    )
    session = ...  # 见 ncg.session.manager.GameSession：mark_started/stop 止损
```

```python
from ncg.input.commands import encode_mouse_down, encode_text
from ncg.models.entities import MouseClick, PixelPoint, TextStroke

encode_mouse_down(MouseClick(point=PixelPoint(x=960, y=540)))  # 左键按下
encode_text(TextStroke(char="你"))                             # 单字文本
```

网关交互见 `ncg.signaling.gateway.GatewaySocket`
（connect 鉴权 → send_answer → send_input → start_keepalive/start_reader），
视频订阅见 `ncg.media.video.VideoOnlyPeer`（`on_frame` 回调 + `collect_stats`）。

## Demo 用法

```powershell
$env:NCG_BEARER='<Bearer>'; $env:NCG_YIDUN='<易盾票>'
uv run ncg-demo --minutes 3 --confirm-billing
```

960×540 窗口：鼠标点拖、键盘打字即玩，标题栏实时显示
`delay/loss%/fps`（保活回显真 RTT 优先，网关测速兜底）。
ESC 或关窗退出，自动 `DELETE` 止损；`--minutes` 上限 10 分钟。

## 计费与止损

- 每天免费 30 分钟；`PATCH games-playing` 为计费起点。
- `GameSession.stop()` 幂等，任何退出路径（超时/ESC/断线）都走它。
- 不传 `--confirm-billing` 拒绝执行计费操作。
