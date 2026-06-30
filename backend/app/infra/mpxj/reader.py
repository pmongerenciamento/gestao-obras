"""Wrapper fino sobre o UniversalProjectReader do MPXJ.

Responsabilidade: entregar um org.mpxj.ProjectFile (objeto Java) a partir de um
.mpp/.xml/.xer. O mapeamento desse objeto para o schema do banco é
responsabilidade de app/domain/import_mpp, não deste módulo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .jvm import is_jvm_running


class MpxjReadError(Exception):
    """Arquivo de cronograma não pôde ser lido (formato inválido/não suportado)."""


def _require_jvm() -> None:
    if not is_jvm_running():
        raise RuntimeError(
            "JVM do MPXJ não está ativa — start_jvm() deve ser chamado no lifespan do FastAPI."
        )


def read_project_file(path: str | Path) -> Any:
    """Lê um cronograma a partir de um caminho no disco. Retorna org.mpxj.ProjectFile."""
    _require_jvm()
    from org.mpxj import MPXJException
    from org.mpxj.reader import UniversalProjectReader

    try:
        project = UniversalProjectReader().read(str(path))
    except MPXJException as exc:
        raise MpxjReadError(str(exc)) from exc

    if project is None:
        raise MpxjReadError(f"Formato de arquivo não reconhecido: {path}")
    return project


def read_project_bytes(data: bytes, *, filename: str = "upload") -> Any:
    """Lê um cronograma a partir do conteúdo em memória (ex: UploadFile.read())."""
    _require_jvm()
    from java.io import ByteArrayInputStream
    from org.mpxj import MPXJException
    from org.mpxj.reader import UniversalProjectReader

    stream = ByteArrayInputStream(data)
    try:
        project = UniversalProjectReader().read(stream)
    except MPXJException as exc:
        raise MpxjReadError(str(exc)) from exc
    finally:
        stream.close()

    if project is None:
        raise MpxjReadError(f"Formato de arquivo não reconhecido: {filename}")
    return project
