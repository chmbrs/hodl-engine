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
            # LD* tokens are Simple Earn receipt tokens — they duplicate earn positions
            if (free > 0 or locked > 0) and not b["asset"].startswith("LD"):
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

    def _fetch_all_pages(self, method, amount_key: str) -> list[dict]:
        results = []
        current = 1
        size = 100
        while True:
            resp = method(current=current, size=size)
            rows = resp.get("rows", [])
            results.extend(rows)
            total = resp.get("total", 0)
            if current * size >= total:
                break
            current += 1

        return results

    def get_earn_positions(self) -> list[BinanceBalance]:
        balances: dict[str, BinanceBalance] = {}

        try:
            rows = self._fetch_all_pages(
                self.client.get_flexible_product_position, "totalAmount"
            )
            for pos in rows:
                amount = float(pos.get("totalAmount", 0))
                if amount > 0:
                    asset = pos["asset"]
                    balances[asset] = BinanceBalance(
                        asset=asset,
                        free=str(amount),
                        locked="0",
                    )
        except Exception as e:
            logger.warning(f"Failed to get flexible earn positions: {e}")

        try:
            rows = self._fetch_all_pages(
                self.client.get_locked_product_position, "amount"
            )
            for pos in rows:
                amount = float(pos.get("amount", 0))
                if amount > 0:
                    asset = pos["asset"]
                    if asset in balances:
                        new_locked = float(balances[asset].locked) + amount
                        balances[asset] = BinanceBalance(
                            asset=asset,
                            free=balances[asset].free,
                            locked=str(new_locked),
                        )
                    else:
                        balances[asset] = BinanceBalance(
                            asset=asset,
                            free="0",
                            locked=str(amount),
                        )
        except Exception as e:
            logger.warning(f"Failed to get locked earn positions: {e}")

        return list(balances.values())

    def get_all_prices(self) -> list[BinancePrice]:
        prices = self.client.ticker_price()

        return [BinancePrice(**p) for p in prices]

    def get_price(self, symbol: str) -> float:
        ticker = self.client.ticker_price(symbol=symbol)

        return float(ticker["price"])

    def get_symbols_for_asset(self, asset: str) -> list[str]:
        """Return all symbols (any status) where the asset is the base."""
        if not hasattr(self, "_exchange_info_cache"):
            info = self.client.exchange_info()
            cache: dict[str, list[str]] = {}
            for s in info["symbols"]:
                base = s["baseAsset"]
                cache.setdefault(base, []).append(s["symbol"])
            self._exchange_info_cache = cache

        return self._exchange_info_cache.get(asset, [])

    def get_historical_usd_price(self, quote_asset: str, timestamp_ms: int) -> float:
        """Get the close price of quote_asset in USD at the given timestamp.

        Tries three sources in order:
        1. {quote_asset}USDT klines (direct)
        2. USDT{quote_asset} klines, inverted (e.g. USDTBRL → 1/price)
        3. Frankfurter API (free, no key, covers back to 1999)
        """
        start = timestamp_ms - 3_600_000
        end = timestamp_ms + 3_600_000

        # 1. Direct pair
        try:
            klines = self.client.klines(
                f"{quote_asset}USDT", "1h", startTime=start, endTime=end, limit=2,
            )
            if klines:
                return float(klines[0][4])
        except Exception:
            pass

        # 2. Inverted pair (e.g. USDTBRL)
        try:
            klines = self.client.klines(
                f"USDT{quote_asset}", "1h", startTime=start, endTime=end, limit=2,
            )
            if klines:
                price = float(klines[0][4])
                return 1.0 / price if price > 0 else 0.0
        except Exception:
            pass

        # 3. Frankfurter free FX API
        try:
            import json as _json
            import urllib.request
            from datetime import datetime, timezone

            date_str = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            url = f"https://api.frankfurter.dev/v1/{date_str}?base={quote_asset}&symbols=USD"
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = _json.loads(resp.read())
                rate = data.get("rates", {}).get("USD", 0.0)
                if rate > 0:
                    return float(rate)
        except Exception as e:
            logger.warning(f"Frankfurter fallback failed for {quote_asset}: {e}")

        return 0.0

    def get_convert_history(self, start_ms: int, end_ms: int) -> list[dict]:
        """Fetch Binance Convert trades, paging through 30-day chunks with rate-limit delay."""
        import time

        all_records: list[dict] = []
        chunk = 30 * 24 * 60 * 60 * 1000
        current = start_ms
        while current < end_ms:
            chunk_end = min(current + chunk, end_ms)
            try:
                resp = self.client.get_convert_trade_history(
                    startTime=current, endTime=chunk_end, limit=1000
                )
                records = resp.get("list", [])
                all_records.extend(records)
                if resp.get("moreData") and records:
                    current = int(records[-1]["createTime"]) + 1
                else:
                    current = chunk_end + 1
                time.sleep(0.5)  # avoid rate limit
            except Exception as e:
                logger.warning(f"Failed to get convert history chunk: {e}")
                current = chunk_end + 1
                time.sleep(2.0)  # back off on error

        return all_records
