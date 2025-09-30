# app/integrations/instagram/instagram_client.py

import os
import json
import time
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, UserNotFound
from app.core.config import settings

logger = logging.getLogger(__name__)

class InstagramClient:
    def __init__(self):
        """Inicializa o cliente Instagram com configurações de segurança"""
        self.cl = Client()
        self.username = settings.instagram_username
        self.password = settings.instagram_password
        
        # Arquivos de persistência
        self.session_file = "instagram_session.json"
        self.processed_messages_file = "instagram_processed.json"
        
        # Carregar mensagens já processadas
        self.processed_messages = self.load_processed_messages()
        
        # Configurações anti-ban
        self.cl.delay_range = [3, 7]  # Delay entre requisições (segundos)
        
        # Simular dispositivo Android real
        self.cl.set_user_agent(
            "Instagram 269.0.0.18.75 Android (30/11; 450dpi; 1080x2340; "
            "OnePlus/OnePlus; OnePlus 6T Dev; OnePlus 6T; qcom; en_US; 449904927)"
        )
        
        # Configurar proxy se disponível (opcional)
        if hasattr(settings, 'instagram_proxy') and settings.instagram_proxy:
            self.cl.set_proxy(settings.instagram_proxy)
        
        # Fazer login
        self.login()
        
        # ID do próprio usuário (para filtrar mensagens)
        try:
            self.my_user_id = self.cl.user_id_from_username(self.username)
        except:
            self.my_user_id = self.cl.user_id
    
    def login(self):
        """Faz login no Instagram com sessão persistente"""
        try:
            # Tentar carregar sessão existente
            if os.path.exists(self.session_file):
                logger.info("Carregando sessão salva do Instagram...")
                try:
                    with open(self.session_file, 'r') as f:
                        session_data = json.load(f)
                        self.cl.set_settings(session_data)
                        
                        # Testar se a sessão ainda é válida
                        try:
                            self.cl.get_timeline_feed()
                            logger.info("✅ Login via sessão salva com sucesso!")
                            return
                        except:
                            logger.warning("Sessão expirada, fazendo novo login...")
                            os.remove(self.session_file)
                except Exception as e:
                    logger.warning(f"Erro carregando sessão: {e}")
                    if os.path.exists(self.session_file):
                        os.remove(self.session_file)
            
            # Fazer login normal
            logger.info(f"Fazendo login no Instagram como @{self.username}...")
            
            # Login com tratamento de 2FA se necessário
            if hasattr(settings, 'instagram_2fa_secret') and settings.instagram_2fa_secret:
                self.cl.login(
                    self.username, 
                    self.password,
                    verification_code=self.get_2fa_code()
                )
            else:
                self.cl.login(self.username, self.password)
            
            # Salvar sessão
            self.save_session()
            logger.info("✅ Login no Instagram realizado com sucesso!")
            
        except ChallengeRequired as e:
            logger.error("⚠️ Instagram solicitou verificação de segurança!")
            logger.error("Por favor:")
            logger.error("1. Abra o Instagram no navegador")
            logger.error("2. Faça login e confirme que é você")
            logger.error("3. Depois tente novamente")
            raise e
            
        except LoginRequired as e:
            logger.error("❌ Login falhou - verifique usuário e senha")
            raise e
            
        except Exception as e:
            logger.error(f"❌ Erro no login: {e}")
            raise e
    
    def get_2fa_code(self) -> str:
        """Gera código 2FA se configurado"""
        try:
            import pyotp
            totp = pyotp.TOTP(settings.instagram_2fa_secret)
            return totp.now()
        except:
            return input("Digite o código 2FA do Instagram: ")
    
    def save_session(self):
        """Salva sessão para reutilizar"""
        try:
            session_data = self.cl.get_settings()
            with open(self.session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            logger.debug("Sessão salva com sucesso")
        except Exception as e:
            logger.error(f"Erro salvando sessão: {e}")
    
    def load_processed_messages(self) -> set:
        """Carrega IDs de mensagens já processadas"""
        try:
            if os.path.exists(self.processed_messages_file):
                with open(self.processed_messages_file, 'r') as f:
                    data = json.load(f)
                    return set(data)
        except Exception as e:
            logger.debug(f"Criando novo arquivo de mensagens processadas: {e}")
        return set()
    
    def save_processed_messages(self):
        """Salva IDs de mensagens processadas"""
        try:
            # Limitar tamanho para não crescer infinitamente
            if len(self.processed_messages) > 1000:
                # Manter apenas as 800 mais recentes
                self.processed_messages = set(list(self.processed_messages)[-800:])
            
            with open(self.processed_messages_file, 'w') as f:
                json.dump(list(self.processed_messages), f)
        except Exception as e:
            logger.error(f"Erro salvando mensagens processadas: {e}")
    
    async def get_unread_messages(self) -> List[Dict]:
        """Busca mensagens não processadas do Instagram"""
        messages_to_process = []
        
        try:
            # Buscar threads de mensagens diretas
            logger.debug("Buscando threads do Instagram...")
            threads = self.cl.direct_threads(amount=20)
            
            if not threads:
                logger.debug("Nenhuma thread encontrada")
                return []
            
            logger.debug(f"Encontradas {len(threads)} threads")
            
            for thread in threads:
                try:
                    # Verificar se deve processar esta thread
                    should_check = False
                    
                    # Verificar se tem mensagem não lida
                    if hasattr(thread, 'pending') and thread.pending:
                        should_check = True
                        logger.debug(f"Thread tem mensagens não lidas")
                    
                    # Verificar atividade recente (últimos 10 minutos)
                    if hasattr(thread, 'last_activity_at'):
                        try:
                            last_activity = thread.last_activity_at
                            if isinstance(last_activity, int):
                                last_activity = datetime.fromtimestamp(last_activity / 1000)
                            elif isinstance(last_activity, str):
                                last_activity = datetime.fromisoformat(last_activity)
                            
                            time_diff = (datetime.now() - last_activity).total_seconds()
                            if time_diff < 600:  # 10 minutos
                                should_check = True
                                logger.debug(f"Thread com atividade recente ({int(time_diff)}s atrás)")
                        except:
                            pass
                    
                    # Sempre verificar pelo menos a última mensagem
                    if should_check or True:
                        # Buscar mensagens da thread
                        messages = self.cl.direct_messages(thread.id, amount=5)
                        
                        for msg in messages:
                            try:
                                # Criar ID único para a mensagem
                                msg_id = f"{thread.id}_{msg.timestamp}"
                                
                                # Pular se já foi processada
                                if msg_id in self.processed_messages:
                                    continue
                                
                                # Processar apenas mensagens de outros usuários
                                if msg.user_id == self.my_user_id:
                                    continue
                                
                                # Processar apenas mensagens com texto
                                if not msg.text:
                                    continue
                                
                                # Extrair username
                                username = "unknown"
                                if thread.users:
                                    for user in thread.users:
                                        if user.pk == msg.user_id:
                                            username = user.username
                                            break
                                    if username == "unknown" and thread.users:
                                        username = thread.users[0].username
                                
                                # Adicionar mensagem para processar
                                messages_to_process.append({
                                    'thread_id': thread.id,
                                    'user_id': msg.user_id,
                                    'username': username,
                                    'message': msg.text,
                                    'timestamp': msg.timestamp,
                                    'msg_id': msg_id
                                })
                                
                                # Marcar como processada
                                self.processed_messages.add(msg_id)
                                
                                # Processar apenas a mensagem mais recente não processada
                                break
                                
                            except Exception as e:
                                logger.error(f"Erro processando mensagem individual: {e}")
                                continue
                            
                except Exception as e:
                    logger.error(f"Erro processando thread: {e}")
                    continue
            
            # Salvar mensagens processadas se houver novas
            if messages_to_process:
                self.save_processed_messages()
                logger.info(f"📥 {len(messages_to_process)} novas mensagens para processar")
            
            return messages_to_process
            
        except Exception as e:
            logger.error(f"Erro buscando mensagens: {e}")
            return []
    
    async def send_message(self, thread_id: str, message: str) -> bool:
        """Envia mensagem para uma thread do Instagram"""
        try:
            # Delay anti-ban
            delay = random.uniform(3, 8)
            logger.debug(f"Aguardando {delay:.1f}s antes de enviar...")
            time.sleep(delay)
            
            # Enviar mensagem
            result = self.cl.direct_send(
                text=message,
                thread_ids=[thread_id]
            )
            
            if result:
                logger.info(f"✅ Mensagem enviada no Instagram")
                
                # Adicionar delay adicional após envio
                time.sleep(random.uniform(2, 4))
                return True
            else:
                logger.error("❌ Falha ao enviar mensagem")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erro enviando mensagem: {e}")
            return False
    
    async def mark_as_read(self, thread_id: str):
        """Marca thread como lida"""
        try:
            self.cl.direct_thread_mark_read(thread_id)
            logger.debug("Thread marcada como lida")
        except Exception as e:
            logger.debug(f"Erro marcando como lida (não crítico): {e}")
    
    def get_user_info(self, username: str) -> Optional[Dict]:
        """Busca informações de um usuário (opcional)"""
        try:
            user = self.cl.user_info_by_username(username)
            return {
                'full_name': user.full_name,
                'is_verified': user.is_verified,
                'is_private': user.is_private,
                'follower_count': user.follower_count,
                'following_count': user.following_count,
                'media_count': user.media_count
            }
        except UserNotFound:
            logger.warning(f"Usuário @{username} não encontrado")
            return None
        except Exception as e:
            logger.error(f"Erro buscando info do usuário: {e}")
            return None

# ============================================
# INICIALIZAÇÃO GLOBAL
# ============================================

instagram_client = None

# Só criar cliente se Instagram estiver configurado
if hasattr(settings, 'instagram_enabled') and settings.instagram_enabled:
    if hasattr(settings, 'instagram_username') and settings.instagram_username:
        try:
            logger.info("Inicializando cliente Instagram...")
            instagram_client = InstagramClient()
            logger.info("Cliente Instagram inicializado com sucesso")
        except Exception as e:
            logger.error(f"Erro inicializando Instagram: {e}")
            logger.error("Instagram será desabilitado nesta sessão")
            instagram_client = None
    else:
        logger.warning("Instagram habilitado mas credenciais não configuradas")
else:
    logger.info("Instagram não habilitado no .env")