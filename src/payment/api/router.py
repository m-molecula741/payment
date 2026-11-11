from fastapi import APIRouter, Depends

from payment.api.deps import require_api_key
from payment.api.v1.payments import router as payments_router

api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])
api_router.include_router(payments_router)
