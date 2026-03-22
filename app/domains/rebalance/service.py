import logging
from datetime import datetime, timezone

from db import managed_db_session
from domains.portfolio.schemas import AssetHolding
from domains.rebalance.schemas import (
    AssetRebalanceView,
    RebalanceDashboard,
    RebalanceSuggestion,
    SellTargetLevel,
    StopLossLevel,
    TakeProfitLevel,
)

logger = logging.getLogger(__name__)


def _get_allocation_targets() -> dict[str, float]:
    with managed_db_session() as db:
        rows = db.execute("SELECT asset, target_pct FROM allocation_targets").fetchall()

    return {row["asset"]: row["target_pct"] for row in rows}


async def set_allocation_targets(targets: dict[str, float]) -> None:
    now = datetime.now(timezone.utc)
    with managed_db_session() as db:
        db.execute("DELETE FROM allocation_targets")
        for asset, pct in targets.items():
            db.execute(
                "INSERT INTO allocation_targets (asset, target_pct, updated_at) VALUES (?, ?, ?)",
                (asset, pct, now),
            )
        db.commit()


async def delete_allocation_targets() -> None:
    with managed_db_session() as db:
        db.execute("DELETE FROM allocation_targets")
        db.commit()


STOP_LOSS_TIERS = [
    ("Conservative -5%", 0.05),
    ("Moderate -10%", 0.10),
    ("Aggressive -15%", 0.15),
]

TAKE_PROFIT_TIERS = [
    ("Short-term +10%", 0.10),
    ("Medium-term +25%", 0.25),
    ("Long-term +50%", 0.50),
]

SELL_TARGET_TIERS = [
    ("Break-even", 0.0),
    ("+10% gain", 0.10),
    ("+25% gain", 0.25),
]


def calculate_stop_losses(avg_entry: float) -> list[StopLossLevel]:
    return [
        StopLossLevel(
            price=round(avg_entry * (1 - pct), 2),
            pct_below_entry=pct,
            label=label,
        )
        for label, pct in STOP_LOSS_TIERS
    ]


def calculate_take_profits(avg_entry: float) -> list[TakeProfitLevel]:
    return [
        TakeProfitLevel(
            price=round(avg_entry * (1 + pct), 2),
            pct_above_entry=pct,
            label=label,
        )
        for label, pct in TAKE_PROFIT_TIERS
    ]


def calculate_sell_targets(avg_entry: float, current_price: float) -> list[SellTargetLevel]:
    return [
        SellTargetLevel(
            price=round(avg_entry * (1 + pct), 2),
            label=label,
            pct_above_entry=pct,
            is_reached=current_price >= round(avg_entry * (1 + pct), 2),
        )
        for label, pct in SELL_TARGET_TIERS
    ]


def calculate_rebalance_suggestions(
    holdings: list[AssetHolding],
    targets: dict[str, float] | None = None,
) -> list[RebalanceSuggestion]:
    if not holdings:
        return []

    total_value = sum(h.current_value for h in holdings)
    if total_value == 0:
        return []

    if targets is None:
        equal_pct = 1.0 / len(holdings)
        targets = {h.group_name: equal_pct for h in holdings}

    suggestions = []
    threshold = 0.02

    for holding in holdings:
        current_pct = holding.current_value / total_value
        target_pct = targets.get(holding.group_name)

        # Asset not in targets → treat as unmanaged, always HOLD
        if target_pct is None:
            action = "HOLD"
            value_diff = 0.0
            qty = 0.0
            target_pct = current_pct  # show current as target so diff is 0
        else:
            diff = current_pct - target_pct
            if diff > threshold:
                action = "SELL"
                value_diff = diff * total_value
                qty = value_diff / holding.current_price if holding.current_price > 0 else 0
            elif diff < -threshold:
                action = "BUY"
                value_diff = abs(diff) * total_value
                qty = value_diff / holding.current_price if holding.current_price > 0 else 0
            else:
                action = "HOLD"
                value_diff = 0.0
                qty = 0.0

        if holding.total_qty > 0:
            target_price = (target_pct * total_value) / holding.total_qty
        else:
            target_price = 0.0

        suggestions.append(
            RebalanceSuggestion(
                group_name=holding.group_name,
                current_allocation_pct=round(current_pct * 100, 2),
                target_allocation_pct=round(target_pct * 100, 2),
                action=action,
                suggested_qty=round(qty, 6),
                suggested_value_usdt=round(value_diff, 2),
                target_price=round(target_price, 4),
            )
        )

    return suggestions


async def get_rebalance_dashboard() -> RebalanceDashboard:
    from domains.portfolio import service as portfolio_service

    dashboard = await portfolio_service.get_portfolio_dashboard()

    persisted_targets = _get_allocation_targets()
    targets = persisted_targets if persisted_targets else None

    suggestions = calculate_rebalance_suggestions(dashboard.holdings, targets)

    if not persisted_targets and dashboard.holdings:
        equal_pct = 1.0 / len(dashboard.holdings)
        resolved_targets = {h.group_name: equal_pct for h in dashboard.holdings}
    else:
        resolved_targets = persisted_targets

    asset_views = []
    for holding in dashboard.holdings:
        if holding.avg_entry_price > 0:
            stop_losses = calculate_stop_losses(holding.avg_entry_price)
            take_profits = calculate_take_profits(holding.avg_entry_price)
            sell_targets = calculate_sell_targets(holding.avg_entry_price, holding.current_price)
        else:
            stop_losses = []
            take_profits = []
            sell_targets = []

        asset_views.append(
            AssetRebalanceView(
                holding=holding,
                stop_losses=stop_losses,
                take_profits=take_profits,
                sell_targets=sell_targets,
            )
        )

    return RebalanceDashboard(
        suggestions=suggestions,
        asset_views=asset_views,
        total_portfolio_value=dashboard.total_value,
        allocation_targets=resolved_targets,
    )
