from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

router = APIRouter()


@router.post("/sync")
async def sync_portfolio_endpoint(background_tasks: BackgroundTasks):
    from domains.portfolio import service

    background_tasks.add_task(service.sync_all)

    return {"status": "started"}


@router.get("/sync/status")
async def sync_status_endpoint():
    from domains.portfolio import service

    return service.get_sync_status()


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


class OverrideRequest(BaseModel):
    avg_price_usd: float
    notes: str = ""


@router.get("/assets/{asset}/override")
async def get_cost_basis_override_endpoint(asset: str):
    from domains.portfolio import service

    override = service.get_cost_basis_override(asset)

    return override or {}


@router.post("/assets/{asset}/override")
async def set_cost_basis_override_endpoint(asset: str, body: OverrideRequest):
    from domains.portfolio import service

    if body.avg_price_usd <= 0:
        raise HTTPException(status_code=400, detail="avg_price_usd must be positive")

    service.set_cost_basis_override(asset, body.avg_price_usd, body.notes)

    return {"status": "ok", "asset": asset, "avg_price_usd": body.avg_price_usd}


@router.delete("/assets/{asset}/override")
async def delete_cost_basis_override_endpoint(asset: str):
    from domains.portfolio import service

    service.delete_cost_basis_override(asset)

    return {"status": "ok", "asset": asset}
