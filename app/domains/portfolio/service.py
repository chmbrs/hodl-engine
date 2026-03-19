import asyncio
import json
import logging
from datetime import datetime, timezone

from exchange.client import BinanceClient
from config import BINANCE_API_KEY, BINANCE_API_SECRET
from db import managed_db_session
from domains.portfolio.schemas import (
    AssetBalance,
    AssetHolding,
    PortfolioDashboard,
    TradeRecord,
)
from domains.portfolio.value_objects import AccountType, SyncStatus, TradeSide

logger = logging.getLogger(__name__)

QUOTE_ASSETS = ["USDT", "BUSD", "USDC", "USD", "BRL", "BNB", "ETH", "BTC"]
STABLECOINS = {"USDT", "BUSD", "USDC", "USD", "DAI", "TUSD", "FDUSD", "RLUSD", "USD1", "USDP", "USDD"}


def _get_binance_client() -> BinanceClient:
    return BinanceClient(api_key=BINANCE_API_KEY, api_secret=BINANCE_API_SECRET)


def _parse_symbol(symbol: str) -> tuple[str, str]:
    for quote in QUOTE_ASSETS:
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]

            return base, quote

    return symbol, ""


async def sync_balances() -> dict:
    client = _get_binance_client()
    now = datetime.now(timezone.utc)
    synced = {"spot": 0, "margin": 0, "earn": 0}

    spot_balances = await asyncio.to_thread(client.get_spot_balances)
    with managed_db_session() as db:
        for b in spot_balances:
            total = float(b.free) + float(b.locked)
            db.execute(
                """INSERT INTO balances (asset, account_type, free, locked, total, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(asset, account_type)
                   DO UPDATE SET free=?, locked=?, total=?, updated_at=?""",
                (
                    b.asset, AccountType.SPOT.value, float(b.free), float(b.locked), total, now,
                    float(b.free), float(b.locked), total, now,
                ),
            )
            synced["spot"] += 1
        db.commit()

    margin_balances = await asyncio.to_thread(client.get_margin_balances)
    with managed_db_session() as db:
        for b in margin_balances:
            total = float(b.free) + float(b.locked)
            db.execute(
                """INSERT INTO balances (asset, account_type, free, locked, total, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(asset, account_type)
                   DO UPDATE SET free=?, locked=?, total=?, updated_at=?""",
                (
                    b.asset, AccountType.MARGIN.value, float(b.free), float(b.locked), total, now,
                    float(b.free), float(b.locked), total, now,
                ),
            )
            synced["margin"] += 1
        db.commit()

    earn_balances = await asyncio.to_thread(client.get_earn_positions)
    with managed_db_session() as db:
        for b in earn_balances:
            total = float(b.free) + float(b.locked)
            db.execute(
                """INSERT INTO balances (asset, account_type, free, locked, total, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(asset, account_type)
                   DO UPDATE SET free=?, locked=?, total=?, updated_at=?""",
                (
                    b.asset, AccountType.EARN.value, float(b.free), float(b.locked), total, now,
                    float(b.free), float(b.locked), total, now,
                ),
            )
            synced["earn"] += 1
        db.commit()

    return synced


async def sync_prices() -> int:
    client = _get_binance_client()
    now = datetime.now(timezone.utc)

    all_prices = await asyncio.to_thread(client.get_all_prices)

    with managed_db_session() as db:
        count = 0
        for p in all_prices:
            for quote in QUOTE_ASSETS:
                if p.symbol.endswith(quote):
                    db.execute(
                        """INSERT INTO prices (symbol, price, updated_at)
                           VALUES (?, ?, ?)
                           ON CONFLICT(symbol)
                           DO UPDATE SET price=?, updated_at=?""",
                        (p.symbol, float(p.price), now, float(p.price), now),
                    )
                    count += 1
                    break
        db.commit()

    return count


def _to_usd(quote_qty: float, quote_asset: str, timestamp_ms: int, client, price_cache: dict) -> float:
    """Convert a quote amount to USD, using cache to avoid repeated API calls."""
    if quote_asset in STABLECOINS:
        return quote_qty
    day_key = (quote_asset, timestamp_ms // 86_400_000)
    if day_key not in price_cache:
        price_cache[day_key] = client.get_historical_usd_price(quote_asset, timestamp_ms)
    return quote_qty * price_cache[day_key]


async def sync_trades() -> int:
    client = _get_binance_client()
    now = datetime.now(timezone.utc)

    with managed_db_session() as db:
        held_assets = db.execute(
            "SELECT DISTINCT asset FROM balances WHERE total > 0"
        ).fetchall()

    assets = [row["asset"] for row in held_assets]
    total_synced = 0
    price_cache: dict = {}

    # Get all exchange symbols once (cached on client instance)
    exchange_symbols = await asyncio.to_thread(client.get_symbols_for_asset, assets[0])
    # Warm the cache
    for asset in assets[1:]:
        await asyncio.to_thread(client.get_symbols_for_asset, asset)

    for asset in assets:
        # Discover all trading pairs for this asset
        all_symbols = client.get_symbols_for_asset(asset)
        # Also try standard pairs not in exchange info (e.g., very old pairs)
        for quote in QUOTE_ASSETS:
            sym = f"{asset}{quote}"
            if sym not in all_symbols:
                all_symbols.append(sym)

        for symbol in all_symbols:
            _, quote_asset = _parse_symbol(symbol)
            if not quote_asset:
                continue

            try:
                with managed_db_session() as db:
                    last_trade = db.execute(
                        "SELECT MAX(trade_time) as last_time FROM trades WHERE symbol = ? AND account_type = ?",
                        (symbol, AccountType.SPOT.value),
                    ).fetchone()

                start_time = None
                if last_trade and last_trade["last_time"]:
                    last_dt = datetime.fromisoformat(last_trade["last_time"])
                    start_time = int(last_dt.timestamp() * 1000) + 1

                spot_trades = await asyncio.to_thread(
                    client.get_spot_trades, symbol, start_time
                )

                if spot_trades:
                    with managed_db_session() as db:
                        for t in spot_trades:
                            base, q_asset = _parse_symbol(t.symbol)
                            trade_id = f"spot_{t.id}_{t.symbol}"
                            ts_ms = t.time
                            q_qty = float(t.quoteQty)
                            q_qty_usd = _to_usd(q_qty, q_asset, ts_ms, client, price_cache)
                            db.execute(
                                """INSERT OR IGNORE INTO trades
                                   (id, symbol, base_asset, quote_asset, account_type, side,
                                    price, qty, quote_qty, quote_qty_usd, commission, commission_asset,
                                    trade_time, synced_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    trade_id, t.symbol, base, q_asset,
                                    AccountType.SPOT.value,
                                    TradeSide.BUY.value if t.isBuyer else TradeSide.SELL.value,
                                    float(t.price), float(t.qty), q_qty, q_qty_usd,
                                    float(t.commission), t.commissionAsset,
                                    datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                                    now,
                                ),
                            )
                            total_synced += 1
                        db.commit()
            except Exception as e:
                if "Invalid symbol" not in str(e):
                    logger.warning(f"Error syncing trades for {symbol}: {e}")
                continue

    return total_synced


async def sync_convert_history() -> int:
    """Sync Binance Convert trades as buy/sell records."""
    client = _get_binance_client()
    now = datetime.now(timezone.utc)
    price_cache: dict = {}

    # Start from last synced convert trade, else 2 years back
    with managed_db_session() as db:
        last = db.execute(
            "SELECT MAX(trade_time) as t FROM trades WHERE id LIKE 'convert_%'"
        ).fetchone()
    if last and last["t"]:
        last_dt = datetime.fromisoformat(last["t"]) if isinstance(last["t"], str) else last["t"]
        start_ms = int(last_dt.timestamp() * 1000) + 1
    else:
        start_ms = int((now.timestamp() - 2 * 365 * 24 * 3600) * 1000)  # 2 years back

    end_ms = int(now.timestamp() * 1000)

    records = await asyncio.to_thread(client.get_convert_history, start_ms, end_ms)
    total_synced = 0

    with managed_db_session() as db:
        for r in records:
            if r.get("orderStatus") != "SUCCESS":
                continue

            from_asset = r["fromAsset"]
            to_asset = r["toAsset"]
            from_amount = float(r["fromAmount"])
            to_amount = float(r["toAmount"])
            ts_ms = int(r["createTime"])
            trade_time = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            order_id = str(r["orderId"])

            # BUY side: acquiring to_asset
            if to_asset not in STABLECOINS:
                q_qty_usd = _to_usd(from_amount, from_asset, ts_ms, client, price_cache)
                buy_id = f"convert_buy_{order_id}"
                db.execute(
                    """INSERT OR IGNORE INTO trades
                       (id, symbol, base_asset, quote_asset, account_type, side,
                        price, qty, quote_qty, quote_qty_usd, commission, commission_asset,
                        trade_time, synced_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        buy_id, f"{to_asset}/{from_asset}", to_asset, from_asset,
                        AccountType.SPOT.value, TradeSide.BUY.value,
                        from_amount / to_amount if to_amount else 0,
                        to_amount, from_amount, q_qty_usd,
                        0.0, "",
                        trade_time, now,
                    ),
                )
                total_synced += 1

            # SELL side: disposing from_asset
            if from_asset not in STABLECOINS:
                q_qty_usd = _to_usd(to_amount, to_asset, ts_ms, client, price_cache)
                sell_id = f"convert_sell_{order_id}"
                db.execute(
                    """INSERT OR IGNORE INTO trades
                       (id, symbol, base_asset, quote_asset, account_type, side,
                        price, qty, quote_qty, quote_qty_usd, commission, commission_asset,
                        trade_time, synced_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sell_id, f"{from_asset}/{to_asset}", from_asset, to_asset,
                        AccountType.SPOT.value, TradeSide.SELL.value,
                        to_amount / from_amount if from_amount else 0,
                        from_amount, to_amount, q_qty_usd,
                        0.0, "",
                        trade_time, now,
                    ),
                )
                total_synced += 1

        db.commit()

    return total_synced


def _sync_log_step(sync_id: int, step: str, partial: dict) -> None:
    with managed_db_session() as db:
        db.execute(
            "UPDATE sync_log SET details = ? WHERE id = ?",
            (json.dumps({"step": step, **partial}), sync_id),
        )
        db.commit()


async def sync_all() -> dict:
    now = datetime.now(timezone.utc)

    with managed_db_session() as db:
        db.execute(
            "INSERT INTO sync_log (sync_type, started_at, status, details) VALUES (?, ?, ?, ?)",
            ("full", now, SyncStatus.RUNNING.value, json.dumps({"step": "balances"})),
        )
        db.commit()
        sync_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    partial: dict = {}
    try:
        balance_counts = await sync_balances()
        partial["balances"] = balance_counts
        _sync_log_step(sync_id, "prices", partial)

        price_count = await sync_prices()
        partial["prices_synced"] = price_count
        _sync_log_step(sync_id, "trades", partial)

        trade_count = await sync_trades()
        partial["trades_synced"] = trade_count
        _sync_log_step(sync_id, "converts", partial)

        convert_count = await sync_convert_history()
        partial["converts_synced"] = convert_count

        result = {"status": "completed", **partial}

        with managed_db_session() as db:
            db.execute(
                "UPDATE sync_log SET completed_at = ?, status = ?, details = ? WHERE id = ?",
                (datetime.now(timezone.utc), SyncStatus.COMPLETED.value, json.dumps(result), sync_id),
            )
            db.commit()

        return result
    except Exception as e:
        logger.error(f"Sync failed: {e}")
        with managed_db_session() as db:
            db.execute(
                "UPDATE sync_log SET completed_at = ?, status = ?, details = ? WHERE id = ?",
                (datetime.now(timezone.utc), SyncStatus.FAILED.value,
                 json.dumps({"step": partial.get("step", "unknown"), "error": str(e), **partial}), sync_id),
            )
            db.commit()

        return {"status": "failed", "error": str(e)}


def get_sync_status() -> dict:
    with managed_db_session() as db:
        row = db.execute(
            """SELECT id, sync_type, started_at, completed_at, status, details
               FROM sync_log ORDER BY id DESC LIMIT 1"""
        ).fetchone()

    if not row:
        return {"status": "never"}

    details = json.loads(row["details"]) if row["details"] else {}

    return {
        "id": row["id"],
        "status": row["status"],
        "step": details.get("step"),
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "details": details,
    }


def _get_asset_groups() -> dict[str, list[str]]:
    with managed_db_session() as db:
        rows = db.execute("SELECT group_name, members_json FROM asset_groups").fetchall()

    return {row["group_name"]: json.loads(row["members_json"]) for row in rows}


def _get_current_price(asset: str) -> float:
    lookup = asset[2:] if asset.startswith("LD") and len(asset) > 2 else asset

    with managed_db_session() as db:
        for quote in QUOTE_ASSETS:
            symbol = f"{lookup}{quote}"
            row = db.execute(
                "SELECT price FROM prices WHERE symbol = ?", (symbol,)
            ).fetchone()
            if row:
                return row["price"]

    return 0.0


def _calculate_cost_basis(group_name: str, group_members: list[str], current_qty: float) -> tuple[float, float, bool]:
    """Returns (avg_entry_price, total_cost, is_overridden)."""
    with managed_db_session() as db:
        override = db.execute(
            "SELECT avg_price_usd FROM cost_basis_overrides WHERE asset = ?",
            (group_name,),
        ).fetchone()

    if override:
        avg_entry = override["avg_price_usd"]
        return avg_entry, round(current_qty * avg_entry, 2), True

    total_cost_usd = 0.0
    total_qty_bought = 0.0

    with managed_db_session() as db:
        for member in group_members:
            rows = db.execute(
                "SELECT qty, quote_qty_usd FROM trades WHERE base_asset = ? AND side = ?",
                (member, TradeSide.BUY.value),
            ).fetchall()
            for row in rows:
                total_cost_usd += row["quote_qty_usd"]
                total_qty_bought += row["qty"]

    if total_qty_bought == 0:
        return 0.0, 0.0, False

    avg_entry = total_cost_usd / total_qty_bought
    current_cost = current_qty * avg_entry

    return avg_entry, current_cost, False


def get_cost_basis_override(asset: str) -> dict | None:
    with managed_db_session() as db:
        row = db.execute(
            "SELECT asset, avg_price_usd, notes, source, created_at FROM cost_basis_overrides WHERE asset = ?",
            (asset,),
        ).fetchone()

    if not row:
        return None

    return {
        "asset": row["asset"],
        "avg_price_usd": row["avg_price_usd"],
        "notes": row["notes"],
        "source": row["source"],
        "created_at": row["created_at"],
    }


def set_cost_basis_override(asset: str, avg_price_usd: float, notes: str = "") -> None:
    now = datetime.now(timezone.utc)
    with managed_db_session() as db:
        db.execute(
            """INSERT INTO cost_basis_overrides (asset, avg_price_usd, notes, source, created_at)
               VALUES (?, ?, ?, 'manual', ?)
               ON CONFLICT(asset) DO UPDATE SET avg_price_usd=?, notes=?, created_at=?""",
            (asset, avg_price_usd, notes, now, avg_price_usd, notes, now),
        )
        db.commit()


def delete_cost_basis_override(asset: str) -> None:
    with managed_db_session() as db:
        db.execute("DELETE FROM cost_basis_overrides WHERE asset = ?", (asset,))
        db.commit()


def _get_group_balances(group_members: list[str]) -> list[AssetBalance]:
    balances = []
    with managed_db_session() as db:
        for member in group_members:
            rows = db.execute(
                "SELECT asset, account_type, free, locked, total FROM balances WHERE asset = ? AND total > 0",
                (member,),
            ).fetchall()
            for row in rows:
                balances.append(
                    AssetBalance(
                        asset=row["asset"],
                        account_type=AccountType(row["account_type"]),
                        free=row["free"],
                        locked=row["locked"],
                        total=row["total"],
                    )
                )

    return balances


async def get_portfolio_dashboard() -> PortfolioDashboard:
    asset_groups = _get_asset_groups()

    with managed_db_session() as db:
        all_assets = db.execute(
            "SELECT DISTINCT asset FROM balances WHERE total > 0"
        ).fetchall()

    all_asset_names = {row["asset"] for row in all_assets}

    grouped_assets = set()
    for members in asset_groups.values():
        grouped_assets.update(members)

    for asset in all_asset_names:
        if asset in grouped_assets:
            continue
        base = asset[2:] if asset.startswith("LD") and len(asset) > 2 else asset
        if base != asset and base in asset_groups:
            asset_groups[base].append(asset)
            grouped_assets.add(asset)
        elif base != asset and base in all_asset_names:
            asset_groups.setdefault(base, [base])
            asset_groups[base].append(asset)
            grouped_assets.update([asset, base])
        else:
            asset_groups[asset] = [asset]

    holdings = []
    for group_name, members in asset_groups.items():
        balances = _get_group_balances(members)
        total_qty = sum(b.total for b in balances)

        if total_qty == 0:
            continue

        avg_entry, total_cost, is_overridden = _calculate_cost_basis(group_name, members, total_qty)

        primary_asset = members[0]
        current_price = _get_current_price(primary_asset)

        current_value = total_qty * current_price
        unrealized_pnl = current_value - total_cost if total_cost > 0 else 0.0
        unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

        holdings.append(
            AssetHolding(
                group_name=group_name,
                members=members,
                total_qty=total_qty,
                avg_entry_price=round(avg_entry, 2),
                current_price=round(current_price, 2),
                current_value=round(current_value, 2),
                total_cost=round(total_cost, 2),
                unrealized_pnl=round(unrealized_pnl, 2),
                unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
                balances=balances,
                cost_basis_overridden=is_overridden,
            )
        )

    holdings.sort(key=lambda h: h.current_value, reverse=True)

    total_value = sum(h.current_value for h in holdings)
    total_cost = sum(h.total_cost for h in holdings)
    total_pnl = total_value - total_cost if total_cost > 0 else 0.0
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    with managed_db_session() as db:
        last_sync_row = db.execute(
            "SELECT completed_at FROM sync_log WHERE status = ? ORDER BY id DESC LIMIT 1",
            (SyncStatus.COMPLETED.value,),
        ).fetchone()

    last_sync = last_sync_row["completed_at"] if last_sync_row else None

    return PortfolioDashboard(
        holdings=holdings,
        total_value=round(total_value, 2),
        total_cost=round(total_cost, 2),
        total_pnl=round(total_pnl, 2),
        total_pnl_pct=round(total_pnl_pct, 2),
        last_sync=last_sync,
    )


async def get_asset_detail(group_name: str) -> dict:
    asset_groups = _get_asset_groups()

    if group_name in asset_groups:
        members = asset_groups[group_name]
    else:
        members = [group_name]

    balances = _get_group_balances(members)
    total_qty = sum(b.total for b in balances)
    avg_entry, total_cost, is_overridden = _calculate_cost_basis(group_name, members, total_qty)

    primary_asset = members[0]
    current_price = _get_current_price(primary_asset)
    current_value = total_qty * current_price
    unrealized_pnl = current_value - total_cost if total_cost > 0 else 0.0
    unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

    holding = AssetHolding(
        group_name=group_name,
        members=members,
        total_qty=total_qty,
        avg_entry_price=round(avg_entry, 2),
        current_price=round(current_price, 2),
        current_value=round(current_value, 2),
        total_cost=round(total_cost, 2),
        unrealized_pnl=round(unrealized_pnl, 2),
        unrealized_pnl_pct=round(unrealized_pnl_pct, 2),
        balances=balances,
        cost_basis_overridden=is_overridden,
    )

    trades = []
    with managed_db_session() as db:
        for member in members:
            rows = db.execute(
                """SELECT id, symbol, base_asset, quote_asset, account_type, side,
                          price, qty, quote_qty, commission, commission_asset, trade_time
                   FROM trades WHERE base_asset = ? ORDER BY trade_time DESC""",
                (member,),
            ).fetchall()
            for row in rows:
                trades.append(
                    TradeRecord(
                        id=row["id"],
                        symbol=row["symbol"],
                        base_asset=row["base_asset"],
                        quote_asset=row["quote_asset"],
                        account_type=AccountType(row["account_type"]),
                        side=TradeSide(row["side"]),
                        price=row["price"],
                        qty=row["qty"],
                        quote_qty=row["quote_qty"],
                        commission=row["commission"],
                        commission_asset=row["commission_asset"],
                        trade_time=row["trade_time"],
                    )
                )

    trades.sort(key=lambda t: t.trade_time, reverse=True)

    return {"group_name": group_name, "holding": holding, "trades": trades}
