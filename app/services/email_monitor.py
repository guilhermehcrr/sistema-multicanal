import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import asyncio
from datetime import datetime
from app.core.config import settings
from app.core.database_simple import db
from app.services.lead_classifier import classifier
from app.services.ai_responder import ai_responder
from app.services.vendor_rotation import vendor_rotation
import logging
import re

logger = logging.getLogger(__name__)

class EmailMonitor:
    def __init__(self):
        self.email_address = settings.email_address
        self.email_password = settings.email_password
        self.imap_server = settings.email_imap_server
        self.imap_port = settings.email_imap_port
        self.smtp_server = settings.email_smtp_server
        self.smtp_port = settings.email_smtp_port
        self.check_interval = int(settings.email_check_interval)
        self.processed_emails = set()  # Para não processar o mesmo email 2x
        
    def connect_imap(self):
        """Conecta ao servidor IMAP para ler emails"""
        try:
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(self.email_address, self.email_password)
            mail.select('INBOX')
            return mail
        except Exception as e:
            logger.error(f"Erro conectando IMAP: {e}")
            return None
    
    def extract_email_content(self, msg):
        """Extrai o conteúdo do email"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
                elif content_type == "text/html" and not body:
                    html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    # Remove tags HTML básicas
                    body = re.sub('<[^<]+?>', '', html)
        else:
            body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        return body.strip()
    
    async def check_new_emails(self):
        """Verifica novos emails na caixa de entrada"""
        try:
            mail = self.connect_imap()
            if not mail:
                return
            
            # Buscar emails não lidos
            status, messages = mail.search(None, 'UNSEEN')
            
            if status != 'OK':
                return
            
            email_ids = messages[0].split()
            
            for email_id in email_ids:
                if email_id in self.processed_emails:
                    continue
                    
                try:
                    # Buscar o email
                    status, msg_data = mail.fetch(email_id, '(RFC822)')
                    
                    if status != 'OK':
                        continue
                    
                    # Parse do email
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    # Extrair informações
                    from_email = msg['From']
                    subject = msg['Subject']
                    body = self.extract_email_content(msg)
                    
                    # Processar apenas se tiver conteúdo
                    if body:
                        await self.process_email(from_email, subject, body, email_id.decode())
                        
                    self.processed_emails.add(email_id)
                    
                except Exception as e:
                    logger.error(f"Erro processando email {email_id}: {e}")
            
            mail.close()
            mail.logout()
            
        except Exception as e:
            logger.error(f"Erro verificando emails: {e}")
    
    async def process_email(self, from_email: str, subject: str, body: str, email_id: str):
        """Processa um email recebido (EXATAMENTE como WhatsApp)"""
        try:
            logger.info(f"Processando email de: {from_email}")
            logger.info(f"Assunto: {subject}")
            
            # Extrair apenas o endereço de email
            if '<' in from_email:
                client_email = from_email.split('<')[1].strip('>')
            else:
                client_email = from_email
            
            # Combinar assunto e corpo para classificação
            full_content = f"Assunto: {subject}\n\n{body[:500]}"  # Limitar tamanho
            
            # 1. Classificar o email (HOT/WARM/COLD)
            classification = await classifier.classify(full_content)
            logger.info(f"Email classificado como: {classification}")
            
            # 2. Buscar ou criar conversa
            conversation = await self.get_or_create_email_conversation(client_email)
            
            # 3. Buscar histórico da conversa
            conversation_history = await self.get_conversation_history(conversation['id'])
            
            # 4. Salvar email recebido no banco
            db.insert('messages', {
                'conversation_id': conversation['id'],
                'content': f"[ASSUNTO: {subject}]\n\n{body}",
                'direction': 'inbound',
                'sender_type': 'lead',
                'channel': 'email'
            })
            
            # 5. SEMPRE gerar resposta inteligente com IA (não importa a classificação)
            response = await ai_responder.generate_response(
                full_content,
                conversation_history,
                classification
            )
            
            # 6. Se for HOT/BOOKING_READY, criar handoff E notificar vendedor
            if classification['category'] in ['HOT', 'BOOKING_READY']:
                # Criar handoff
                db.insert('handoff_queue', {
                    'conversation_id': conversation['id'],
                    'priority': 'HIGH',
                    'reason': f"Email {classification['category']}: {classification.get('reasoning', '')}",
                    'channel': 'email'
                })
                
                # Notificar grupo WhatsApp com vendedor designado
                notification_result = await vendor_rotation.notify_group_hot_lead(
                    phone=client_email,  # Usar email em vez de telefone
                    message=f"[EMAIL] {subject}\n{body[:200]}...",
                    classification=classification,
                    conversation_id=conversation['id'],
                    channel='email'  # Indicar que veio de email
                )
                
                vendor_name = notification_result.get('vendor', 'nossa equipe')
                logger.info(f"Email HOT - Vendedor designado: {vendor_name}")
                
                # Substituir resposta da IA pela mensagem personalizada do vendedor
                response = f"""Olá!

Perfeito! Recebi seu email sobre reserva.

Já encaminhei sua solicitação para {vendor_name}, nosso(a) especialista em reservas, 
que entrará em contato em breve para finalizar todos os detalhes.

{vendor_name} responderá este email em até 30 minutos com todas as informações 
e disponibilidade.

Atenciosamente,
Hotel Paradise São Paulo"""
            
            # Se for WARM ou COLD, o bot responde normalmente com IA
            # A resposta já foi gerada no passo 5
            
            # 7. SEMPRE enviar resposta por email (seja qual for a classificação)
            await self.send_email_response(client_email, subject, response)
            
            # 8. Salvar resposta enviada no banco
            db.insert('messages', {
                'conversation_id': conversation['id'],
                'content': response,
                'direction': 'outbound',
                'sender_type': 'bot',
                'channel': 'email'
            })
            
            logger.info(f"Email processado e respondido: {client_email}")
            logger.info(f"Tipo de resposta: {'Vendedor notificado' if classification['category'] in ['HOT', 'BOOKING_READY'] else 'Bot respondeu dúvidas'}")
            
        except Exception as e:
            logger.error(f"Erro processando email: {e}")
    
    async def send_email_response(self, to_email: str, original_subject: str, body: str):
        """Envia resposta por email"""
        try:
            # Preparar mensagem
            msg = MIMEMultipart()
            msg['From'] = self.email_address
            msg['To'] = to_email
            msg['Subject'] = f"Re: {original_subject}"
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Conectar e enviar
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_address, self.email_password)
                server.send_message(msg)
            
            logger.info(f"Email enviado para: {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Erro enviando email: {e}")
            return False
    
    async def get_or_create_email_conversation(self, email_address: str):
        """Busca ou cria conversa de email"""
        conversations = db.select('conversations', {
            'channel_identifier': email_address,
            'channel_type': 'email',
            'status': 'active'
        })
        
        if conversations:
            return conversations[0]
        
        return db.insert('conversations', {
            'channel_type': 'email',
            'channel_identifier': email_address,
            'status': 'active'
        })
    
    async def get_conversation_history(self, conversation_id: str):
        """Busca histórico de mensagens"""
        messages = db.select('messages', {'conversation_id': conversation_id})
        return sorted(messages, key=lambda x: x.get('created_at', ''))
    
    async def start_monitoring(self):
        """Inicia o monitoramento contínuo de emails"""
        logger.info(f"Iniciando monitoramento de emails a cada {self.check_interval} segundos")
        
        while True:
            try:
                await self.check_new_emails()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Erro no loop de monitoramento: {e}")
                await asyncio.sleep(self.check_interval)

email_monitor = EmailMonitor()
