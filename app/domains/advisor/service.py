import logging
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from anthropic import AsyncAnthropic
from config import ANTHROPIC_API_KEY
from db import managed_db_session
from domains.advisor.schemas import AnalysisSnapshot
from domains.advisor.prompts import (
    ALLOCATION_TARGETS_PROMPT,
    ANALYZE_PORTFOLIO_PROMPT,
    COIN_SUGGESTIONS_PROMPT,
    SELL_POINTS_PROMPT,
    SYSTEM_PROMPT,
    build_asset_context,
    build_portfolio_context,
)
from domains.portfolio.schemas import AssetHolding, PortfolioDashboard, TradeRecord

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"


def _get_client() -> AsyncAnthropic:
    return AsyncAnthropic(api_key=ANTHROPIC_API_KEY)


async def get_portfolio_analysis(dashboard: PortfolioDashboard) -> str:
    client = _get_client()
    context = build_portfolio_context(dashboard)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT + "\n\n" + context,
        messages=[{"role": "user", "content": ANALYZE_PORTFOLIO_PROMPT}],
    )

    return response.content[0].text


async def get_sell_points(dashboard: PortfolioDashboard) -> str:
    client = _get_client()
    context = build_portfolio_context(dashboard)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT + "\n\n" + context,
        messages=[{"role": "user", "content": SELL_POINTS_PROMPT}],
    )

    return response.content[0].text


async def get_coin_suggestions(dashboard: PortfolioDashboard) -> str:
    client = _get_client()
    context = build_portfolio_context(dashboard)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT + "\n\n" + context,
        messages=[{"role": "user", "content": COIN_SUGGESTIONS_PROMPT}],
    )

    return response.content[0].text


async def get_asset_insights(
    holding: AssetHolding, trades: list[TradeRecord]
) -> str:
    client = _get_client()
    context = build_asset_context(holding, trades)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT + "\n\n" + context,
        messages=[
            {
                "role": "user",
                "content": f"Provide a detailed analysis of my {holding.group_name} position. "
                "Include entry price evaluation, current status, and specific action recommendations.",
            }
        ],
    )

    return response.content[0].text


async def get_allocation_suggestion(
    dashboard: PortfolioDashboard, market_context: str = ""
) -> str:
    client = _get_client()
    context = build_portfolio_context(dashboard)

    user_content = ALLOCATION_TARGETS_PROMPT
    if market_context.strip():
        user_content += f"\n\n## Market Context (from user)\n{market_context.strip()}"

    response = await client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=SYSTEM_PROMPT + "\n\n" + context,
        messages=[{"role": "user", "content": user_content}],
    )

    return response.content[0].text


async def chat_stream(
    message: str, dashboard: PortfolioDashboard
) -> AsyncIterator[str]:
    client = _get_client()
    context = build_portfolio_context(dashboard)

    async with client.messages.stream(
        model=MODEL,
        max_tokens=2000,
        system=SYSTEM_PROMPT + "\n\n" + context,
        messages=[{"role": "user", "content": message}],
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def save_analysis(label: str, content: str) -> AnalysisSnapshot:
    now = datetime.now(timezone.utc)
    with managed_db_session() as db:
        cursor = db.execute(
            "INSERT INTO analysis_snapshots (label, content, created_at) VALUES (?, ?, ?)",
            (label, content, now),
        )
        db.commit()
        row = db.execute(
            "SELECT id, label, content, created_at FROM analysis_snapshots WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return AnalysisSnapshot(
        id=row["id"],
        label=row["label"],
        content=row["content"],
        created_at=row["created_at"],
    )


async def get_analysis_history() -> list[AnalysisSnapshot]:
    with managed_db_session() as db:
        rows = db.execute(
            "SELECT id, label, content, created_at FROM analysis_snapshots ORDER BY created_at DESC"
        ).fetchall()

    return [
        AnalysisSnapshot(
            id=row["id"],
            label=row["label"],
            content=row["content"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


async def delete_analysis(snapshot_id: int) -> None:
    with managed_db_session() as db:
        db.execute("DELETE FROM analysis_snapshots WHERE id = ?", (snapshot_id,))
        db.commit()
