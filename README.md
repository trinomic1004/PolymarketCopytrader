Polymarket Multi-Trader Copytrader
=================================

Overview
--------
- Monitors multiple target trader wallets concurrently
- Copies trades proportionally to each trader’s portfolio risk
- Enforces global and per-trader risk rules
- CLI to start/stop and view status

Project Structure
-----------------
- `config/settings.yaml`: Multi-trader configuration (allocations, risk, monitoring)
- `src/cli.py`: CLI entry point and orchestration
- `src/config_manager.py`: Loads and validates YAML config and env
- `src/portfolio_tracker.py`: Fetches trader portfolios via Data API
- `src/monitor.py`: Polls trader trades concurrently
- `src/risk_manager.py`: Proportional sizing + risk checks
- `src/executor.py`: Places orders via Polymarket CLOB client
- `src/utils.py`: Logging, env utilities
- `.env.example`: Required environment variables
- `requirements.txt`: Python dependencies

Setup
-----
1) Create and populate `.env` from `.env.example`.
2) Edit `config/settings.yaml` with your allocations and trader wallets.
3) Install dependencies: `pip install -r requirements.txt`.

Run
---
- Start copytrader: `python -m src.cli start --config config/settings.yaml`
- Status (best when running): `python -m src.cli status`

Notes
-----
- Uses Polymarket Data API for positions and trades and CLOB API for orders.
- Proportional sizing considers trader portfolio value and your allocated capital.
- See `reference-bot/context_polymarket.md` for Polymarket API details used here.

