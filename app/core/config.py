from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

# Força carregar o .env
load_dotenv()

class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str
    
    # Claude
    anthropic_api_key: str
    
    # MegaAPI (opcional por enquanto)
    megaapi_instance: str = ""
    megaapi_token: str = ""
    
    # App Config
    app_name: str = "Sistema Multi-Canal"
    debug: bool = True
    secret_key: str = "uma-chave-secreta-padrao"
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignora campos extras

settings = Settings()