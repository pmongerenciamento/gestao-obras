"""Utilitários compartilhados pelos scripts de apply/test das migrations.

ssl_ctx(target): contexto TLS com verificação completa para o pooler do Supabase,
confiando só na CA da Supabase baixada em backend/certs (validado por prova_tls.py
em staging e prod em 2026-10-08).
"""
import ssl
from pathlib import Path

CERTS = Path(__file__).resolve().parents[2] / "certs"
CA_FILES = {
    "prod": CERTS / "supabase-prod-ca.crt",
    "staging": CERTS / "supabase-staging-ca.crt",
}


def ssl_ctx(target):
    """Contexto TLS para o alvo ("prod" ou "staging"): só a CA da Supabase,
    check_hostname e CERT_REQUIRED. Nunca cai para conexão sem verificação."""
    if target not in CA_FILES:
        raise ValueError(f"alvo inválido: {target!r} (use 'prod' ou 'staging')")
    cafile = CA_FILES[target]
    if not cafile.is_file():
        raise FileNotFoundError(
            f"certificado da CA de {target} não encontrado em {cafile}; "
            "sem ele a conexão não é feita (não há fallback sem verificação)")
    ctx = ssl.create_default_context(cafile=cafile)
    # Desde o Python 3.13, create_default_context liga VERIFY_X509_STRICT, que exige a
    # extensão Key Usage em toda CA da cadeia. A CA intermediária "Supabase Intermediate
    # 2021 CA" não traz essa extensão (confirmado via openssl s_client -starttls postgres
    # contra aws-1-us-west-2.pooler.supabase.com em 2026-10-08), e a conexão falha com
    # "CA cert does not include key usage extension". Tirar só esse flag NÃO desliga
    # check_hostname nem CERT_REQUIRED: cadeia, assinaturas, validade e nome do host
    # continuam verificados; cai apenas a exigência extra de Key Usage na CA intermediária.
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    assert ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED
    return ctx
