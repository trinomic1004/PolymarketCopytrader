#!/usr/bin/env python3
"""
Quick-and-dirty Polymarket trade watcher for debugging.

Polls https://data-api.polymarket.com/trades with a rolling cursor and prints any
new trades in real time so you can confirm data is flowing.
"""

import argparse
import asyncio
import datetime as dt
from typing import Dict, List

import aiohttp

DATA_API = "https://data-api.polymarket.com"


async def fetch_trades(session: aiohttp.ClientSession, wallet: str, limit: int = 50) -> List[Dict]:
    params = {
        "user": wallet,
        "limit": limit,
        "offset": 0,
        "takerOnly": "false",
    }
    async with session.get(f"{DATA_API}/trades", params=params) as resp:
        resp.raise_for_status()
        return await resp.json()


async def watch(wallet: str, poll_interval: float) -> None:
    last_ts = 0
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                trades = await fetch_trades(session, wallet)
                trades.sort(key=lambda t: int(t.get("timestamp", 0)))
                for tr in trades:
                    ts = int(tr.get("timestamp", 0))
                    if ts <= last_ts:
                        continue
                    last_ts = ts
                    print(
                        f"[{dt.datetime.utcfromtimestamp(ts).isoformat()}Z] "
                        f"{tr.get('title')} | {tr.get('side')} {tr.get('size')} @ {tr.get('price')} "
                        f"(wallet {wallet})"
                    )
            except Exception as exc:
                print(f"Error fetching trades: {exc}")
            await asyncio.sleep(poll_interval)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch Polymarket trades for a wallet.")
    parser.add_argument("--wallet", required=True, help="Proxy wallet address to monitor")
    parser.add_argument("--poll", type=float, default=2.0, help="Poll interval seconds (default 2)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(watch(args.wallet, args.poll))


if __name__ == "__main__":
    main()
