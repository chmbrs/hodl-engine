from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def render_rebalance_page(request: Request):
    from domains.rebalance import service

    dashboard = await service.get_rebalance_dashboard()

    return templates.TemplateResponse(
        "rebalance.html",
        {"request": request, "dashboard": dashboard},
    )
