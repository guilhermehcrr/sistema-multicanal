import httpx
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class MegaAPIClient:
    def __init__(self):
        self.instance = settings.megaapi_instance
        self.token = settings.megaapi_token
        self.base_url = "https://apinocode01.megaapi.com.br/rest"
    
    async def send_message(self, phone: str, message: str):
        """Envia mensagem via MegaAPI"""
        try:
            if not self.instance or not self.token or self.instance == "" or self.token == "":
                logger.info(f"[SIMULADO] Enviando para {phone}: {message}")
                return {"status": "simulated"}
            
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            # Formata número com @s.whatsapp.net
            if '@' not in phone:
                if not phone.startswith('55'):
                    phone = f"55{phone}"
                phone = f"{phone}@s.whatsapp.net"
            
            # FORMATO CORRETO - aninhado em messageData
            data = {
                "messageData": {
                    "to": phone,
                    "text": message
                }
            }
            
            # URL com /text no final
            url = f"{self.base_url}/sendMessage/{self.instance}/text"
            
            logger.info(f"Enviando para: {phone}")
            logger.info(f"Body: {data}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=data,
                    timeout=30.0
                )
                
                logger.info(f"Response Status: {response.status_code}")
                
                if response.status_code in [200, 201]:
                    logger.info(f"✅ Mensagem enviada com sucesso!")
                    return response.json() if response.text else {"status": "sent"}
                else:
                    logger.error(f"❌ Erro: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Erro: {e}")
            return None

megaapi = MegaAPIClient()