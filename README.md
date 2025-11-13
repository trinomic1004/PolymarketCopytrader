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
- Start copytrader: `python -m src.cli start --config config/settings.yaml` (automatically mirrors trades *and* streams each watched trader's fills into CSVs under `state/trader_trades/`)
- Status (best when running): `python -m src.cli status`
- Record trader trade history only: `python -m src.cli track-trades --config config/settings.yaml` (standalone tracker without executing copy trades)

Notes
-----
- Uses Polymarket Data API for positions and trades and CLOB API for orders.
- Proportional sizing considers trader portfolio value and your allocated capital.
- See `reference-bot/context_polymarket.md` for Polymarket API details used here.

Trade Tracking
--------------
- `trade_tracking` config block controls the per-trader history recorder that now runs alongside the copytrader.
- Defaults write CSVs to `state/trader_trades/` and resume progress from `state/trade_history_state.json`.
- Adjust `poll_interval` or point `output_dir` somewhere else if you want a different cadence or storage location.
- Run `python -m src.cli track-trades ...` to operate the recorder standalone without placing orders.
