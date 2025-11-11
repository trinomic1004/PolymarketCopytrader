from typing import Any, Dict, Tuple


MIN_ORDER_USD = 1.0


class RiskManager:
    def __init__(self, config: Dict[str, Any], portfolio_tracker):
        self.config = config
        self.portfolio_tracker = portfolio_tracker
        self.current_exposure_usd: Dict[str, float] = {}  # trader_wallet -> USD
        self.global_exposure_usd: float = 0.0

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
        if 0 < mirror_usd < MIN_ORDER_USD:
            if effective_alloc < MIN_ORDER_USD:
                return 0.0, "Allocated capital below $1 minimum order", 0.0
            mirror_usd = MIN_ORDER_USD

        mirror_shares = mirror_usd / max(price, 1e-9)

        reason = f"{position_pct*100:.2f}% of trader portfolio; deployment {deployment_rate*100:.1f}%"
        if mirror_usd == MIN_ORDER_USD and trade_value_usd > 0:
            reason += " (floored to $1 min)"
        return mirror_shares, reason, mirror_usd

    def validate_trade(self, trade: Dict[str, Any], mirror_shares: float, mirror_usd: float) -> Tuple[bool, str]:
        trader_wallet = trade["trader_wallet"]
        price = float(trade.get("price", 0.0))

        # Check 1: Absolute max single bet (USD)
        if mirror_usd > float(self.config["global"]["max_single_bet"]):
            return False, f"Exceeds max single bet: ${mirror_usd:.2f}"

        # Check 2: Per-trader max position percentage of allocated
        allocated = float(trade["allocated_capital"]) or 1.0
        position_pct = mirror_usd / allocated
        max_pct = float(self.config["per_trader"]["max_position_pct"]) or 1.0
        if position_pct > max_pct:
            return False, f"Exceeds max position %: {position_pct*100:.1f}%"

        # Check 3: Global exposure limit
        new_global = self.global_exposure_usd + mirror_usd
        if new_global > float(self.config["global"]["max_total_exposure"]):
            return False, f"Exceeds global exposure: ${new_global:.2f}"

        # Check 4: Per-trader exposure against allocated capital
        trader_exposure = float(self.current_exposure_usd.get(trader_wallet, 0.0))
        if trader_exposure + mirror_usd > allocated:
            return False, "Exceeds allocated capital for trader"

        # Check 5: Market filters placeholder (can integrate categories/liquidity)
        # Always passes for now
        return True, "OK"

    def update_exposure(self, trade: Dict[str, Any], mirror_usd: float) -> None:
        trader_wallet = trade["trader_wallet"]
        self.current_exposure_usd[trader_wallet] = self.current_exposure_usd.get(trader_wallet, 0.0) + mirror_usd
        self.global_exposure_usd += mirror_usd

    def update_config(self, config: Dict[str, Any]) -> None:
        self.config = config
