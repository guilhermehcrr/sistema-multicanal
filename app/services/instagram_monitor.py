# app/services/instagram_monitor.py

import asyncio
from datetime import datetime
from typing import Dict, List, Optional
import logging

from app.core.config import settings
from app.core.database_simple import db
from app.services.lead_classifier import classifier
from app.services.ai_responder import ai_responder
from app.services.vendor_rotation import vendor_rotation

logger = logging.getLogger(__name__)

class InstagramMonitor:
    def __init__(self):
        """Inicializa o monitor do Instagram"""
        # Importar o cliente aqui para evitar import circular
        from app.integrations.instagram.instagram_client import instagram_client
        
        self.client = instagram_client
        self.check_interval = getattr(settings, 'instagram_check_interval', 120)
        self.processed_messages = set()  # IDs já processados nesta sessão
        logger.info("Monitor Instagram inicializado")
        
    async def start_monitoring(self):
        """Inicia monitoramento contínuo do Instagram"""
        if not self.client:
            logger.warning("Cliente Instagram não disponível - monitor desabilitado")
            return
            
        logger.info(f"📸 Iniciando monitor do Instagram (intervalo: {self.check_interval}s)")
        logger.info(f"   Usuário: @{settings.instagram_username}")
        
        while True:
            try:
                await self.check_messages()
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                logger.info("Monitor Instagram cancelado")
                break
                
            except Exception as e:
                logger.error(f"Erro no monitor Instagram: {e}")
                # Espera mais tempo em caso de erro
                await asyncio.sleep(self.check_interval * 2)
    
    async def check_messages(self):
        """Verifica e processa novas mensagens"""
        try:
            logger.debug("🔍 Verificando mensagens Instagram...")
            
            # Buscar mensagens não processadas
            messages = await self.client.get_unread_messages()
            
            if messages:
                logger.info(f"📊 {len(messages)} mensagens novas encontradas")
            
            for msg_data in messages:
                try:
                    # Processar cada mensagem
                    await self.process_instagram_message(msg_data)
                    
                    # Pequeno delay entre processamentos
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Erro processando mensagem individual: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Erro verificando mensagens Instagram: {e}")
    
    async def process_instagram_message(self, msg_data: Dict):
        """Processa uma mensagem do Instagram (igual WhatsApp/Email)"""
        try:
            username = msg_data.get('username', 'unknown')
            message = msg_data.get('message', '')
            thread_id = msg_data.get('thread_id')
            
            # Log da mensagem recebida
            logger.info(f"📸 Nova mensagem Instagram de @{username}")
            logger.info(f"   Mensagem: {message[:100]}{'...' if len(message) > 100 else ''}")
            
            # 1. Classificar mensagem
            classification = await classifier.classify(message)
            logger.info(f"   Classificação: {classification['category']} ({classification['confidence']*100:.0f}%)")
            
            # 2. Buscar ou criar conversa
            conversation = await self.get_or_create_conversation(username, thread_id)
            
            # 3. Buscar histórico de conversas
            history = await self.get_conversation_history(conversation['id'])
            
            # 4. Salvar mensagem recebida no banco
            db.insert('messages', {
                'conversation_id': conversation['id'],
                'content': message,
                'direction': 'inbound',
                'sender_type': 'lead',
                
            })
            
            # 5. Gerar resposta com IA
            response = await ai_responder.generate_response(
                message,
                history,
                classification
            )
            
            # 6. Se for HOT/BOOKING_READY, notificar vendedor
            if classification['category'] in ['HOT', 'BOOKING_READY']:
                logger.info(f"🔥 Lead QUENTE detectado! Notificando vendedor...")
                
                # Criar handoff
                db.insert('handoff_queue', {
                    'conversation_id': conversation['id'],
                    'priority': 'HIGH',
                    'reason': f"Instagram {classification['category']}: {classification.get('reasoning', '')}",
                    'channel': 'instagram'
                })
                
                # Notificar grupo WhatsApp com vendedor designado
                notification = await vendor_rotation.notify_group_hot_lead(
                    phone=f"@{username}",  # Username do Instagram
                    message=f"[INSTAGRAM] {message[:200]}{'...' if len(message) > 200 else ''}",
                    classification=classification,
                    conversation_id=conversation['id'],
                    channel='instagram'
                )
                
                vendor_name = notification.get('vendor', 'nossa equipe')
                logger.info(f"   Vendedor designado: {vendor_name}")
                
                # Resposta personalizada informando o vendedor
                response = f"""Perfeito! 🎯

Já acionei {vendor_name}, nosso(a) especialista em reservas.
{vendor_name} vai entrar em contato aqui pelo Instagram em instantes!

Por favor, aguarde só um minutinho... ⏰"""
            
            # 7. Enviar resposta via Instagram
            if response and thread_id:
                success = await self.client.send_message(thread_id, response)
                
                if success:
                    logger.info(f"✅ Resposta enviada para @{username}")
                else:
                    logger.error(f"❌ Falha ao enviar resposta para @{username}")
            
            # 8. Salvar resposta no banco
            db.insert('messages', {
                'conversation_id': conversation['id'],
                'content': response,
                'direction': 'outbound',
                'sender_type': 'bot',
             
            })
            
            # 9. Marcar como lida (opcional)
            if thread_id:
                await self.client.mark_as_read(thread_id)
            
            logger.info(f"✅ Mensagem Instagram de @{username} processada com sucesso")
            
        except Exception as e:
            logger.error(f"Erro processando mensagem Instagram: {e}")
            logger.error(f"Dados da mensagem: {msg_data}")
    
    async def get_or_create_conversation(self, username: str, thread_id: str) -> Dict:
      """Busca ou cria conversa do Instagram"""
      try:
          # Buscar conversa existente
          conversations = db.select('conversations', {
              'channel_identifier': username,
              'channel_type': 'instagram',
              'status': 'active'
          })
          
          if conversations and len(conversations) > 0:
              return conversations[0]
          
          # Criar nova conversa - CORREÇÃO AQUI
          new_conversation = db.insert('conversations', {
              'channel_type': 'instagram',
              'channel_identifier': username,
              'status': 'active'
              # REMOVIDO: external_id e created_at podem estar causando problema
          })
          
          # IMPORTANTE: Verificar se criou mesmo
          if new_conversation is None:
              logger.error("Falha ao criar conversa no banco")
              # Retornar conversa temporária
              return {
                  'id': f'temp_{thread_id}',
                  'channel_type': 'instagram',
                  'channel_identifier': username,
                  'status': 'active'
              }
          
          logger.info(f"Nova conversa criada para @{username}")
          return new_conversation
          
      except Exception as e:
          logger.error(f"Erro criando/buscando conversa: {e}")
          # Retornar conversa temporária se houver erro
          return {
              'id': f'temp_{thread_id}',
              'channel_type': 'instagram',
              'channel_identifier': username
          }
    
    async def get_conversation_history(self, conversation_id: str) -> List[Dict]:
        """Busca histórico de mensagens da conversa"""
        try:
            messages = db.select('messages', {
                'conversation_id': conversation_id
            })
            
            # Ordenar por data de criação
            return sorted(
                messages, 
                key=lambda x: x.get('created_at', ''),
                reverse=False  # Mais antigas primeiro
            )[-20:]  # Últimas 20 mensagens
            
        except Exception as e:
            logger.error(f"Erro buscando histórico: {e}")
            return []
    
    def is_running(self) -> bool:
        """Verifica se o monitor está rodando"""
        return self.client is not None

# ============================================
# CRIAÇÃO DA INSTÂNCIA GLOBAL
# ============================================

# Inicializar o monitor apenas se Instagram estiver configurado
instagram_monitor = None

try:
    # Verificar se Instagram está habilitado
    if hasattr(settings, 'instagram_enabled') and settings.instagram_enabled:
        if hasattr(settings, 'instagram_username') and settings.instagram_username:
            # Criar instância do monitor
            instagram_monitor = InstagramMonitor()
            logger.info("✅ Instância do monitor Instagram criada")
        else:
            logger.warning("Instagram habilitado mas sem username configurado")
    else:
        logger.info("Instagram não habilitado no .env")
        
except Exception as e:
    logger.error(f"Erro criando instância do monitor Instagram: {e}")
    instagram_monitor = None