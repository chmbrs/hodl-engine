from domains.advisor.router_pages import router as advisor_pages
from domains.portfolio.router_pages import router as portfolio_pages
from domains.rebalance.router_pages import router as rebalance_pages
from fastapi import APIRouter

router = APIRouter(include_in_schema=False)
router.include_router(portfolio_pages, prefix="/portfolio")
router.include_router(rebalance_pages, prefix="/rebalance")
router.include_router(advisor_pages, prefix="/advisor")
