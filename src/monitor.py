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
        new_trades.sort(key=lambda x: x["timestamp"])  # oldest → newest
        return new_trades

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
