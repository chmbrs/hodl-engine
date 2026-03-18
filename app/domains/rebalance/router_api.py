from fastapi import APIRouter

router = APIRouter()


@router.get("/suggestions")
async def rebalance_suggestions_endpoint():
    from domains.rebalance import service

    dashboard = await service.get_rebalance_dashboard()

    return dashboard
