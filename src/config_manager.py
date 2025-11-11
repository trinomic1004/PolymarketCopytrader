import os
from typing import Any, Dict

import yaml

from .utils import expand_env_ref


class ConfigError(Exception):
    pass


class ConfigManager:
    def __init__(self, path: str):
        self.path = path
        self._config: Dict[str, Any] = {}

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            raise ConfigError(f"Config not found: {self.path}")
        with open(self.path, "r") as f:
            raw = yaml.safe_load(f)

        # Expand env:VAR references recursively
        expanded = self._expand(raw)
        self._validate(expanded)
        self._config = expanded
        return expanded

    def _expand(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._expand(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._expand(x) for x in obj]
        if isinstance(obj, str):
            return expand_env_ref(obj)
        return obj

    def _validate(self, cfg: Dict[str, Any]) -> None:
        acct = cfg.get("your_account", {})
        traders = cfg.get("traders", [])
        risk = cfg.get("risk_management", {})

        # Total capital vs allocations
        total_capital = float(acct.get("total_capital", 0))
        allocated_sum = sum(float(t.get("allocated_capital", 0)) for t in traders if t.get("enabled", False))
        if allocated_sum > total_capital:
            raise ConfigError(f"Allocated capital ({allocated_sum}) exceeds total_capital ({total_capital})")

        # Validate addresses
        for t in traders:
            addr = str(t.get("wallet_address", "")).lower()
            if not addr.startswith("0x") or len(addr) != 42:
                raise ConfigError(f"Invalid wallet address for trader '{t.get('name','?')}': {addr}")

        # Risk checks sanity
        global_risk = risk.get("global", {})
        if float(global_risk.get("max_total_exposure", 0)) <= 0:
            raise ConfigError("max_total_exposure must be > 0")

        # Monitoring defaults
        mon = cfg.get("monitoring", {})
        if int(mon.get("poll_interval", 0)) <= 0:
            raise ConfigError("monitoring.poll_interval must be > 0")

