"""Rotas de importação de cronograma (.mpp/.xml/.xer): upload e processamento via MPXJ."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from app.core.dependencies import get_current_user, get_db
from app.domain.snapshots import ImportType, process_import
from app.infra.mpxj import MpxjReadError, read_project_bytes
from app.infra.storage import upload_original_file
from app.schemas import UploadResponse

router = APIRouter()


@router.post("/upload")
async def upload_schedule(
    file: UploadFile,
    owner_id: UUID = Depends(get_current_user),
    conn: asyncpg.connection.Connection = Depends(get_db),
) -> JSONResponse:
    data = await file.read()

    try:
        project = read_project_bytes(data, filename=file.filename)
    except MpxjReadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    file_url = await upload_original_file(data, owner_id, file.filename)
    fallback_name = Path(file.filename).stem

    async with conn.transaction():
        result = await process_import(
            conn,
            owner_id,
            project,
            fallback_name=fallback_name,
            reference_month=date.today().replace(day=1),
            file_url=file_url,
        )

    response = UploadResponse(
        import_type=result.import_type.value,
        project_id=result.project_id,
        snapshot_id=result.snapshot_id,
        pending_import_id=result.pending_import_id,
        diff_summary=result.diff_summary,
    )
    status_code = 202 if result.import_type == ImportType.STRUCTURAL_CHANGE else 201
    return JSONResponse(status_code=status_code, content=response.model_dump(mode="json"))
