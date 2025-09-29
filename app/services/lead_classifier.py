from anthropic import Anthropic
from app.core.config import settings
import json

class LeadClassifier:
    def __init__(self):
        self.client = Anthropic(api_key=settings.anthropic_api_key)
    
    async def classify(self, message: str):
        prompt = """Classifique esta mensagem de cliente de hotel em uma das categorias:
        
        HOT: Quer reservar agora, tem data específica, urgente
        WARM: Interessado, pesquisando opções
        COLD: Apenas tirando dúvidas gerais
        BOOKING_READY: Pronto para fechar reserva
        
        Mensagem: "{}"
        
        Responda APENAS um JSON: {{"category": "...", "confidence": 0.0-1.0, "reasoning": "..."}}
        """.format(message)
        
        response = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return json.loads(response.content[0].text)

classifier = LeadClassifier()