#!/usr/bin/env python3
"""
Derive Polymarket CLOB API credentials using your wallet.

Reads POLYMARKET_PRIVATE_KEY, POLYMARKET_PROXY_ADDRESS, and
POLYMARKET_SIGNATURE_TYPE from the repo's .env file (or ambient env),
then prints the api_key / secret / passphrase returned by the CLOB.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from py_clob_client.client import ClobClient


ROOT = Path(__file__).resolve().parents[1]
DOTENV_PATH = ROOT / ".env"


def main() -> None:
    load_dotenv(DOTENV_PATH)

    required = [
        "POLYMARKET_PRIVATE_KEY",
        "POLYMARKET_PROXY_ADDRESS",
        "POLYMARKET_SIGNATURE_TYPE",
    ]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise SystemExit(f"Missing env vars: {missing}")

    client = ClobClient(
        host="https://clob.polymarket.com",
        key=os.environ["POLYMARKET_PRIVATE_KEY"],
        chain_id=137,
        signature_type=int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "1")),
        funder=os.environ["POLYMARKET_PROXY_ADDRESS"].strip(),
    )

    creds = client.create_or_derive_api_creds()
    if not creds:
        raise SystemExit("Server returned no API credentials; check account access.")

    print("Paste these into your .env file:")
    print(f"POLYMARKET_API_KEY={creds.api_key}")
    print(f"POLYMARKET_API_SECRET={creds.api_secret}")
    print(f"POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")


if __name__ == "__main__":
    main()
