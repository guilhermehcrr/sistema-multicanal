from anthropic import Anthropic
from app.core.config import settings
from app.services.bot_prompts import HOTEL_BOT_SYSTEM_PROMPT, get_conversation_context_prompt
import logging

logger = logging.getLogger(__name__)

class AIResponder:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
    
    async def generate_response(self, message: str, conversation_history: list, classification: dict):
        """Gera resposta contextualizada usando Claude"""
        try:
            # Monta o contexto completo
            context = get_conversation_context_prompt(conversation_history)
            
            # Prompt específico baseado na classificação
            classification_context = f"\nCLASSIFICAÇÃO: {classification['category']} - {classification['reasoning']}"
            
            # Se for HOT/BOOKING_READY, adiciona instrução especial
            special_instruction = ""
            if classification['category'] in ['HOT', 'BOOKING_READY']:
                special_instruction = "\nIMPORTANTE: O cliente quer reservar. Seja proativo, mas informe que vai conectar com um especialista para confirmar a reserva."
            
            # Monta o prompt completo
            full_prompt = f"""
{HOTEL_BOT_SYSTEM_PROMPT}

{context}

{classification_context}
{special_instruction}

Mensagem atual do cliente: {message}

Responda de forma natural e contextualizada, considerando todo o histórico da conversa.
"""
            
            # Gera resposta com Claude
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=300,
                messages=[
                    {"role": "user", "content": full_prompt}
                ]
            )
            
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Erro gerando resposta com IA: {e}")
            # Fallback para respostas padrão
            if classification['category'] in ['HOT', 'BOOKING_READY']:
                return "Ótimo! Vou conectar você com nosso especialista para finalizar sua reserva. Um momento, por favor."
            return "Desculpe, tive um problema técnico. Como posso ajudar você?"

ai_responder = AIResponder()