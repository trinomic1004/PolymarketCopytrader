import asyncio
from collections import defaultdict
import os
import signal
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

import click

from .config_manager import ConfigManager, ConfigError
from .utils import append_csv_row, load_env, persist_state, read_state, setup_logging


STATE_PATH = "state/copytrade_state.json"
TRADE_LOG_HEADERS = [
    "timestamp",
    "event_type",
    "trader_name",
    "trader_wallet",
    "market",
    "title",
    "outcome",
    "side",
    "trader_size",
    "trader_price",
    "mirror_shares",
    "mirror_usd",
    "reason",
    "order_status",
    "order_id",
    "notes",
    "stats_copied_trades",
    "stats_copied_usd",
    "stats_rejected_trades",
    "stats_failed_trades",
    "stats_dry_run_trades",
]


class CopyTraderApp:
    def __init__(self, cfg_path: str):
        self.cfg_path = cfg_path
        self.cfg: Dict[str, Any] = {}
        self.logger = None
        self.running = True
        self.portfolio_tracker = None
        self.monitor = None
        self.risk_manager = None
        self.executor = None
        self.config_mtime: float = 0.0
        self.enabled_wallets: Set[str] = set()
        self.poll_interval = 5
        self.portfolio_sync_interval = 60
        self.trader_stats = defaultdict(
            lambda: {
                "copied_trades": 0,
                "copied_usd": 0.0,
                "rejected_trades": 0,
                "failed_trades": 0,
                "dry_run_trades": 0,
            }
        )
        self.trades_file = None

    def stop(self, *_):
        if self.logger:
            self.logger.info("Stopping copytrader...")
        self.running = False

    async def run(self):
        load_env()
        cfg_mgr = ConfigManager(self.cfg_path)
        self.cfg = cfg_mgr.load()
        self.config_mtime = Path(self.cfg_path).stat().st_mtime if Path(self.cfg_path).exists() else 0.0
        self.enabled_wallets = self._enabled_wallets(self.cfg)

        log_cfg = self.cfg.get("logging", {})
        log_level = log_cfg.get("level", os.getenv("LOG_LEVEL", "INFO"))
        log_file = log_cfg.get("file")
        self.trades_file = log_cfg.get("trades_file") or "trades.csv"
        self.logger = setup_logging(log_level, log_file)

        # Lazy import runtime components to avoid requiring all deps for non-start commands
        from .portfolio_tracker import PortfolioTracker
        from .monitor import MultiTraderMonitor
        from .risk_manager import RiskManager

        self.portfolio_tracker = PortfolioTracker()
        self.monitor = MultiTraderMonitor(self.cfg["traders"])
        self.risk_manager = RiskManager(self.cfg["risk_management"], self.portfolio_tracker)

        # Lazy import executor to allow status command without dependency
        from .executor import TradeExecutor, MissingDependency

        try:
            self.executor = TradeExecutor(self.cfg["your_account"])
        except MissingDependency:
            self.logger.error("py-clob-client not installed. Install dependencies to place orders.")
            self.executor = None  # type: ignore

        self.poll_interval = int(self.cfg["monitoring"]["poll_interval"]) or 5
        self.portfolio_sync_interval = int(self.cfg["monitoring"]["portfolio_sync_interval"]) or 60

        # Initial portfolio sync so we have deployment stats before processing trades
        await self._sync_enabled_portfolios()
        last_portfolio_sync = asyncio.get_event_loop().time()

        # Handle signals for graceful shutdown
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        enabled = [
            f"{t.get('name', t['wallet_address'])} ({t['wallet_address']})"
            for t in self.cfg["traders"]
            if t.get("enabled")
        ]
        if enabled:
            self.logger.info("Starting multi-trader copytrader...")
            self.logger.info("Watching %d traders:", len(enabled))
            for entry in enabled:
                self.logger.info(f"- {entry}")
        else:
            self.logger.info("Starting copytrader with no enabled traders.")

        while self.running:
            now = asyncio.get_event_loop().time()

            self._maybe_reload_config()

            # 1) Periodic portfolio sync
            if now - last_portfolio_sync >= self.portfolio_sync_interval:
                await self._sync_enabled_portfolios()
                last_portfolio_sync = now

            # 2) Fetch new trades for all traders
            all_lists = await self.monitor.monitor_all_traders()
            new_trades = [t for sub in all_lists for t in sub]

            # 3) Process trades
            for tr in new_trades:
                mirror_shares, reason, mirror_usd = self.risk_manager.calculate_mirror(tr)
                if mirror_shares <= 0:
                    if self.logger:
                        self.logger.info(
                            f"Skip {tr['trader_name']} trade: {reason} (mirror shares {mirror_shares:.4f})"
                        )
                    continue

                ok, msg = self.risk_manager.validate_trade(tr, mirror_shares, mirror_usd)
                if not ok:
                    self.logger.warning(f"Rejected trade from {tr['trader_name']}: {msg}")
                    self._log_trade_event("rejected", tr, 0.0, mirror_usd, msg, {})
                    continue

                if self.executor is None:
                    self.logger.info(
                        f"Dry-run: Would copy {tr['trader_name']} ${mirror_usd:.2f} ({reason})"
                    )
                    self.risk_manager.update_exposure(tr, mirror_usd)
                    self._log_trade_event("dry_run", tr, mirror_shares, mirror_usd, reason, {"status": "dry_run"})
                    continue

                res = await self.executor.execute_mirror_trade(tr, mirror_shares)
                if res.get("success"):
                    exec_usd = float(res.get("executed_usd", mirror_usd))
                    exec_shares = float(res.get("executed_shares", mirror_shares))
                    reason_text = reason
                    if res.get("note"):
                        reason_text = f"{reason_text}; {res['note']}"
                    self.logger.info(
                        f"Copied {tr['trader_name']}: ${exec_usd:.2f} ({reason_text}) order={res.get('order_id')}"
                    )
                    self.risk_manager.update_exposure(tr, exec_usd)
                    self._log_trade_event("executed", tr, exec_shares, exec_usd, reason_text, res)
                else:
                    self.logger.error(f"Order failed: {res.get('error')}")
                    self._log_trade_event("failed", tr, mirror_shares, mirror_usd, res.get("error", ""), res)

            # 4) Persist status snapshot
            snapshot = {
                "global_exposure_usd": self.risk_manager.global_exposure_usd,
                "per_trader_exposure_usd": self.risk_manager.current_exposure_usd,
                "portfolios": self.portfolio_tracker.portfolios,
            }
            persist_state(STATE_PATH, snapshot)

            await asyncio.sleep(self.poll_interval)

    def _maybe_reload_config(self) -> None:
        cfg_file = Path(self.cfg_path)
        try:
            mtime = cfg_file.stat().st_mtime
        except FileNotFoundError:
            return
        if mtime <= self.config_mtime:
            return

        cfg_mgr = ConfigManager(self.cfg_path)
        new_cfg = cfg_mgr.load()
        self.config_mtime = mtime

        old_enabled = self.enabled_wallets
        self.cfg = new_cfg
        self.enabled_wallets = self._enabled_wallets(new_cfg)
        newly_enabled = self.monitor.update_traders(new_cfg["traders"]) if self.monitor else set()

        self.poll_interval = int(new_cfg["monitoring"]["poll_interval"]) or 5
        self.portfolio_sync_interval = int(new_cfg["monitoring"]["portfolio_sync_interval"]) or 60
        if self.risk_manager:
            self.risk_manager.update_config(new_cfg["risk_management"])

        if newly_enabled and self.logger:
            for trader in new_cfg["traders"]:
                if trader.get("enabled") and trader["wallet_address"] in newly_enabled:
                    self.logger.info(
                        f"Now mirroring {trader.get('name', trader['wallet_address'])} ({trader['wallet_address']})"
                    )

    @staticmethod
    def _enabled_wallets(cfg: Dict[str, Any]) -> Set[str]:
        return {
            str(t.get("wallet_address", "")).lower()
            for t in cfg.get("traders", [])
            if t.get("enabled")
        }

    def _log_trade_event(
        self,
        event_type: str,
        trade: Dict[str, Any],
        mirror_shares: float,
        mirror_usd: float,
        reason: str,
        extra: Dict[str, Any],
    ) -> None:
        if not self.trades_file:
            return

        wallet = trade["trader_wallet"]
        stats = self.trader_stats[wallet]

        if event_type == "executed":
            stats["copied_trades"] += 1
            stats["copied_usd"] += mirror_usd
        elif event_type == "rejected":
            stats["rejected_trades"] += 1
        elif event_type == "failed":
            stats["failed_trades"] += 1
        elif event_type == "dry_run":
            stats["dry_run_trades"] += 1

        note = extra.get("error") or extra.get("note")
        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "trader_name": trade.get("trader_name"),
            "trader_wallet": wallet,
            "market": trade.get("market"),
            "title": trade.get("title"),
            "outcome": trade.get("outcome"),
            "side": trade.get("side"),
            "trader_size": trade.get("size"),
            "trader_price": trade.get("price"),
            "mirror_shares": mirror_shares,
            "mirror_usd": mirror_usd,
            "reason": reason,
            "order_status": extra.get("status"),
            "order_id": extra.get("order_id"),
            "notes": note,
            "stats_copied_trades": stats["copied_trades"],
            "stats_copied_usd": f"{stats['copied_usd']:.2f}",
            "stats_rejected_trades": stats["rejected_trades"],
            "stats_failed_trades": stats["failed_trades"],
            "stats_dry_run_trades": stats["dry_run_trades"],
        }
        append_csv_row(self.trades_file, TRADE_LOG_HEADERS, row)

    async def _sync_enabled_portfolios(self) -> None:
        if not self.portfolio_tracker:
            return
        tasks = [
            self.portfolio_tracker.sync_portfolio(t["wallet_address"])
            for t in self.cfg.get("traders", [])
            if t.get("enabled")
        ]
        if tasks:
            await asyncio.gather(*tasks)


@click.group()
def cli():
    """Polymarket Multi-Trader Copytrading CLI"""
    pass


@cli.command()
@click.option("--config", default="config/settings.yaml", help="Config file path")
def start(config: str):
    """Start monitoring and copying all enabled traders."""
    app = CopyTraderApp(config)
    asyncio.run(app.run())


@cli.command()
def status():
    """Show current exposure and portfolio snapshot (if running)."""
    state = read_state(STATE_PATH)
    if not state:
        click.echo("No runtime state found. Is the copytrader running?")
        return
    click.echo(f"Global Exposure (USD): {state.get('global_exposure_usd', 0.0):.2f}")
    click.echo("Per-trader Exposure (USD):")
    for wallet, usd in (state.get("per_trader_exposure_usd", {}) or {}).items():
        click.echo(f"- {wallet}: ${usd:.2f}")


@cli.command()
@click.option("--trader-name", required=True)
def pause(trader_name: str):
    """Pause copying a specific trader (edit config to disable persistently)."""
    click.echo("Pause is not persisted; please disable the trader in config.")


@cli.command()
@click.option("--trader-name", required=True)
def resume(trader_name: str):
    """Resume copying a specific trader (edit config to enable persistently)."""
    click.echo("Resume is not persisted; please enable the trader in config.")


@cli.command()
def stop():
    """Stop all copytrading (Ctrl+C the running process)."""
    click.echo("To stop, press Ctrl+C in the running process.")


if __name__ == "__main__":  # pragma: no cover
    cli()
