# app/services/vendor_rotation.py
from app.integrations.whatsapp.megaapi_client import megaapi
from app.core.database_simple import db
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

class VendorRotationSystem:
    def __init__(self):
        # Configuração dos vendedores
        self.vendors = [
            {
                "name": "Anderson",
                "phone": "5511999999999",  # TROCAR: número real do Anderson
                "emoji": "👨‍💼"
            },
            {
                "name": "Sheila", 
                "phone": "5511888888888",  # TROCAR: número real da Sheila
                "emoji": "👩‍💼"
            },
            {
                "name": "Ayla",
                "phone": "5511777777777",  # TROCAR: número real da Ayla
                "emoji": "👩‍💼"
            }
        ]
        
        # ID do grupo WhatsApp
        self.sales_group_id = "120363421034922709@g.us"  # Seu ID real do grupo
        
        # Modo teste (False = envio real)
        self.test_mode = False
    
    def get_current_vendor_index(self):
        """Busca qual vendedor é a vez de atender"""
        try:
            # Buscar último atendimento no banco
            last_assignments = db.select('vendor_assignments')
            
            if not last_assignments:
                return 0  # Começa com Anderson
            
            # Pegar o último e calcular próximo
            last = sorted(last_assignments, key=lambda x: x.get('created_at', ''))[-1]
            last_index = last.get('vendor_index', 0)
            
            # Próximo vendedor (rotação circular)
            next_index = (last_index + 1) % len(self.vendors)
            return next_index
            
        except Exception as e:
            logger.error(f"Erro buscando índice: {e}")
            # Se der erro, tenta arquivo local
            try:
                if os.path.exists('last_vendor.txt'):
                    with open('last_vendor.txt', 'r') as f:
                        last_index = int(f.read().strip())
                        return (last_index + 1) % len(self.vendors)
            except:
                pass
            return 0
    
    def save_assignment(self, vendor_index: int, conversation_id: str):
        """Salva qual vendedor foi designado"""
        try:
            # Salvar no banco
            db.insert('vendor_assignments', {
                'vendor_index': vendor_index,
                'vendor_name': self.vendors[vendor_index]['name'],
                'conversation_id': conversation_id,
                'created_at': datetime.utcnow().isoformat()
            })
            logger.info(f"✅ Salvo: {self.vendors[vendor_index]['name']} vai atender")
        except Exception as e:
            logger.error(f"Erro salvando no banco: {e}")
            
        # Backup em arquivo local
        try:
            with open('last_vendor.txt', 'w') as f:
                f.write(str(vendor_index))
        except:
            pass
    
    async def notify_group_hot_lead(self, phone: str, message: str, 
                                   classification: dict, conversation_id: str,
                                   channel: str = 'whatsapp'):
        """Envia notificação no grupo com vendedor designado (WhatsApp ou Email)"""
        try:
            # Determinar vendedor da vez
            vendor_index = self.get_current_vendor_index()
            vendor = self.vendors[vendor_index]
            
            # Salvar no banco
            self.save_assignment(vendor_index, conversation_id)
            
            # Próximo vendedor
            next_vendor = self.vendors[(vendor_index + 1) % len(self.vendors)]
            
            ## Detectar canal corretamente
            if channel == 'email':
                channel_type = '📧 EMAIL'
                contact_info = phone
                contact_link = f"mailto:{contact_info}"
                contact_display = f"📧 {contact_info}"
            elif channel == 'instagram':
                channel_type = '📸 INSTAGRAM'
                username_clean = phone.replace('@', '')
                contact_link = f"https://instagram.com/{username_clean}"
                contact_display = f"📸 @{username_clean}"
            else:  # whatsapp (padrão)
                channel_type = '📱 WHATSAPP'
                contact_info = phone.replace('+', '').replace(' ', '')
                contact_link = f"https://wa.me/{contact_info}"
                contact_display = f"📱 wa.me/{contact_info}"
            
            # Formatar mensagem
            urgency = "🔥🔥🔥" if classification['category'] == 'HOT' else "💳✅"
            time_now = datetime.now().strftime('%H:%M')
            
            group_message = f"""{urgency} *LEAD {classification['category']}* {urgency}
{channel_type} - NOVO LEAD!

{vendor['emoji']} *VEZ DE: {vendor['name'].upper()}* {vendor['emoji']}

*Contato do Cliente:*
{contact_display}

💬 *Mensagem:*
_{message[:200]}{"..." if len(message) > 200 else ""}_

📊 *Análise da IA:*
• Classificação: {classification['category']}
• Confiança: {int(classification['confidence'] * 100)}%
• Motivo: {classification.get('reasoning', 'Cliente interessado')}

⏰ *Recebido às:* {time_now}

⚡ *{vendor['name']}, RESPONDA AGORA!*
👉 {contact_link}

━━━━━━━━━━━━━━━
📌 Próximo da fila: {next_vendor['name']}"""
            
            # Enviar mensagens
            if self.test_mode:
                logger.info("=" * 50)
                logger.info("MODO TESTE - Mensagem que seria enviada:")
                logger.info(group_message)
                logger.info("=" * 50)
                return {
                    "status": "test_mode",
                    "vendor": vendor['name'],
                    "message": group_message
                }
            else:
                # Enviar para o grupo
                await megaapi.send_message(self.sales_group_id, group_message)
                
                # Mensagem privada para o vendedor baseada no canal
                if channel == 'email':
                    private_msg = f"""🚨 *EMAIL URGENTE!* 🚨

            📧 Cliente esperando resposta por EMAIL!

            De: {phone}
            Assunto: {message[:50]}...

            ✉️ Responda o email AGORA!
            {contact_link}"""

                elif channel == 'instagram':  # elif e minúsculo!
                    private_msg = f"""🚨 *INSTAGRAM URGENTE!* 🚨

            📸 Cliente esperando no Instagram!

            Clique para abrir:
            {contact_link}

            Mensagem: "{message[:100]}{"..." if len(message) > 100 else ""}" """

                else:  # whatsapp (padrão)
                    private_msg = f"""🚨 *SUA VEZ!* 🚨

            📱 Cliente esperando no WhatsApp!

            Clique para abrir:
            {contact_link}

            Mensagem: "{message[:100]}{"..." if len(message) > 100 else ""}" """
                
                # Enviar UMA VEZ só para o vendedor
                await megaapi.send_message(vendor['phone'], private_msg)
                
                logger.info(f"✅ Notificações enviadas - Vendedor: {vendor['name']}")
                
                return {
                    "status": "sent",
                    "vendor": vendor['name']
                }
                            
                
                

                
        except Exception as e:
            logger.error(f"❌ Erro enviando notificação: {e}")
            return {"status": "error", "error": str(e)}
    
    async def get_vendor_stats(self):
        """Retorna estatísticas de atendimento"""
        try:
            assignments = db.select('vendor_assignments')
            stats = {}
            
            for vendor in self.vendors:
                vendor_assignments = [a for a in assignments 
                                     if a.get('vendor_name') == vendor['name']]
                stats[vendor['name']] = {
                    'total': len(vendor_assignments),
                    'today': len([a for a in vendor_assignments 
                                 if datetime.fromisoformat(a.get('created_at', '2000-01-01')).date() == datetime.now().date()]),
                    'emoji': vendor['emoji']
                }
            
            return stats
        except Exception as e:
            logger.error(f"Erro calculando estatísticas: {e}")
            return {}

# Criar instância global
vendor_rotation = VendorRotationSystem()