from app.core.database_simple import db
from app.services.lead_classifier import classifier
from app.integrations.whatsapp.megaapi_client import megaapi
from app.services.ai_responder import ai_responder
import logging
import json

logger = logging.getLogger(__name__)

class MessageProcessor:
    async def process_message(self, data: dict):
        """Processa mensagem recebida do webhook"""
        try:
            logger.info(f"Dados recebidos para processar: {data}")
            
            # Verifica se é mensagem válida
            if not data.get('message'):
                logger.info("Sem mensagem para processar")
                return None
                
            # Ignorar mensagens enviadas por nós
            if data.get('key', {}).get('fromMe'):
                logger.info("Ignorando mensagem enviada por nós")
                return None
            
            # Extrair informações
            phone = data.get('key', {}).get('remoteJid', '').replace('@s.whatsapp.net', '')
            text = data.get('message', {}).get('conversation', '')
            user_name = data.get('pushName', '')
            
            if not text:
                logger.info("Sem texto na mensagem")
                return None
            
            logger.info(f"Processando: {phone} ({user_name}) - {text}")
            
            # 1. Classificar mensagem
            classification = await classifier.classify(text)
            logger.info(f"Classificação: {classification}")
            
            # 2. Buscar ou criar conversa
            conversation = await self.get_or_create_conversation(phone)
            
            # 3. Buscar histórico da conversa
            conversation_history = await self.get_conversation_history(conversation['id'])
            
            # 4. Salvar mensagem recebida
            message_saved = db.insert('messages', {
                'conversation_id': conversation['id'],
                'content': text,
                'direction': 'inbound',
                'sender_type': 'lead'
            })
            
            # 5. Gerar resposta inteligente com contexto
            response = await ai_responder.generate_response(
                text, 
                conversation_history,
                classification
            )
            
            # 6. Se for HOT/BOOKING_READY, criar handoff
            if classification['category'] in ['HOT', 'BOOKING_READY']:
                db.insert('handoff_queue', {
                    'conversation_id': conversation['id'],
                    'priority': 'HIGH',
                    'reason': f"Lead {classification['category']}: {classification.get('reasoning', '')}"
                })
                logger.info("Handoff criado para atendimento humano")
            
            # 7. Enviar resposta via WhatsApp
            if response:
                await megaapi.send_message(phone, response)
                
                # Salvar resposta enviada no banco
                db.insert('messages', {
                    'conversation_id': conversation['id'],
                    'content': response,
                    'direction': 'outbound', 
                    'sender_type': 'bot'
                })
            
            return {
                'conversation_id': conversation['id'],
                'classification': classification,
                'response': response
            }
            
        except Exception as e:
            logger.error(f"Erro processando mensagem: {e}")
            return None
    
    async def get_conversation_history(self, conversation_id: str):
        """Busca histórico de mensagens da conversa"""
        try:
            # Buscar últimas 20 mensagens
            messages = db.select('messages', {'conversation_id': conversation_id})
            
            # Ordenar por data (assumindo que tem created_at)
            messages_sorted = sorted(messages, key=lambda x: x.get('created_at', ''))
            
            return messages_sorted
        except Exception as e:
            logger.error(f"Erro buscando histórico: {e}")
            return []
    
    async def get_or_create_conversation(self, phone: str):
        """Busca ou cria uma conversa"""
        conversations = db.select('conversations', {
            'channel_identifier': phone,
            'status': 'active'
        })
        
        if conversations:
            return conversations[0]
        
        return db.insert('conversations', {
            'channel_type': 'whatsapp',
            'channel_identifier': phone,
            'status': 'active'
        })
    
    async def decide_action(self, classification: dict, text: str, conversation: dict):
        """Método mantido por compatibilidade mas não é mais usado"""
        pass

processor = MessageProcessor()