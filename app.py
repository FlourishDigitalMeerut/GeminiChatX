import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from api.routes import router as api_router
from api.voice_routes import router as voice_router
from api.website_routes import router as website_router  
from api.whatsapp_routes import router as whatsapp_router
from api.contact_routes import router as contact_router
from models.database import create_db_and_tables
from config.settings import BASE_DIR
from api.auth import router as auth_router
from services.mongodb import lifespan_manager
from models.api_keys import BotAPIKey
from api.api_key_routes import router as api_key_router
from api.plivo_routes import router as plivo_router

# Create database tables
create_db_and_tables()


app = FastAPI(
    title="Geminichatx",
    description="This is the API for Geminichatx, a chatbot platform supporting website and WhatsApp and Voice bots.",
    version="1.0.0",
    lifespan=lifespan_manager
)

# Mount static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
# app.include_router(api_router)
app.include_router(auth_router)
app.include_router(api_key_router)
app.include_router(voice_router)
app.include_router(website_router)   
app.include_router(whatsapp_router)
app.include_router(contact_router)
app.include_router(plivo_router)

@app.get("/")
async def root():
    return {"message": "Welcome to GeminiChatX, A Saas platform that provides feature of website and whatsapp AI chatbot(RAG) and voice call bot.", "status": "active"}

# @app.get("/")
# async def serve_frontend():
#     return FileResponse('app4.html')

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)