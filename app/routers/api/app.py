from domains.advisor.router_api import router as advisor_api
from domains.portfolio.router_api import router as portfolio_api
from domains.rebalance.router_api import router as rebalance_api
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["api"])
router.include_router(portfolio_api, prefix="/portfolio", tags=["portfolio"])
router.include_router(rebalance_api, prefix="/rebalance", tags=["rebalance"])
router.include_router(advisor_api, prefix="/advisor", tags=["advisor"])
