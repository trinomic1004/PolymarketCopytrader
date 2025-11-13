#!/usr/bin/env python3
"""
Print the available USDC balance (and other assets) for the configured Polymarket proxy wallet.

Uses the same POLYMARKET_* credentials defined in .env.
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds, AssetType, BalanceAllowanceParams
except ImportError:
    sys.stderr.write("py-clob-client not installed. Run `pip install -r requirements.txt`.\n")
    raise


def require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise SystemExit(f"Missing required env var: {name}")
    return val


def build_client() -> ClobClient:
    load_dotenv(ENV_PATH)
    private_key = require_env("POLYMARKET_PRIVATE_KEY")
    proxy_address = require_env("POLYMARKET_PROXY_ADDRESS")
    signature_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "1"))

    client = ClobClient(
        host="https://clob.polymarket.com",
        key=private_key,
        chain_id=137,
        signature_type=signature_type,
        funder=proxy_address,
    )

    api_key = os.getenv("POLYMARKET_API_KEY")
    api_secret = os.getenv("POLYMARKET_API_SECRET")
    api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE")
    if api_key and api_secret and api_passphrase:
        creds = ApiCreds(
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
        )
    else:
        creds = client.create_or_derive_api_creds()

    if not creds:
        raise SystemExit("Unable to obtain Polymarket API credentials.")

    client.set_api_creds(creds)
    return client


def main() -> None:
    client = build_client()
    params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, token_id="", signature_type=None)
    info = client.get_balance_allowance(params)
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
