import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Optional

import pandas as pd

from app import get_settings
from app.config.models import BotConfigSnapshot, MarketConfig, StrategyParameters
from app.config.repository import ConfigRepository, to_snapshot


class BaseConfigProvider(ABC):
    """Abstract configuration provider."""

    @abstractmethod
    async def fetch(self) -> BotConfigSnapshot:
        """Return the latest configuration snapshot."""


class GoogleSheetConfigProvider(BaseConfigProvider):
    """
    Transitional provider that reuses the existing Google Sheets integration.

    This allows the legacy configuration workflow to keep working while
    the system is migrated to the new database-backed configuration service.
    """

    def __init__(self, spreadsheet_url: Optional[str] = None) -> None:
        settings = get_settings()
        self.spreadsheet_url = spreadsheet_url or settings.spreadsheet_url

    async def fetch(self) -> BotConfigSnapshot:
        # Read directly from Google Sheets to avoid circular dependency
        def _read_sheets():
            try:
                from poly_utils.google_utils import get_spreadsheet
            except ImportError:
                from data_updater.google_utils import get_spreadsheet
            
            spreadsheet = get_spreadsheet(read_only=True)
            wk_full = spreadsheet.worksheet("Full Markets")
            wk_hyper = spreadsheet.worksheet("Hyperparameters")
            
            # Get markets as DataFrame
            markets_records = wk_full.get_all_records()
            df = pd.DataFrame(markets_records)
            if not df.empty and "question" in df.columns:
                df = df[df["question"] != ""].reset_index(drop=True)
            
            # Get hyperparameters as dict
            hyper_records = wk_hyper.get_all_records()
            params = {}
            for record in hyper_records:
                param_type = record.get("type", "")
                param_name = record.get("param", "")
                param_value = record.get("value", "")
                # Filter out NaN, None, or empty values
                if (param_type and param_name and 
                    not pd.isna(param_type) and not pd.isna(param_name) and
                    str(param_type).strip() and str(param_name).strip()):
                    if param_type not in params:
                        params[param_type] = {}
                    params[param_type][param_name] = param_value
            
            return df, params
        
        loop = asyncio.get_running_loop()
        df, params = await loop.run_in_executor(None, _read_sheets)
        return self._to_snapshot(df, params)

    def _to_snapshot(
        self, markets_df: pd.DataFrame, strategy_dict: Dict[str, Dict[str, object]]
    ) -> BotConfigSnapshot:
        def _clean_value(v):
            """Convert pandas NaN/NaT to None, and handle numpy types."""
            if pd.isna(v):
                return None
            if hasattr(v, "item"):
                return v.item()
            return v
        
        def _clean_dict(d):
            """Recursively clean a dictionary, replacing NaN values with None."""
            if isinstance(d, dict):
                return {k: _clean_dict(v) for k, v in d.items() if not pd.isna(k)}
            return _clean_value(d)
        
        markets = []
        if markets_df is not None and not markets_df.empty:
            for _, row in markets_df.iterrows():
                row_dict = {
                    k: _clean_value(v) for k, v in row.to_dict().items()
                }
                # Clean the metadata dictionary
                cleaned_metadata = _clean_dict(row_dict)
                market = MarketConfig(
                    condition_id=str(row.get("condition_id")),
                    question=row.get("question", ""),
                    token_yes=str(row.get("token1")),
                    token_no=str(row.get("token2")),
                    neg_risk=str(row.get("neg_risk", "")).upper() == "TRUE",
                    tick_size=float(row.get("tick_size", 0.01) or 0.01),
                    trade_size=float(row.get("trade_size", 1) or 1),
                    min_size=float(row.get("min_size", 0) or 0),
                    max_size=self._safe_float(row.get("max_size")),
                    max_spread=float(row.get("max_spread", 5) or 5),
                    param_type=row.get("param_type"),
                    metadata=cleaned_metadata,
                )
                markets.append(market)

        strategies = {}
        for key, values in strategy_dict.items():
            strategies[key] = StrategyParameters(name=key, values=values or {})

        return BotConfigSnapshot(markets=markets, strategies=strategies)

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None


class DatabaseConfigProvider(BaseConfigProvider):
    """Load configuration from the PostgreSQL database."""

    def __init__(self, repository: Optional[ConfigRepository] = None) -> None:
        self._repository = repository or ConfigRepository()

    async def fetch(self) -> BotConfigSnapshot:
        config = await self._repository.load_configuration()
        return to_snapshot(config)


__all__ = ["BaseConfigProvider", "GoogleSheetConfigProvider", "DatabaseConfigProvider"]

