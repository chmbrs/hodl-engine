import logging
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from config import ANTHROPIC_API_KEY
from domains.advisor.prompts import (
    ANALYZE_PORTFOLIO_PROMPT,
    COIN_SUGGESTIONS_PROMPT,
    SELL_POINTS_PROMPT,
    SYSTEM_PROMPT,
    build_asset_context,
    build_portfolio_context,
)
from domains.portfolio.schemas import AssetHolding, PortfolioDashboard, TradeRecord

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"


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
