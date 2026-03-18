from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def render_portfolio_dashboard_page(request: Request):
    from domains.portfolio import service

    dashboard = await service.get_portfolio_dashboard()

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "dashboard": dashboard},
    )


@router.get("/{group_name}")
async def render_asset_detail_page(request: Request, group_name: str):
    from domains.portfolio import service

    detail = await service.get_asset_detail(group_name)

    return templates.TemplateResponse(
        "asset-detail.html",
        {"request": request, "detail": detail, "group_name": group_name},
    )
