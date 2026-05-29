"""
Fugle WebSocket 即時報價 hub — 給「自選清單 / 全市場 movers 各列」用的多檔即時價。

為何要後端 hub（而非瀏覽器直連 Fugle）：
- Fugle 免費方案：**1 條 WS 連線、5 個訂閱數**。若每個瀏覽器分頁各開一條會立刻超限。
- API key 不能放到前端。
所以後端維護「單一」上游 Fugle 連線，訂閱目前需要的 ≤5 檔（aggregates channel），
再把報價廣播給所有瀏覽器端 WS client。同一時間通常只有一個 view（movers 或 watchlist）
在跑，union 多半 ≤5；超過 5 會截斷並 log（不靜默吃掉）。

aggregates channel 的 data 欄位與 REST /intraday/quote 幾乎一致，因此直接重用
fugle._shape_quote() 整形，前後端報價結構一致。
"""

import asyncio
import json
import logging

import websockets

import fugle

log = logging.getLogger("uvicorn.error")

WS_URL = "wss://api.fugle.tw/marketdata/v1.0/stock/streaming"
CHANNEL = "aggregates"
MAX_SUBS = 5  # Fugle 免費方案訂閱上限


def _tw_only(symbols) -> set[str]:
    """只保留台股代碼（數字開頭：個股/ETF，含主動式 00xxxA）。美股 ticker（字母開頭）
    Fugle 沒有 → 過濾掉，不浪費寶貴的訂閱額度。"""
    out: set[str] = set()
    for s in symbols or []:
        s = str(s).strip().upper()
        if s and s[0].isdigit():
            out.add(s)
    return out


def _union_capped(symbol_sets, max_subs: int = MAX_SUBS) -> tuple[set[str], int]:
    """多個 client 的訂閱集合取聯集後截斷到 max_subs。回 (截斷後集合, 聯集原始大小)。"""
    union: set[str] = set()
    for s in symbol_sets:
        union |= s
    capped = set(sorted(union)[:max_subs])
    return capped, len(union)


class _Client:
    __slots__ = ("queue", "symbols")

    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.symbols: set[str] = set()


class QuoteHub:
    def __init__(self):
        self._clients: set[_Client] = set()
        self._desired: set[str] = set()     # union(clients) 截斷到 MAX_SUBS
        self._subscribed: set[str] = set()  # 已確認訂閱（收到 subscribed ack）的 symbol
        self._pending: set[str] = set()     # 已送出 subscribe、等 ack 中的 symbol
        self._sub_ids: dict[str, str] = {}  # symbol → Fugle 訂閱 id（unsubscribe 要用）
        self._latest: dict[str, dict] = {}  # symbol → 最新整形報價（給新 client seed）
        self._ws = None
        self._authed = False
        self._task: asyncio.Task | None = None

    # ── client 管理 ──
    def add_client(self) -> _Client:
        c = _Client()
        self._clients.add(c)
        self._ensure_task()
        return c

    async def remove_client(self, c: _Client) -> None:
        self._clients.discard(c)
        await self._recompute()

    async def set_client_symbols(self, c: _Client, symbols) -> None:
        c.symbols = _tw_only(symbols)
        # 立即把已快取的最新報價推給該 client（含盤後/週末的最後一盤）
        for s in c.symbols:
            if s in self._latest:
                self._put(c, {"event": "quote", "quote": self._latest[s]})
        await self._recompute()

    async def _recompute(self) -> None:
        desired, total = _union_capped(c.symbols for c in self._clients)
        if total > MAX_SUBS:
            log.warning("Fugle WS 訂閱數 %d 超過免費上限 %d，只訂閱 %s（其餘略過）",
                        total, MAX_SUBS, sorted(desired))
        self._desired = desired
        if not self._clients:
            # 沒有任何瀏覽器 client 了 → 主動關上游連線，釋放 Fugle 免費方案唯一的連線額度
            # （ping keepalive 會讓閒置 socket 不會自己 timeout）；關閉後 _run 會接著 break。
            if self._ws:
                try:
                    await self._ws.close()
                except Exception:
                    pass
            return
        await self._apply_desired()

    # ── 上游 Fugle 連線 ──
    def _ensure_task(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _apply_desired(self) -> None:
        if not (self._ws and self._authed):
            return  # 尚未連上/認證 → authenticated 時會整批補送
        active = self._subscribed | self._pending  # 已訂閱或等 ack 中的，不重複訂
        add = self._desired - active
        rm = self._subscribed - self._desired      # 只退「已確認」的；pending 的退訂在收到 ack 時對帳
        try:
            for s in sorted(rm):
                sid = self._sub_ids.pop(s, None)
                if sid:  # Fugle 的 unsubscribe 認訂閱 id（不是 symbol）
                    await self._ws.send(json.dumps({"event": "unsubscribe", "data": {"id": sid}}))
                self._subscribed.discard(s)
            for s in sorted(add):
                await self._ws.send(json.dumps(
                    {"event": "subscribe", "data": {"channel": CHANNEL, "symbol": s}}))
                self._pending.add(s)  # 等 subscribed ack（拿到 id）才算數，之後才退得掉
                asyncio.create_task(self._seed(s))  # REST 補最後一盤，盤後/週末也先有畫面
        except Exception as e:
            log.warning("Fugle WS 套用訂閱失敗：%s", e)

    async def _seed(self, symbol: str) -> None:
        q = await fugle.quote(symbol)
        if q and symbol in self._desired:
            self._latest[symbol] = q
            self._broadcast({"event": "quote", "quote": q})

    async def _run(self) -> None:
        key = fugle._api_key()
        if not key:
            log.warning("Fugle WS：未設定 FUGLE_API_KEY，即時報價串流停用")
            return
        backoff = 1
        while self._clients:
            self._authed = False
            self._subscribed = set()
            self._pending = set()
            self._sub_ids = {}
            try:
                async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=20) as ws:
                    self._ws = ws
                    await ws.send(json.dumps({"event": "auth", "data": {"apikey": key}}))
                    async for raw in ws:
                        await self._handle(raw)
                        if self._authed:
                            backoff = 1  # 認證成功後才重置 backoff，避免壞 key 造成 1s 重連風暴
            except Exception as e:
                log.warning("Fugle WS 連線中斷：%s（%ds 後重連）", e, backoff)
            finally:
                self._ws = None
                self._authed = False
            if not self._clients:
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
        self._task = None

    async def _handle(self, raw) -> None:
        try:
            msg = json.loads(raw)
        except Exception:
            return
        ev = msg.get("event")
        if ev == "authenticated":
            self._authed = True
            self._subscribed = set()
            self._pending = set()
            self._sub_ids = {}
            await self._apply_desired()
        elif ev == "subscribed":
            d = msg.get("data") or {}
            sym, sid = d.get("symbol"), d.get("id")
            if sym and sid:
                self._pending.discard(sym)
                if sym in self._desired:
                    self._sub_ids[sym] = sid
                    self._subscribed.add(sym)
                elif self._ws:
                    # ack 回來時已經不需要了 → 立刻用剛拿到的 id 退訂，避免孤兒訂閱佔額度
                    try:
                        await self._ws.send(json.dumps({"event": "unsubscribe", "data": {"id": sid}}))
                    except Exception:
                        pass
        elif ev in ("data", "snapshot"):
            # snapshot = 訂閱當下的即時快照；data = 後續逐筆更新。兩者 data 結構一致。
            d = msg.get("data") or {}
            sym = d.get("symbol")
            if not sym:
                return
            q = fugle._shape_quote(sym, d)
            self._latest[sym] = q
            self._broadcast({"event": "quote", "quote": q})
        elif ev == "error":
            log.warning("Fugle WS error：%s", (msg.get("data") or {}).get("message"))
        # heartbeat / unsubscribed / pong：略過

    def _broadcast(self, msg: dict) -> None:
        for c in list(self._clients):
            self._put(c, msg)

    def _put(self, c: _Client, msg: dict) -> None:
        try:
            c.queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # 慢 client：丟棄最舊報價，不阻塞 hub


hub = QuoteHub()
