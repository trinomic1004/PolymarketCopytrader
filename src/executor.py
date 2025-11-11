from typing import Any, Dict


class MissingDependency(Exception):
    pass


try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
    from py_clob_client.order_builder.constants import BUY, SELL
except Exception as e:  # pragma: no cover
    ClobClient = None  # type: ignore
    OrderArgs = None  # type: ignore
    OrderType = None  # type: ignore
    BUY = "BUY"  # fallbacks for type hints
    SELL = "SELL"

from .risk_manager import MIN_ORDER_USD


class TradeExecutor:
    def __init__(self, account_cfg: Dict[str, Any]):
        if ClobClient is None:
            raise MissingDependency(
                "py-clob-client is required. Install with `pip install py-clob-client`"
            )

        host = "https://clob.polymarket.com"
        private_key = account_cfg.get("private_key")
        signature_type = int(account_cfg.get("signature_type", 1))
        proxy_address = account_cfg.get("proxy_address")
        self.min_order_size_cache: Dict[str, float] = {}

        self.client = ClobClient(
            host,
            key=private_key,
            chain_id=137,
            signature_type=signature_type,
            funder=proxy_address,
        )

        # Use provided API creds if present, else create/derive
        api_key = account_cfg.get("api_key")
        api_secret = account_cfg.get("api_secret")
        api_passphrase = account_cfg.get("api_passphrase")
        if api_key and api_secret and api_passphrase:
            creds = ApiCreds(
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase,
            )
        else:
            creds = self.client.create_or_derive_api_creds()

        if not creds:
            raise MissingDependency("Unable to obtain Polymarket API credentials.")

        self.client.set_api_creds(creds)

    def _get_min_order_size(self, token_id: str) -> float:
        if token_id in self.min_order_size_cache:
            return self.min_order_size_cache[token_id]
        try:
            book = self.client.get_order_book(token_id)
            min_size = float(getattr(book, "min_order_size", 0.0) or 0.0)
        except Exception:
            min_size = 0.0
        self.min_order_size_cache[token_id] = min_size
        return min_size

    def _apply_minimums(self, token_id: str, price: float, shares: float) -> Dict[str, Any]:
        price = max(price, 1e-9)
        min_shares_usd = MIN_ORDER_USD / price
        min_shares_market = self._get_min_order_size(token_id)
        min_shares = max(min_shares_usd, min_shares_market)

        adjusted_shares = shares
        note_parts = []

        if min_shares_market > 0 and shares < min_shares_market:
            adjusted_shares = max(adjusted_shares, min_shares_market)
            note_parts.append(f"raised to market min {min_shares_market:.4f} shares")

        usd_value = adjusted_shares * price
        if usd_value < MIN_ORDER_USD:
            adjusted_shares = max(adjusted_shares, min_shares_usd)
            usd_value = adjusted_shares * price
            note_parts.append("raised to $1 min")

        return {
            "shares": adjusted_shares,
            "usd": usd_value,
            "note": "; ".join(note_parts) if note_parts else "",
        }

    async def execute_mirror_trade(self, original_trade: Dict[str, Any], mirror_shares: float) -> Dict[str, Any]:
        """Places a limit order mirroring the observed trade size (shares)."""
        try:
            side_str = str(original_trade.get("side", "BUY")).upper()
            side = BUY if side_str == "BUY" else SELL
            token_id = str(original_trade["tokenID"])
            price = float(original_trade["price"])

            minimums = self._apply_minimums(token_id, price, mirror_shares)
            adjusted_shares = minimums["shares"]
            adjusted_usd = minimums["usd"]

            order_args = OrderArgs(
                price=price,
                size=float(adjusted_shares),
                side=side,
                token_id=token_id,
            )

            signed = self.client.create_order(order_args)
            result = self.client.post_order(signed, OrderType.GTC)

            return {
                "success": True,
                "order_id": result.get("orderID"),
                "status": result.get("status"),
                "executed_shares": adjusted_shares,
                "executed_usd": adjusted_usd,
                "note": minimums.get("note"),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
