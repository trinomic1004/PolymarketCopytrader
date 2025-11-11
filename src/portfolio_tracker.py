import aiohttp
from typing import Dict, Any


class PortfolioTracker:
    """Tracks trader portfolios and deployment rates using Polymarket Data API."""

    def __init__(self) -> None:
        self.portfolios: Dict[str, float] = {}
        self.deployed_capital: Dict[str, float] = {}
        self.deployment_rates: Dict[str, float] = {}
        self.data_api_url = "https://data-api.polymarket.com"

    async def sync_portfolio(self, wallet_address: str) -> Dict[str, Any]:
        positions = await self._fetch_positions(wallet_address)

        if not positions:
            self.portfolios[wallet_address] = 0.0
            self.deployed_capital[wallet_address] = 0.0
            self.deployment_rates[wallet_address] = 0.0
            return {
                "total_portfolio": 0.0,
                "deployed": 0.0,
                "cash_reserve": 0.0,
                "deployment_rate": 0.0,
                "position_count": 0,
            }

        deployed = sum(float(pos.get("currentValue", 0.0)) for pos in positions)
        total_pnl = sum(float(pos.get("cashPnl", 0.0)) for pos in positions)
        initial_investment = sum(float(pos.get("initialValue", 0.0)) for pos in positions)

        total_value = deployed if deployed > 0 else initial_investment
        deployment_rate = min(deployed / total_value, 1.0) if total_value > 0 else 0.0

        self.portfolios[wallet_address] = float(total_value)
        self.deployed_capital[wallet_address] = float(deployed)
        self.deployment_rates[wallet_address] = float(deployment_rate)

        return {
            "total_portfolio": total_value,
            "deployed": deployed,
            "cash_reserve": total_value - deployed,
            "deployment_rate": deployment_rate,
            "position_count": len(positions),
        }

    async def _fetch_positions(self, wallet_address: str):
        async with aiohttp.ClientSession() as session:
            params = {
                "user": wallet_address,
                "sortBy": "TOKENS",
                "sortDirection": "DESC",
                "sizeThreshold": 0.1,
            }
            async with session.get(f"{self.data_api_url}/positions", params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                return []

    def get_deployment_rate(self, wallet_address: str) -> float:
        return self.deployment_rates.get(wallet_address, 1.0)

    def calculate_effective_allocation(self, wallet_address: str, allocated_capital: float):
        rate = self.get_deployment_rate(wallet_address)
        effective_allocation = allocated_capital * rate
        return effective_allocation, rate

