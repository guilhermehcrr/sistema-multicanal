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

    # Email - ADICIONE ESTAS LINHAS
    email_address: str = ""
    email_password: str = ""
    email_imap_server: str = "imap.gmail.com"
    email_imap_port: int = 993
    email_smtp_server: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_check_interval: int = 10

    # Instagram
    instagram_username: str = ""
    instagram_password: str = ""
    instagram_2fa_secret: str = ""
    instagram_check_interval: int = 120
    instagram_enabled: bool = False

    # App Config
    app_name: str = "Sistema Multi-Canal"
    debug: bool = True
    secret_key: str = "uma-chave-secreta-padrao"
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignora campos extras

settings = Settings()