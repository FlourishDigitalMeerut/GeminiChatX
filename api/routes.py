from fastapi import APIRouter
from pydantic import BaseModel
from api.website_routes import router as website_router
from api.whatsapp_routes import router as whatsapp_router
from api.contact_routes import router as contact_router
# from api.voice_routes import router as voice_router

router = APIRouter(prefix="/api/v1")

class HealthResponse(BaseModel):
    status: str

# Include all route modules
router.include_router(website_router)
router.include_router(whatsapp_router)
router.include_router(contact_router)
# router.include_router(voice_router)


@router.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")