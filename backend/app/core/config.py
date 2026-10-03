from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Configurações da aplicação: variáveis de ambiente, conexão Supabase, etc.


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    supabase_url: str
    supabase_service_role_key: str

    # Integração Banco Inter (só "Saldo e Extrato"). Opcionais: o app sobe
    # sem elas; só as rotas do Inter falham se faltarem.
    banco_inter_client_id: str | None = None
    banco_inter_client_secret: str | None = None
    banco_inter_cert_base64: str | None = None
    banco_inter_key_base64: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
