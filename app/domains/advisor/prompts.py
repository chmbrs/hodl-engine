from domains.portfolio.schemas import AssetHolding, PortfolioDashboard, TradeRecord

SYSTEM_PROMPT = """You are an expert crypto portfolio advisor with deep knowledge of cryptocurrency markets, \
technical analysis, risk management, and portfolio theory. You have access to the user's real Binance portfolio data.

Your role:
- Analyze portfolio composition, diversification, and risk exposure
- Suggest entry/exit strategies, stop-loss levels, and take-profit targets
- Recommend rebalancing actions based on market conditions and portfolio goals
- Identify potential new assets that complement the existing portfolio
- Provide insights on cost basis optimization and tax-efficient strategies

Guidelines:
- Be specific with numbers, prices, and percentages
- Reference the user's actual holdings and entry prices in your analysis
- Consider correlation between assets when making recommendations
- Always explain the reasoning behind suggestions
- Disclaimer: This is informational analysis, not financial advice. The user makes all final decisions.

Current portfolio data is provided below."""


def build_portfolio_context(dashboard: PortfolioDashboard) -> str:
    lines = [
        "## Current Portfolio Snapshot",
        f"Total Value: ${dashboard.total_value:,.2f}",
        f"Total Cost Basis: ${dashboard.total_cost:,.2f}",
        f"Total P&L: ${dashboard.total_pnl:,.2f} ({dashboard.total_pnl_pct:.2f}%)",
        "",
        "### Holdings:",
    ]

    for h in dashboard.holdings:
        lines.append(
            f"- **{h.group_name}** ({', '.join(h.members)}): "
            f"{h.total_qty:.6f} units | "
            f"Avg Entry: ${h.avg_entry_price:,.2f} | "
            f"Current: ${h.current_price:,.2f} | "
            f"Value: ${h.current_value:,.2f} | "
            f"P&L: ${h.unrealized_pnl:,.2f} ({h.unrealized_pnl_pct:.2f}%)"
        )
        if len(h.balances) > 1:
            for bal in h.balances:
                lines.append(
                    f"  - {bal.asset} ({bal.account_type}): {bal.total:.8f}"
                )

    return "\n".join(lines)


def build_asset_context(holding: AssetHolding, trades: list[TradeRecord]) -> str:
    lines = [
        f"## {holding.group_name} Detail",
        f"Members: {', '.join(holding.members)}",
        f"Total Qty: {holding.total_qty:.6f}",
        f"Avg Entry Price: ${holding.avg_entry_price:,.2f}",
        f"Current Price: ${holding.current_price:,.2f}",
        f"Current Value: ${holding.current_value:,.2f}",
        f"Total Cost: ${holding.total_cost:,.2f}",
        f"Unrealized P&L: ${holding.unrealized_pnl:,.2f} ({holding.unrealized_pnl_pct:.2f}%)",
        "",
        "### Balance Breakdown:",
    ]

    for bal in holding.balances:
        lines.append(f"- {bal.asset} ({bal.account_type}): {bal.total:.8f}")

    lines.append("")
    lines.append(f"### Recent Trades (last {min(len(trades), 20)}):")

    for trade in trades[:20]:
        lines.append(
            f"- {trade.trade_time.strftime('%Y-%m-%d %H:%M')} | "
            f"{trade.side} {trade.qty:.6f} {trade.base_asset} @ ${trade.price:,.2f} | "
            f"Total: ${trade.quote_qty:,.2f} ({trade.account_type})"
        )

    return "\n".join(lines)


ANALYZE_PORTFOLIO_PROMPT = """Analyze this portfolio and provide:
1. Overall portfolio health assessment (diversification, concentration risk)
2. Top strengths and weaknesses
3. Risk exposure analysis
4. Key observations about entry prices vs current prices
5. Actionable recommendations (2-3 specific actions)

Be concise but specific. Reference actual numbers from the portfolio."""


SELL_POINTS_PROMPT = """Based on the portfolio data, suggest specific sell points for each major holding:
1. Partial profit-taking levels (where to take some profits)
2. Stop-loss levels (where to cut losses)
3. DCA-out strategy (how to gradually reduce positions)
4. Consider the entry price and current price relationship

For each suggestion, explain the reasoning. Be specific with price levels."""


COIN_SUGGESTIONS_PROMPT = """Based on the current portfolio composition, suggest new assets to consider:
1. Identify gaps in the portfolio (missing sectors, underweight categories)
2. Suggest 3-5 specific assets that would improve diversification
3. For each suggestion, explain why it complements the existing holdings
4. Consider correlation with current holdings
5. Suggest allocation percentages

Focus on quality over quantity. Only suggest assets available on Binance."""
