from typing import Any, Dict, Tuple


MIN_ORDER_USD = 1.0


class RiskManager:
    def __init__(self, config: Dict[str, Any], portfolio_tracker):
        self.config = config
        self.portfolio_tracker = portfolio_tracker
        self.current_exposure_usd: Dict[str, float] = {}  # trader_wallet -> USD
        self.global_exposure_usd: float = 0.0
        self.positions_usd: Dict[str, Dict[str, float]] = {}  # trader_wallet -> token_id -> USD

    def calculate_mirror(self, trade: Dict[str, Any]) -> Tuple[float, str, float]:
        """
        Calculate mirror trade size in SHARES and return:
        - mirror_shares (float)
        - reason (str)
        - mirror_usd (float)
        """
        trader_wallet = trade["trader_wallet"]
        allocated_capital = float(trade["allocated_capital"])  # USD
        price = float(trade.get("price", 0.0))
        size = float(trade.get("size", 0.0))

        # Trader portfolio value (USD)
        trader_portfolio = float(self.portfolio_tracker.portfolios.get(trader_wallet, 0.0))
        if trader_portfolio <= 0.0 or price <= 0.0 or size <= 0.0:
            return 0.0, "Insufficient data for proportional sizing", 0.0

        # Adjust allocated capital by trader deployment rate
        effective_alloc, deployment_rate = self.portfolio_tracker.calculate_effective_allocation(
            trader_wallet, allocated_capital
        )

        # Trade value in USD and proportion of trader portfolio
        trade_value_usd = size * price
        position_pct = trade_value_usd / trader_portfolio

        # Our USD exposure to mirror and convert to shares
        mirror_usd = max(effective_alloc * position_pct, 0.0)
        if mirror_usd < MIN_ORDER_USD:
            mirror_usd = MIN_ORDER_USD

        mirror_shares = mirror_usd / max(price, 1e-9)

        reason = f"{position_pct*100:.2f}% of trader portfolio; deployment {deployment_rate*100:.1f}%"
        if mirror_usd == MIN_ORDER_USD and trade_value_usd > 0:
            reason += " (floored to $1 min)"
        return mirror_shares, reason, mirror_usd

    def validate_trade(self, trade: Dict[str, Any], mirror_shares: float, mirror_usd: float) -> Tuple[bool, str]:
        trader_wallet = trade["trader_wallet"]
        token_id = str(trade.get("tokenID"))
        side = str(trade.get("side", "BUY")).upper()

        # Check 1: Absolute max single bet (USD)
        if mirror_usd > float(self.config["global"]["max_single_bet"]):
            return False, f"Exceeds max single bet: ${mirror_usd:.2f}"

        # Check 2: Per-trader max position percentage of allocated
        raw_allocated = float(trade["allocated_capital"]) or 0.0
        effective_allocated = max(raw_allocated, MIN_ORDER_USD)
        if side == "BUY":
            position_pct = mirror_usd / effective_allocated
            max_pct = float(self.config["per_trader"]["max_position_pct"]) or 1.0
            if position_pct > max_pct:
                return False, f"Exceeds max position %: {position_pct*100:.1f}%"

        # Check 3: Global exposure limit
        delta = self._simulate_exposure_delta(trader_wallet, token_id, mirror_usd, side)
        new_global = max(self.global_exposure_usd + delta, 0.0)
        if new_global > float(self.config["global"]["max_total_exposure"]):
            return False, f"Exceeds global exposure: ${new_global:.2f}"

        # Check 4: Per-trader exposure against allocated capital
        trader_exposure = float(self.current_exposure_usd.get(trader_wallet, 0.0))
        projected = max(trader_exposure + delta, 0.0)
        if projected > effective_allocated:
            return False, "Exceeds allocated capital for trader"

        # Check 5: Market filters placeholder (can integrate categories/liquidity)
        # Always passes for now
        return True, "OK"

    def update_exposure(self, trade: Dict[str, Any], mirror_usd: float) -> None:
        trader_wallet = trade["trader_wallet"]
        token_id = str(trade.get("tokenID"))
        side = str(trade.get("side", "BUY")).upper()
        delta = self._apply_position_change(trader_wallet, token_id, mirror_usd, side)
        self.current_exposure_usd[trader_wallet] = max(
            self.current_exposure_usd.get(trader_wallet, 0.0) + delta, 0.0
        )
        self.global_exposure_usd = max(self.global_exposure_usd + delta, 0.0)

    def update_config(self, config: Dict[str, Any]) -> None:
        self.config = config

    def _simulate_exposure_delta(self, wallet: str, token_id: str, mirror_usd: float, side: str) -> float:
        if side == "SELL":
            available = self._get_position_usd(wallet, token_id)
            return -min(available, mirror_usd)
        return mirror_usd

    def _apply_position_change(self, wallet: str, token_id: str, mirror_usd: float, side: str) -> float:
        if side == "SELL":
            available = self._get_position_usd(wallet, token_id)
            reduction = min(available, mirror_usd)
            if wallet in self.positions_usd and token_id in self.positions_usd[wallet]:
                self.positions_usd[wallet][token_id] -= reduction
                if self.positions_usd[wallet][token_id] <= 1e-9:
                    del self.positions_usd[wallet][token_id]
                if not self.positions_usd[wallet]:
                    del self.positions_usd[wallet]
            return -reduction

        # BUY
        self.positions_usd.setdefault(wallet, {})
        self.positions_usd[wallet][token_id] = self.positions_usd[wallet].get(token_id, 0.0) + mirror_usd
        return mirror_usd

    def _get_position_usd(self, wallet: str, token_id: str) -> float:
        return self.positions_usd.get(wallet, {}).get(token_id, 0.0)
