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

QUOTE_ASSETS = ["USDT", "BUSD", "USDC", "USD"]


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


async def sync_trades() -> int:
    client = _get_binance_client()
    now = datetime.now(timezone.utc)

    with managed_db_session() as db:
        held_assets = db.execute(
            "SELECT DISTINCT asset FROM balances WHERE total > 0"
        ).fetchall()

    assets = [row["asset"] for row in held_assets]
    total_synced = 0

    for asset in assets:
        for quote in QUOTE_ASSETS:
            symbol = f"{asset}{quote}"
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
                            base, quote_asset = _parse_symbol(t.symbol)
                            trade_id = f"spot_{t.id}_{t.symbol}"
                            db.execute(
                                """INSERT OR IGNORE INTO trades
                                   (id, symbol, base_asset, quote_asset, account_type, side,
                                    price, qty, quote_qty, commission, commission_asset,
                                    trade_time, synced_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    trade_id, t.symbol, base, quote_asset,
                                    AccountType.SPOT.value,
                                    TradeSide.BUY.value if t.isBuyer else TradeSide.SELL.value,
                                    float(t.price), float(t.qty), float(t.quoteQty),
                                    float(t.commission), t.commissionAsset,
                                    datetime.fromtimestamp(t.time / 1000, tz=timezone.utc),
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


async def sync_all() -> dict:
    now = datetime.now(timezone.utc)

    with managed_db_session() as db:
        db.execute(
            "INSERT INTO sync_log (sync_type, started_at, status) VALUES (?, ?, ?)",
            ("full", now, SyncStatus.RUNNING.value),
        )
        db.commit()
        sync_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    try:
        balance_counts = await sync_balances()
        price_count = await sync_prices()
        trade_count = await sync_trades()

        result = {
            "status": "completed",
            "balances": balance_counts,
            "prices_synced": price_count,
            "trades_synced": trade_count,
        }

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
                (datetime.now(timezone.utc), SyncStatus.FAILED.value, str(e), sync_id),
            )
            db.commit()

        return {"status": "failed", "error": str(e)}


def _get_asset_groups() -> dict[str, list[str]]:
    with managed_db_session() as db:
        rows = db.execute("SELECT group_name, members_json FROM asset_groups").fetchall()

    return {row["group_name"]: json.loads(row["members_json"]) for row in rows}


def _get_current_price(asset: str) -> float:
    with managed_db_session() as db:
        for quote in QUOTE_ASSETS:
            symbol = f"{asset}{quote}"
            row = db.execute(
                "SELECT price FROM prices WHERE symbol = ?", (symbol,)
            ).fetchone()
            if row:
                return row["price"]

    return 0.0


def _calculate_cost_basis(group_members: list[str]) -> tuple[float, float]:
    total_cost = 0.0
    total_qty_bought = 0.0

    with managed_db_session() as db:
        for member in group_members:
            rows = db.execute(
                "SELECT price, qty, quote_qty FROM trades WHERE base_asset = ? AND side = ?",
                (member, TradeSide.BUY.value),
            ).fetchall()
            for row in rows:
                total_cost += row["quote_qty"]
                total_qty_bought += row["qty"]

    if total_qty_bought == 0:
        return 0.0, 0.0

    avg_entry = total_cost / total_qty_bought

    return avg_entry, total_cost


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
        if asset not in grouped_assets:
            asset_groups[asset] = [asset]

    holdings = []
    for group_name, members in asset_groups.items():
        balances = _get_group_balances(members)
        total_qty = sum(b.total for b in balances)

        if total_qty == 0:
            continue

        avg_entry, total_cost = _calculate_cost_basis(members)

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
    avg_entry, total_cost = _calculate_cost_basis(members)

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
