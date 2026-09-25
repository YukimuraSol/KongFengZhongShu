from fastapi import APIRouter, HTTPException

from ..schemas.calc import CalcResult, EmRequest, HpRequest, LinearFitRequest, TwoPointRequest
from ..services.calc_service import calc_em, calc_hp, calc_linear_fit, calc_two_point

router = APIRouter(prefix="/calc", tags=["calc"])


@router.post("/atk-def/two-point", response_model=CalcResult)
def atk_def_two_point(payload: TwoPointRequest) -> CalcResult:
    try:
        return calc_two_point(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/atk-def/linear-fit", response_model=CalcResult)
def atk_def_linear_fit(payload: LinearFitRequest) -> CalcResult:
    try:
        return calc_linear_fit(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/hp", response_model=CalcResult)
def hp(payload: HpRequest) -> CalcResult:
    try:
        return calc_hp(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/em", response_model=CalcResult)
def em(payload: EmRequest) -> CalcResult:
    try:
        return calc_em(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
