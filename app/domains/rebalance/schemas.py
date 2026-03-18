from pydantic import BaseModel

from domains.portfolio.schemas import AssetHolding


class StopLossLevel(BaseModel):
    price: float
    pct_below_entry: float
    label: str


class TakeProfitLevel(BaseModel):
    price: float
    pct_above_entry: float
    label: str


class RebalanceSuggestion(BaseModel):
    group_name: str
    current_allocation_pct: float
    target_allocation_pct: float
    action: str
    suggested_qty: float
    suggested_value_usdt: float


class AssetRebalanceView(BaseModel):
    holding: AssetHolding
    stop_losses: list[StopLossLevel]
    take_profits: list[TakeProfitLevel]


class RebalanceDashboard(BaseModel):
    suggestions: list[RebalanceSuggestion]
    asset_views: list[AssetRebalanceView]
    total_portfolio_value: float
