import csv
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


def load_env() -> None:
    """Load environment variables from .env if present."""
    load_dotenv(override=False)


def setup_logging(level: str, logfile: Optional[str]) -> logging.Logger:
    logger = logging.getLogger("copytrader")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    if logfile:
        fh = RotatingFileHandler(logfile, maxBytes=2_000_000, backupCount=2)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger


def ensure_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def persist_state(state_path: str, data: dict) -> None:
    ensure_dir(state_path)
    with open(state_path, "w") as f:
        json.dump(data, f, indent=2)


def read_state(state_path: str) -> Optional[dict]:
    p = Path(state_path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def expand_env_ref(value: str) -> str:
    """Expand values like 'env:VAR_NAME' to the environment value."""
    if isinstance(value, str) and value.startswith("env:"):
        var = value.split(":", 1)[1]
        return os.getenv(var, "")
    return value


def append_csv_row(csv_path: str, headers: list, row: dict) -> None:
    """Append a row to csv_path, creating the file with headers if needed."""
    if not csv_path:
        return
    ensure_dir(csv_path)
    csv_file = Path(csv_path)
    file_exists = csv_file.exists()
    with open(csv_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if not file_exists:
            writer.writeheader()
        writer.writerow({h: row.get(h, "") for h in headers})
