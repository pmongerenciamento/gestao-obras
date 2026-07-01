"""Upload do arquivo original (.mpp/.xml/.xer) para o Supabase Storage.

Bucket privado `mpp-files` (criado como setup, fora do código — ver plano do
item 7). O que é guardado em snapshots.file_url/pending_imports.file_url é a
storage key (caminho dentro do bucket), não uma URL pública — o bucket é
privado, então baixar o arquivo depois exige URL assinada (fora de escopo
aqui).
"""
from __future__ import annotations

from pathlib import PurePosixPath
from uuid import UUID, uuid4

from .client import get_supabase_client

BUCKET = "mpp-files"


async def upload_original_file(data: bytes, owner_id: UUID, filename: str) -> str:
    """Sobe os bytes originais pro bucket e devolve a storage key.

    Caminho: {owner_id}/{uuid4()}-{nome do arquivo, só o basename}. O uuid4()
    evita colisão entre uploads do mesmo nome de arquivo pelo mesmo usuário.
    """
    safe_filename = PurePosixPath(filename).name
    path = f"{owner_id}/{uuid4()}-{safe_filename}"

    client = get_supabase_client()
    await client.storage.from_(BUCKET).upload(path, data)
    return path
