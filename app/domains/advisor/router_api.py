from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from domains.advisor.schemas import AnalysisResponse, ChatMessage

router = APIRouter()


@router.post("/analyze")
async def analyze_portfolio_endpoint() -> AnalysisResponse:
    from domains.advisor import service
    from domains.portfolio import service as portfolio_service

    dashboard = await portfolio_service.get_portfolio_dashboard()
    analysis = await service.get_portfolio_analysis(dashboard)

    return AnalysisResponse(analysis=analysis)


@router.post("/sell-points/{group_name}")
async def sell_points_endpoint(group_name: str) -> AnalysisResponse:
    from domains.advisor import service
    from domains.portfolio import service as portfolio_service

    dashboard = await portfolio_service.get_portfolio_dashboard()
    analysis = await service.get_sell_points(dashboard)

    return AnalysisResponse(analysis=analysis)


@router.post("/coin-suggestions")
async def coin_suggestions_endpoint() -> AnalysisResponse:
    from domains.advisor import service
    from domains.portfolio import service as portfolio_service

    dashboard = await portfolio_service.get_portfolio_dashboard()
    analysis = await service.get_coin_suggestions(dashboard)

    return AnalysisResponse(analysis=analysis)


@router.post("/asset/{group_name}/insights")
async def asset_insights_endpoint(group_name: str) -> AnalysisResponse:
    from domains.advisor import service
    from domains.portfolio import service as portfolio_service

    detail = await portfolio_service.get_asset_detail(group_name)
    analysis = await service.get_asset_insights(
        detail["holding"], detail["trades"]
    )

    return AnalysisResponse(analysis=analysis)


@router.post("/chat")
async def advisor_chat_endpoint(chat_message: ChatMessage):
    from domains.advisor import service
    from domains.portfolio import service as portfolio_service

    dashboard = await portfolio_service.get_portfolio_dashboard()

    async def event_stream():
        async for chunk in service.chat_stream(chat_message.message, dashboard):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
