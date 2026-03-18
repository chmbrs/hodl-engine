from pydantic import BaseModel


class BinanceTrade(BaseModel):
    id: int
    symbol: str
    price: str
    qty: str
    quoteQty: str
    commission: str
    commissionAsset: str
    time: int
    isBuyer: bool


class BinanceBalance(BaseModel):
    asset: str
    free: str
    locked: str


class BinancePrice(BaseModel):
    symbol: str
    price: str
