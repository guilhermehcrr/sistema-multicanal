import httpx
from app.core.config import settings
import json

class SimpleSupabaseClient:
    def __init__(self):
        self.url = settings.supabase_url
        self.headers = {
            "apikey": settings.supabase_service_key,
            "Authorization": f"Bearer {settings.supabase_service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"  # Adiciona essa linha
        }
    
    def test_connection(self):
        try:
            response = httpx.get(
                f"{self.url}/rest/v1/",
                headers=self.headers
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Erro: {e}")
            return False
    
    def insert(self, table: str, data: dict):
        """Insere dados em uma tabela"""
        response = httpx.post(
            f"{self.url}/rest/v1/{table}",
            headers=self.headers,
            json=data
        )
        if response.status_code == 201:
            try:
                result = response.json()
                return result[0] if result else data
            except:
                return data
        return None
    
    def select(self, table: str, filters: dict = None):
        """Busca dados de uma tabela"""
        url = f"{self.url}/rest/v1/{table}"
        if filters:
            params = "&".join([f"{k}=eq.{v}" for k, v in filters.items()])
            url += f"?{params}"
        
        response = httpx.get(url, headers=self.headers)
        return response.json() if response.status_code == 200 else []

db = SimpleSupabaseClient()