"""Integração com a API do Banco Inter (escopo só "Saldo e Extrato").

Por enquanto só autenticação: OAuth2 client_credentials com mTLS. Consulta
de extrato e gravação em bank_transactions ficam pra depois.

Especificação conferida em https://developers.inter.co/references/token:
  - POST https://cdpj.partners.bancointer.com.br/oauth/v2/token
  - corpo application/x-www-form-urlencoded: client_id, client_secret,
    grant_type=client_credentials, scope
  - escopo de extrato/saldo: "extrato.read"
  - token vale 1 hora; rate limit do endpoint de token: 5 chamadas/minuto
    (por isso o token fica em cache em memória até perto de expirar)
"""
from __future__ import annotations

import atexit
import base64
import os
import tempfile
import time

import httpx

from app.core.config import get_settings

TOKEN_URL = "https://cdpj.partners.bancointer.com.br/oauth/v2/token"
SCOPE = "extrato.read"

# Renova o token um pouco antes de expirar, pra não usar um token que vence
# no meio de uma requisição.
_TOKEN_EXPIRY_MARGIN_SECONDS = 60

_cert_files: tuple[str, str] | None = None
_cached_token: str | None = None
_cached_token_expires_at: float = 0.0


class BancoInterConfigError(RuntimeError):
    """Variável de ambiente do Banco Inter ausente."""


def _require(value: str | None, env_name: str) -> str:
    if not value:
        raise BancoInterConfigError(f"Variável de ambiente {env_name} não configurada")
    return value


def _write_temp_file(content: bytes, suffix: str) -> str:
    # mkstemp cria o arquivo com permissão só do dono (0600 em Unix).
    fd, path = tempfile.mkstemp(prefix="banco_inter_", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return path


def _remove_cert_files() -> None:
    global _cert_files
    if _cert_files is None:
        return
    for path in _cert_files:
        try:
            os.remove(path)
        except OSError:
            pass
    _cert_files = None


def get_client_cert_files() -> tuple[str, str]:
    """Decodifica certificado e chave mTLS (base64 nas variáveis de ambiente)
    pra arquivos temporários e devolve (caminho_crt, caminho_key).

    Os arquivos são criados uma vez por processo e reaproveitados; são
    apagados quando o processo termina.
    """
    global _cert_files
    if _cert_files is not None and all(os.path.exists(p) for p in _cert_files):
        return _cert_files

    settings = get_settings()
    cert_b64 = _require(settings.banco_inter_cert_base64, "BANCO_INTER_CERT_BASE64")
    key_b64 = _require(settings.banco_inter_key_base64, "BANCO_INTER_KEY_BASE64")

    cert_path = _write_temp_file(base64.b64decode(cert_b64), ".crt")
    key_path = _write_temp_file(base64.b64decode(key_b64), ".key")
    _cert_files = (cert_path, key_path)
    return _cert_files


atexit.register(_remove_cert_files)


async def get_access_token() -> str:
    """Obtém um access token OAuth2 (client_credentials, escopo extrato.read)
    autenticando via mTLS. Reaproveita o token em cache enquanto ele não
    estiver perto de expirar. Levanta httpx.HTTPStatusError se o Inter
    recusar a requisição.
    """
    global _cached_token, _cached_token_expires_at
    if _cached_token is not None and time.monotonic() < _cached_token_expires_at:
        return _cached_token

    settings = get_settings()
    client_id = _require(settings.banco_inter_client_id, "BANCO_INTER_CLIENT_ID")
    client_secret = _require(settings.banco_inter_client_secret, "BANCO_INTER_CLIENT_SECRET")

    async with httpx.AsyncClient(cert=get_client_cert_files(), timeout=30.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "scope": SCOPE,
            },
        )
    response.raise_for_status()
    body = response.json()

    _cached_token = body["access_token"]
    expires_in = float(body.get("expires_in", 3600))
    _cached_token_expires_at = time.monotonic() + expires_in - _TOKEN_EXPIRY_MARGIN_SECONDS
    return _cached_token
