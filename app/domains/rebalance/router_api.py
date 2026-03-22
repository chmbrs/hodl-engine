from fastapi import APIRouter, HTTPException

from domains.rebalance.schemas import AllocationTargetRequest

router = APIRouter()


@router.get("/suggestions")
async def rebalance_suggestions_endpoint():
    from domains.rebalance import service

    dashboard = await service.get_rebalance_dashboard()

    return dashboard


@router.get("/targets")
async def get_allocation_targets_endpoint():
    from domains.rebalance.service import _get_allocation_targets

    return {"targets": _get_allocation_targets()}


@router.put("/targets")
async def set_allocation_targets_endpoint(body: AllocationTargetRequest):
    from domains.rebalance import service

    if not body.targets:
        raise HTTPException(status_code=400, detail="Targets cannot be empty")

    if any(v < 0 for v in body.targets.values()):
        raise HTTPException(status_code=400, detail="Target percentages cannot be negative")

    total = sum(body.targets.values())
    if abs(total - 1.0) > 0.001:
        raise HTTPException(
            status_code=400,
            detail=f"Targets must sum to 100%. Current sum: {total * 100:.1f}%",
        )

    await service.set_allocation_targets(body.targets)

    return {"status": "ok", "targets": body.targets}


@router.delete("/targets")
async def delete_allocation_targets_endpoint():
    from domains.rebalance import service

    await service.delete_allocation_targets()

    return {"status": "ok"}
