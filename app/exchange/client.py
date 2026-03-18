import logging

from binance.spot import Spot

from exchange.schemas import BinanceBalance, BinancePrice, BinanceTrade

logger = logging.getLogger(__name__)


class BinanceClient:
    def __init__(self, api_key: str, api_secret: str):
        self.client = Spot(api_key=api_key, api_secret=api_secret)

    def get_spot_balances(self) -> list[BinanceBalance]:
        account = self.client.account()
        balances = []
        for b in account.get("balances", []):
            free = float(b["free"])
            locked = float(b["locked"])
            if free > 0 or locked > 0:
                balances.append(BinanceBalance(**b))

        return balances

    def get_spot_trades(
        self, symbol: str, start_time: int | None = None
    ) -> list[BinanceTrade]:
        params = {"symbol": symbol, "limit": 1000}
        if start_time:
            params["startTime"] = start_time

        all_trades = []
        while True:
            trades = self.client.my_trades(**params)
            if not trades:
                break
            all_trades.extend([BinanceTrade(**t) for t in trades])
            if len(trades) < 1000:
                break
            params["fromId"] = trades[-1]["id"] + 1

        return all_trades

    def get_margin_account(self) -> dict:
        try:
            return self.client.margin_account()
        except Exception as e:
            logger.warning(f"Failed to get margin account: {e}")

            return {"userAssets": []}

    def get_margin_balances(self) -> list[BinanceBalance]:
        account = self.get_margin_account()
        balances = []
        for asset in account.get("userAssets", []):
            free = float(asset.get("free", 0))
            locked = float(asset.get("locked", 0))
            if free > 0 or locked > 0:
                balances.append(
                    BinanceBalance(
                        asset=asset["asset"],
                        free=str(free),
                        locked=str(locked),
                    )
                )

        return balances

    def get_margin_trades(
        self, symbol: str, start_time: int | None = None
    ) -> list[BinanceTrade]:
        params = {"symbol": symbol, "limit": 1000}
        if start_time:
            params["startTime"] = start_time

        try:
            trades = self.client.margin_my_trades(**params)

            return [BinanceTrade(**t) for t in trades]
        except Exception as e:
            logger.warning(f"Failed to get margin trades for {symbol}: {e}")

            return []

    def get_earn_positions(self) -> list[BinanceBalance]:
        balances = []
        try:
            flexible = self.client.get_flexible_product_position()
            for pos in flexible.get("rows", []):
                amount = float(pos.get("totalAmount", 0))
                if amount > 0:
                    balances.append(
                        BinanceBalance(
                            asset=pos["asset"],
                            free=str(amount),
                            locked="0",
                        )
                    )
        except Exception as e:
            logger.warning(f"Failed to get flexible earn positions: {e}")

        try:
            locked = self.client.get_locked_product_position()
            for pos in locked.get("rows", []):
                amount = float(pos.get("amount", 0))
                if amount > 0:
                    existing = next(
                        (b for b in balances if b.asset == pos["asset"]), None
                    )
                    if existing:
                        new_locked = float(existing.locked) + amount
                        idx = balances.index(existing)
                        balances[idx] = BinanceBalance(
                            asset=existing.asset,
                            free=existing.free,
                            locked=str(new_locked),
                        )
                    else:
                        balances.append(
                            BinanceBalance(
                                asset=pos["asset"],
                                free="0",
                                locked=str(amount),
                            )
                        )
        except Exception as e:
            logger.warning(f"Failed to get locked earn positions: {e}")

        return balances

    def get_all_prices(self) -> list[BinancePrice]:
        prices = self.client.ticker_price()

        return [BinancePrice(**p) for p in prices]

    def get_price(self, symbol: str) -> float:
        ticker = self.client.ticker_price(symbol=symbol)

        return float(ticker["price"])
