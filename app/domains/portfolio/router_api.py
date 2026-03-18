from fastapi import APIRouter

router = APIRouter()


@router.post("/sync")
async def sync_portfolio_endpoint():
    from domains.portfolio import service

    result = await service.sync_all()

    return result


@router.get("/holdings")
async def holdings_endpoint():
    from domains.portfolio import service

    dashboard = await service.get_portfolio_dashboard()

    return dashboard


@router.get("/holdings/{group_name}")
async def holding_detail_endpoint(group_name: str):
    from domains.portfolio import service

    detail = await service.get_asset_detail(group_name)

    return detail
