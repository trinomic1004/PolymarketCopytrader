import asyncio
import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from .utils import ensure_dir, persist_state, read_state


TRADE_HEADERS = [
    "timestamp_iso",
    "timestamp_unix",
    "transaction_hash",
    "side",
    "size",
    "price",
    "market",
    "token_id",
    "title",
    "outcome",
]


class TradeHistoryRecorder:
    """Fetches and persist trades for all enabled traders to per-trader CSV files."""

    def __init__(
        self,
        traders_config: List[Dict[str, Any]],
        output_dir: str = "state/trader_trades",
        state_path: str = "state/trade_history_state.json",
        poll_interval: int = 30,
        page_size: int = 200,
        log_level: str = "INFO",
    ) -> None:
        self.traders = [t for t in traders_config if t.get("enabled")]
        self.output_dir = Path(output_dir)
        self.state_path = state_path
        self.poll_interval = max(poll_interval, 5)
        self.page_size = page_size
        self.data_api_url = "https://data-api.polymarket.com"
        self.logger = self._build_logger(log_level)
        self.state: Dict[str, Any] = read_state(self.state_path) or {}
        self.trader_state: Dict[str, Dict[str, Any]] = self.state.get("per_trader", {})
        self._session: Optional[aiohttp.ClientSession] = None
        self._trader_update_event = asyncio.Event()
        self._pending_traders: Optional[List[Dict[str, Any]]] = None

    @staticmethod
    def _build_logger(level: str) -> logging.Logger:
        logger = logging.getLogger("trade_recorder")
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            logger.addHandler(handler)
        return logger

    async def run(self) -> None:
        if not self.traders:
            self.logger.info("No enabled traders found in configuration.")
            return

        self.output_dir.mkdir(parents=True, exist_ok=True)
        try:
            async with aiohttp.ClientSession() as session:
                self._session = session
                await self._bootstrap_traders()
                while True:
                    await self._apply_pending_updates()
                    await self._sync_new_trades()
                    await asyncio.sleep(self.poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.logger.error(f"Trade recorder stopped due to error: {exc}")
            raise
        finally:
            self._persist_state()
            self._session = None

    async def _bootstrap_traders(self) -> None:
        for trader in self.traders:
            wallet = trader["wallet_address"]
            log_path = self._log_path(trader)
            state = self.trader_state.get(wallet)
            if state and log_path.exists():
                continue

            trades = await self._fetch_all_trades(wallet)
            if trades:
                self.logger.info(
                    f"Bootstrapping history for {self._label(trader)} with {len(trades)} trades."
                )
                self._write_full_log(trader, trades)
                last_ts = trades[-1]["timestamp"]
                last_hashes = [t["transaction_hash"] for t in trades if t["timestamp"] == last_ts]
                self.trader_state[wallet] = {
                    "last_timestamp": last_ts,
                    "last_hashes": last_hashes,
                }
            else:
                self.logger.info(f"No trades found for {self._label(trader)}; writing empty log.")
                self._write_full_log(trader, [])
                self.trader_state.setdefault(wallet, {"last_timestamp": 0, "last_hashes": []})
            self._persist_state()

    async def _sync_new_trades(self) -> None:
        for trader in self.traders:
            wallet = trader["wallet_address"]
            state = self.trader_state.setdefault(wallet, {"last_timestamp": 0, "last_hashes": []})
            last_ts = int(state.get("last_timestamp", 0))
            last_hashes = state.get("last_hashes", [])

            new_trades = await self._fetch_new_trades(wallet, last_ts, last_hashes)
            if not new_trades:
                continue

            self._append_trades(trader, new_trades)
            latest_ts = new_trades[-1]["timestamp"]
            latest_hashes = [t["transaction_hash"] for t in new_trades if t["timestamp"] == latest_ts]
            self.trader_state[wallet] = {
                "last_timestamp": latest_ts,
                "last_hashes": latest_hashes,
            }
            self.logger.info(
                f"Recorded {len(new_trades)} trades for {self._label(trader)} (latest ts {latest_ts})."
            )
            self._persist_state()

    async def _fetch_all_trades(self, wallet: str) -> List[Dict[str, Any]]:
        trades: List[Dict[str, Any]] = []
        offset = 0
        while True:
            batch = await self._fetch_trades_batch(wallet, offset)
            if not batch:
                break
            trades.extend(batch)
            if len(batch) < self.page_size:
                break
            offset += self.page_size
        normalized = [self._normalize_trade(wallet, tr) for tr in trades]
        normalized.sort(key=lambda t: t["timestamp"])
        return normalized

    async def _fetch_new_trades(
        self, wallet: str, last_timestamp: int, last_hashes: List[str]
    ) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        offset = 0
        last_hash_set = set(last_hashes or [])

        while True:
            batch = await self._fetch_trades_batch(wallet, offset)
            if not batch:
                break
            normalized = [self._normalize_trade(wallet, tr) for tr in batch]
            collected.extend(normalized)

            min_ts = min((t["timestamp"] for t in normalized), default=None)
            if len(batch) < self.page_size or (min_ts is not None and min_ts < last_timestamp):
                break
            offset += self.page_size

        if not collected:
            return []

        collected.sort(key=lambda t: t["timestamp"])
        new_trades = []
        for trade in collected:
            ts = trade["timestamp"]
            tx_hash = trade["transaction_hash"]
            if ts < last_timestamp:
                continue
            if ts == last_timestamp and tx_hash in last_hash_set:
                continue
            new_trades.append(trade)

        return new_trades

    async def _fetch_trades_batch(self, wallet: str, offset: int) -> List[Dict[str, Any]]:
        if not self._session:
            raise RuntimeError("TradeHistoryRecorder session is not initialized.")

        params = {
            "user": wallet,
            "limit": self.page_size,
            "offset": offset,
            "takerOnly": "false",
        }
        try:
            async with self._session.get(f"{self.data_api_url}/trades", params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                self.logger.warning(
                    f"Fetching trades for {wallet} failed with status {resp.status}."
                )
        except Exception as exc:
            self.logger.error(f"Error fetching trades for {wallet}: {exc}")
        return []

    def _append_trades(self, trader: Dict[str, Any], trades: List[Dict[str, Any]]) -> None:
        if not trades:
            return
        log_path = self._log_path(trader)
        ensure_dir(str(log_path))
        file_exists = log_path.exists()
        with open(log_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_HEADERS)
            if not file_exists:
                writer.writeheader()
            for trade in trades:
                writer.writerow(self._format_row(trade))

    def _write_full_log(self, trader: Dict[str, Any], trades: List[Dict[str, Any]]) -> None:
        log_path = self._log_path(trader)
        ensure_dir(str(log_path))
        with open(log_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=TRADE_HEADERS)
            writer.writeheader()
            for trade in trades:
                writer.writerow(self._format_row(trade))

    def _format_row(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        ts = int(trade.get("timestamp", 0))
        timestamp_iso = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        return {
            "timestamp_iso": timestamp_iso,
            "timestamp_unix": ts,
            "transaction_hash": trade.get("transaction_hash", ""),
            "side": trade.get("side", ""),
            "size": f"{float(trade.get('size', 0.0)):.6f}",
            "price": f"{float(trade.get('price', 0.0)):.6f}",
            "market": trade.get("market", ""),
            "token_id": trade.get("token_id", ""),
            "title": trade.get("title", ""),
            "outcome": trade.get("outcome", ""),
        }

    def _log_path(self, trader: Dict[str, Any]) -> Path:
        wallet = trader["wallet_address"].lower()
        name = trader.get("name") or wallet
        safe_name = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_") or "trader"
        filename = f"{safe_name}_{wallet}.csv"
        return self.output_dir / filename

    @staticmethod
    def _label(trader: Dict[str, Any]) -> str:
        return trader.get("name") or trader.get("wallet_address")

    def _normalize_trade(self, wallet: str, trade: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "timestamp": int(trade.get("timestamp", 0)),
            "transaction_hash": str(trade.get("transactionHash", "") or ""),
            "side": str(trade.get("side", "")).upper(),
            "size": float(trade.get("size", 0.0)),
            "price": float(trade.get("price", 0.0)),
            "market": trade.get("conditionId") or "",
            "token_id": trade.get("asset") or "",
            "title": trade.get("title") or "",
            "outcome": trade.get("outcome") or "",
            "trader_wallet": wallet,
        }

    def _persist_state(self) -> None:
        self.state["per_trader"] = self.trader_state
        persist_state(self.state_path, self.state)
    def queue_trader_update(self, traders_config: List[Dict[str, Any]]) -> None:
        """Schedule a trader set update to be processed by the recorder loop."""
        self._pending_traders = traders_config
        self._trader_update_event.set()

    async def _apply_pending_updates(self) -> None:
        if not self._trader_update_event.is_set():
            return
        self._trader_update_event.clear()
        pending = self._pending_traders
        self._pending_traders = None
        if not pending:
            return
        self.traders = [t for t in pending if t.get("enabled")]
        await self._bootstrap_traders()
