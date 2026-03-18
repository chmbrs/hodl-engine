from datetime import datetime

from pydantic import BaseModel

from domains.portfolio.value_objects import AccountType, TradeSide


class TradeRecord(BaseModel):
    id: str
    symbol: str
    base_asset: str
    quote_asset: str
    account_type: AccountType
    side: TradeSide
    price: float
    qty: float
    quote_qty: float
    commission: float
    commission_asset: str
    trade_time: datetime


class AssetBalance(BaseModel):
    asset: str
    account_type: AccountType
    free: float
    locked: float
    total: float


class AssetHolding(BaseModel):
    group_name: str
    members: list[str]
    total_qty: float
    avg_entry_price: float
    current_price: float
    current_value: float
    total_cost: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    balances: list[AssetBalance]


class PortfolioDashboard(BaseModel):
    holdings: list[AssetHolding]
    total_value: float
    total_cost: float
    total_pnl: float
    total_pnl_pct: float
    last_sync: datetime | None
