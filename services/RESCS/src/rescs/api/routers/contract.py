"""Contract discovery endpoint for C.O.R.E."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from rescs.contract import build_contract
from rescs.security import require_api_key

router = APIRouter(
    prefix="/contract",
    tags=["contract"],
    dependencies=[Depends(require_api_key)],
)


@router.get("")
def get_contract(request: Request) -> dict[str, Any]:
    return build_contract(request.app.state.settings)
