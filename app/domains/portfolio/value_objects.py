from enum import StrEnum


class AccountType(StrEnum):
    SPOT = "spot"
    MARGIN = "margin"
    EARN = "earn"
    FUTURES = "futures"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class SyncStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
