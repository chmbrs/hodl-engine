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


class SellTargetLevel(BaseModel):
    price: float
    label: str
    pct_above_entry: float
    is_reached: bool


class RebalanceSuggestion(BaseModel):
    group_name: str
    current_allocation_pct: float
    target_allocation_pct: float
    action: str
    suggested_qty: float
    suggested_value_usdt: float
    target_price: float = 0.0


class AssetRebalanceView(BaseModel):
    holding: AssetHolding
    stop_losses: list[StopLossLevel]
    take_profits: list[TakeProfitLevel]
    sell_targets: list[SellTargetLevel] = []


class AllocationTargetRequest(BaseModel):
    targets: dict[str, float]


class RebalanceDashboard(BaseModel):
    suggestions: list[RebalanceSuggestion]
    asset_views: list[AssetRebalanceView]
    total_portfolio_value: float
    allocation_targets: dict[str, float]
