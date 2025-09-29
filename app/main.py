from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.services.message_processor import processor
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Criar app
app = FastAPI(
    title=settings.app_name,
    debug=settings.debug
)

# CORS para permitir requisições do frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Recebe mensagens do MegaAPI"""
    try:
        data = await request.json()
        logger.info(f"Webhook recebido: {data}")
        
        # Processar mensagem
        result = await processor.process_message(data)
        
        if result:
            logger.info(f"Mensagem processada: {result}")
            return {"status": "processed", "result": result}
        
        return {"status": "ignored"}
        
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))