import asyncio
import time
from typing import Any, Dict, List

import aiohttp


class MultiTraderMonitor:
    """Polls Polymarket Data API for trades of configured traders concurrently."""

    def __init__(self, traders_config: List[Dict[str, Any]]):
        self.traders = traders_config
        self.last_check: Dict[str, int] = {}  # wallet -> epoch seconds
        self.data_api_url = "https://data-api.polymarket.com"

    async def monitor_all_traders(self) -> List[List[Dict[str, Any]]]:
        tasks = [self.monitor_trader(t) for t in self.traders if t.get("enabled")]
        return await asyncio.gather(*tasks)

    async def monitor_trader(self, trader: Dict[str, Any]) -> List[Dict[str, Any]]:
        wallet = trader["wallet_address"]
        if wallet not in self.last_check:
            # First observation: mark baseline timestamp so we only react to future trades.
            self.last_check[wallet] = int(time.time())
            return []

        since = self.last_check.get(wallet, 0)
        trades = await self._fetch_trades(wallet, limit=100)
        now = int(time.time())
        self.last_check[wallet] = now

        new_trades: List[Dict[str, Any]] = []
        for tr in trades:
            ts = int(tr.get("timestamp", 0))
            if ts <= since:
                continue

            # Normalize fields for downstream usage
            normalized = {
                "market": tr.get("conditionId"),
                "tokenID": tr.get("asset"),
                "side": tr.get("side"),
                "size": float(tr.get("size", 0.0)),
                "price": float(tr.get("price", 0.0)),
                "timestamp": ts,
                "title": tr.get("title"),
                "outcome": tr.get("outcome"),
                "transactionHash": tr.get("transactionHash"),
                "trader_name": trader.get("name"),
                "trader_wallet": wallet,
                "allocated_capital": float(trader.get("allocated_capital", 0.0)),
            }
            new_trades.append(normalized)

        # Most recent first
        aggregated = self._aggregate_trades(new_trades)
        aggregated.sort(key=lambda x: x["timestamp"])  # oldest → newest
        return aggregated

    async def _fetch_trades(self, wallet: str, limit: int = 50) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession() as session:
            params = {
                "user": wallet,
                "limit": limit,
                "offset": 0,
                "takerOnly": "false",
            }
            async with session.get(f"{self.data_api_url}/trades", params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                return []

    def update_traders(self, traders_config: List[Dict[str, Any]]) -> set:
        old_enabled = {t["wallet_address"] for t in self.traders if t.get("enabled")}
        new_enabled = {t["wallet_address"] for t in traders_config if t.get("enabled")}
        removed = old_enabled - new_enabled
        for wallet in removed:
            self.last_check.pop(wallet, None)
        self.traders = traders_config
        return new_enabled - old_enabled

    def _aggregate_trades(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, Dict[str, Any]] = {}
        for tr in trades:
            key = self._aggregation_key(tr)
            if key not in grouped:
                grouped[key] = {
                    **tr,
                    "_size_sum": 0.0,
                    "_price_notional": 0.0,
                    "timestamp": tr["timestamp"],
                }
            entry = grouped[key]
            entry["_size_sum"] += tr["size"]
            entry["_price_notional"] += tr["price"] * tr["size"]
            entry["timestamp"] = max(entry["timestamp"], tr["timestamp"])

        aggregated: List[Dict[str, Any]] = []
        for entry in grouped.values():
            size = entry["_size_sum"]
            notional = entry["_price_notional"]
            price = notional / max(size, 1e-9)
            entry["size"] = size
            entry["price"] = price
            entry.pop("_size_sum", None)
            entry.pop("_price_notional", None)
            aggregated.append(entry)
        return aggregated

    def _aggregation_key(self, trade: Dict[str, Any]) -> str:
        tx_hash = str(trade.get("transactionHash") or "").lower()
        if tx_hash:
            return f"tx:{tx_hash}:{trade.get('tokenID')}:{trade.get('side')}"
        return "ts:{timestamp}:{token}:{side}:{price}".format(
            timestamp=trade.get("timestamp"),
            token=trade.get("tokenID"),
            side=trade.get("side"),
            price=trade.get("price"),
        )
