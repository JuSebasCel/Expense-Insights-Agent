"""Configuración de la app, leída desde variables de entorno / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

CATEGORIES = [
    "mercado",
    "transporte",
    "restaurantes",
    "suscripciones",
    "salud",
    "entretenimiento",
    "servicios_facturas",
    "transferencias",
    "otros",
]

# Remitentes conocidos de notificaciones bancarias. Se combinan con OR en la
# búsqueda de Gmail. Hoy solo hay evidencia real de Bancolombia en la cuenta
# del usuario; los de Nequi son placeholders a confirmar cuando existan.
BANK_SENDERS = [
    "alertasynotificaciones@bancolombia.com.co",
    "nequi.com.co",
]

CHECKPOINT_THREAD_ID = "expense-tracker-main"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str
    gemini_model: str = "gemini-flash-latest"

    gmail_credentials_path: str = "secrets/credentials.json"
    gmail_token_path: str = "secrets/token.json"

    checkpoint_db_path: str = "data/checkpoints.sqlite"


@lru_cache
def get_settings() -> Settings:
    return Settings()
