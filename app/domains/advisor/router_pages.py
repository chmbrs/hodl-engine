from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/")
async def render_advisor_page(request: Request):
    return templates.TemplateResponse(
        "advisor.html",
        {"request": request},
    )
