# app/main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.services.message_processor import processor
import logging
import asyncio

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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

# ============================================
# ENDPOINTS PRINCIPAIS
# ============================================
@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "status": "running",
        "version": "1.0.0",
        "channels": {
            "whatsapp": "active",
            "email": "active" if hasattr(settings, 'email_address') and settings.email_address else "inactive",
            "instagram": "active" if hasattr(settings, 'instagram_enabled') and settings.instagram_enabled else "inactive"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ============================================
# WEBHOOK WHATSAPP
# ============================================
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """Recebe mensagens do MegaAPI"""
    try:
        data = await request.json()
        logger.info(f"Webhook recebido: {data}")
        
        # Debug temporário para ver ID do grupo (remover depois)
        remote_jid = data.get('key', {}).get('remoteJid', '')
        if '@g.us' in remote_jid:
            logger.info(f"🎯🎯🎯 ID DO GRUPO: {remote_jid} 🎯🎯🎯")
        
        # Processar mensagem
        result = await processor.process_message(data)
        
        if result:
            logger.info(f"Mensagem processada: {result}")
            return {"status": "processed", "result": result}
        
        return {"status": "ignored"}
        
    except Exception as e:
        logger.error(f"Erro no webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# STARTUP - Inicializa todos os monitores
# ============================================
@app.on_event("startup")
async def startup_event():
    """Inicia todos os monitores configurados"""
    
    logger.info("=" * 50)
    logger.info("INICIANDO SISTEMA MULTI-CANAL")
    logger.info("=" * 50)
    
    # ========== MONITOR DE EMAIL ==========
    email_started = False
    try:
        if hasattr(settings, 'email_address') and settings.email_address:
            from app.services.email_monitor import email_monitor
            asyncio.create_task(email_monitor.start_monitoring())
            logger.info("✅ Monitor de EMAIL iniciado")
            logger.info(f"   📧 Email: {settings.email_address}")
            email_started = True
        else:
            logger.info("⏭️  Email não configurado - pulando")
    except ImportError as e:
        logger.error(f"❌ Erro importando módulo de email: {e}")
    except Exception as e:
        logger.error(f"❌ Erro iniciando email: {e}")
    
    # ========== MONITOR DO INSTAGRAM ==========
    instagram_started = False
    try:
        # Verificar configuração
        if not hasattr(settings, 'instagram_enabled'):
            logger.info("⏭️  Instagram: Configuração 'instagram_enabled' não encontrada")
        elif not settings.instagram_enabled:
            logger.info("⏭️  Instagram desabilitado (instagram_enabled=false)")
        else:
            logger.info("🔍 Iniciando Instagram...")
            
            # Importar módulos
            from app.integrations.instagram.instagram_client import instagram_client
            from app.services.instagram_monitor import instagram_monitor
            
            if instagram_monitor and instagram_client:
                asyncio.create_task(instagram_monitor.start_monitoring())
                logger.info("✅ Monitor do INSTAGRAM iniciado")
                logger.info(f"   📸 Usuário: @{settings.instagram_username}")
                logger.info(f"   ⏱️  Intervalo: {settings.instagram_check_interval}s")
                instagram_started = True
            else:
                logger.error("❌ Instagram: Monitor ou cliente é None")
                
    except ImportError as e:
        logger.error(f"❌ Erro importando módulo Instagram: {e}")
    except Exception as e:
        logger.error(f"❌ Erro iniciando Instagram: {e}")
    
    # ========== RESUMO ==========
    logger.info("=" * 50)
    logger.info("SISTEMA INICIADO - Canais Ativos:")
    logger.info(f"  📱 WhatsApp: ✅ Ativo (webhook)")
    logger.info(f"  📧 Email: {'✅ Ativo' if email_started else '❌ Inativo'}")
    logger.info(f"  📸 Instagram: {'✅ Ativo' if instagram_started else '❌ Inativo'}")
    logger.info("=" * 50)

# ============================================
# ENDPOINTS DE TESTE E STATUS
# ============================================
@app.get("/api/status")
async def get_system_status():
    """Retorna status detalhado de todos os canais"""
    status = {
        "system": "running",
        "channels": {
            "whatsapp": {
                "status": "active",
                "type": "webhook",
                "details": "MegaAPI webhook configurado"
            },
            "email": {
                "status": "inactive",
                "type": "monitor",
                "details": "Não configurado"
            },
            "instagram": {
                "status": "inactive",
                "type": "monitor",
                "details": "Não configurado"
            }
        }
    }
    
    # Verificar Email
    try:
        if hasattr(settings, 'email_address') and settings.email_address:
            from app.services.email_monitor import email_monitor
            status["channels"]["email"] = {
                "status": "active",
                "type": "monitor",
                "details": f"Monitorando: {settings.email_address}",
                "check_interval": f"{settings.email_check_interval}s"
            }
    except:
        pass
    
    # Verificar Instagram
    try:
        if hasattr(settings, 'instagram_enabled') and settings.instagram_enabled:
            from app.services.instagram_monitor import instagram_monitor
            if instagram_monitor:
                status["channels"]["instagram"] = {
                    "status": "active",
                    "type": "monitor",
                    "details": f"Monitorando: @{settings.instagram_username}",
                    "check_interval": f"{settings.instagram_check_interval}s"
                }
    except:
        pass
    
    return status

@app.get("/api/email/test")
async def test_email_connection():
    """Testa conexão com email"""
    try:
        from app.services.email_monitor import email_monitor
        mail = email_monitor.connect_imap()
        if mail:
            mail.logout()
            return {
                "status": "success",
                "message": "Conexão com email funcionando",
                "email": settings.email_address
            }
        return {"status": "error", "message": "Não foi possível conectar"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/instagram/test")
async def test_instagram_connection():
    """Testa conexão com Instagram"""
    try:
        from app.services.instagram_monitor import instagram_monitor
        if instagram_monitor and instagram_monitor.client:
            return {
                "status": "success",
                "message": "Instagram conectado",
                "username": settings.instagram_username
            }
        return {"status": "error", "message": "Instagram não configurado"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/test/message")
async def test_message(channel: str, message: str):
    """Endpoint para testar processamento de mensagem em qualquer canal"""
    try:
        if channel == "whatsapp":
            # Simular mensagem WhatsApp
            from app.services.message_processor import processor
            result = await processor.process_message({
                "key": {"remoteJid": "5511999999999@s.whatsapp.net", "fromMe": False},
                "message": {"conversation": message},
                "pushName": "Teste"
            })
            return {"status": "success", "result": result}
            
        elif channel == "email":
            # Simular email
            from app.services.email_monitor import email_monitor
            await email_monitor.process_email(
                "teste@example.com",
                "Teste de Email",
                message,
                "test_001"
            )
            return {"status": "success", "message": "Email processado"}
            
        elif channel == "instagram":
            # Simular DM Instagram
            from app.services.instagram_monitor import instagram_monitor
            await instagram_monitor.process_instagram_message({
                "username": "teste_user",
                "message": message,
                "thread_id": "test_thread",
                "timestamp": "2024-01-01"
            })
            return {"status": "success", "message": "Instagram processado"}
            
        else:
            return {"status": "error", "message": "Canal inválido"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============================================
# SHUTDOWN - Limpa recursos
# ============================================
@app.on_event("shutdown")
async def shutdown_event():
    """Limpa recursos ao desligar"""
    logger.info("🔴 Desligando sistema...")
    
    # Aqui você pode adicionar limpeza de recursos se necessário
    # Por exemplo: fechar conexões, salvar estados, etc.
    
    logger.info("👋 Sistema desligado com sucesso")