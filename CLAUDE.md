# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Development Commands

**Start the application:**
From the project root:
```bash
cd app
uv run hypercorn main:app --reload --log-level debug
```

Or using Taskfile:
```bash
task run
```

**Other commands:**
```bash
task test          # Run tests
task lint          # Auto-fix lint issues
task lint-check    # Check for lint issues
task lock          # Update uv.lock after changing pyproject.toml
task install-deps  # Install dependencies
```

## Application Architecture

**Hodl Engine** is a Binance portfolio cost basis tracker and AI-powered financial advisor built with FastAPI. It syncs trade history from Binance, calculates average entry prices, and provides rebalancing suggestions with AI-powered insights.

### Core Architecture

**FastAPI Backend (app/main.py):**
- Serves web application and API endpoints using modular router architecture
- Uses SQLite database for persistence
- Integrates with Anthropic Claude for AI portfolio analysis
- Implements streaming responses for real-time AI chat

**Database Layer (app/db.py):**
- Database initialization with `init_db()`
- Context manager `managed_db_session()` for database sessions
- Asset group seeding with `seed_default_asset_groups()`
- SQLite with `sqlite3.Row` row factory for dict-like access

**Configuration (app/config.py):**
- Environment variable loading via python-dotenv

**Binance Client (app/binance/):**
- `client.py` - Wrapper around `binance-connector` SDK
- `schemas.py` - Pydantic models for Binance API responses
- Synchronous client called via `asyncio.to_thread()` from async services

### Domain-Driven Architecture (app/domains/)

Each domain contains:
- `service.py` - Business logic and database operations
- `router_api.py` - JSON API endpoints
- `router_pages.py` - HTML page rendering
- `schemas.py` - Pydantic models for validation
- `value_objects.py` - Domain enums and constants

**Domains:**
- `portfolio/` - Core portfolio management: sync from Binance, balance tracking, cost basis calculation, holdings dashboard
- `rebalance/` - Stop-loss/take-profit levels, allocation suggestions, rebalancing recommendations
- `advisor/` - AI-powered financial advisor using Claude API with streaming chat, portfolio analysis, sell point suggestions, coin recommendations

### Router Architecture (app/routers/)

Two-layer routing structure:
- `api/app.py` - Aggregates all domain API routers under `/api` prefix
- `pages/app.py` - Aggregates all domain page routers

### Database Schema

- `trades` - Synced trade history from Binance (spot + margin)
- `balances` - Current asset balances across account types (spot, margin, earn)
- `prices` - Cached current prices
- `asset_groups` - Asset consolidation groups (e.g., ETH -> ETH, BETH, WBETH)
- `sync_log` - Sync operation history
- `chats` - AI conversation history

### Key Features

**Portfolio Tracking:**
- Auto-discovers all held assets from Binance
- Syncs balances across spot, margin, and earn accounts
- Pulls trade history for cost basis calculation
- Weighted average entry price calculation
- Asset group consolidation (ETH + BETH + WBETH)

**Rebalancing Engine:**
- Percentage-based stop-loss levels (5%, 10%, 15%)
- Percentage-based take-profit levels (10%, 25%, 50%)
- Allocation comparison vs targets
- BUY/SELL/HOLD suggestions

**AI Financial Advisor:**
- Portfolio analysis (diversification, risk, recommendations)
- Sell point suggestions per asset
- New coin recommendations
- Streaming chat with full portfolio context

### File Structure

```
hodl-engine/
├── app/
│   ├── main.py          # FastAPI app entry point
│   ├── db.py            # SQLite database management
│   ├── config.py        # Environment configuration
│   ├── binance/         # Binance API client layer
│   ├── domains/         # Domain-driven modules
│   │   ├── portfolio/   # Portfolio sync & cost basis
│   │   ├── rebalance/   # Rebalancing suggestions
│   │   └── advisor/     # AI financial advisor
│   ├── routers/         # Router aggregation layer
│   ├── templates/       # Jinja2 HTML templates
│   └── static/          # CSS and frontend assets
├── local_db/            # SQLite database files (gitignored)
└── logs/                # Application logs (gitignored)
```

### Environment Variables

**Required:**
- `BINANCE_API_KEY` - Binance API key (read-only permissions)
- `BINANCE_API_SECRET` - Binance API secret
- `ANTHROPIC_API_KEY` - Anthropic API key for AI advisor

## Prompt Quality Guardrail

If the user's request is vague, underspecified, or contradictory:
* Pause execution.
* Explain briefly what is missing.
* Propose a clearer version of the request.
* Do not guess or fill in gaps silently.

## Rules for Codebase

- All service functions that call the database and all router functions must be asynchronous (`async` keyword)
- For `router_pages.py` files: route definitions returning HTML use format `render_{page_name}_page`
- For `router_api.py` files: route definitions returning JSON use format `{function_name}_endpoint`
- When inserting page links into Jinja templates, use `{{url_for(page_name)}}` instead of HTML paths
- Use existing icon libraries (Font Awesome) before adding new ones

## Coding Style & Best Practices

- Always use Enums (StrEnum) instead of string literals for statuses, types, and categorical values
- Avoid redundant comments — prefer self-documenting code through clear naming
- Private/helper functions use underscore prefix `_function_name`
- Line break before `return` statements in multi-statement functions
- New line at end of files
- Keep files short and focused
- Tests should be independent and minimal
