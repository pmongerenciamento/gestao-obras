from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Configurações da aplicação: variáveis de ambiente, conexão Supabase, etc.


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
