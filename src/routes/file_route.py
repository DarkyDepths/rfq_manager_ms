"""
File routes — FastAPI router for File endpoints.

Endpoints:
- GET    /rfqs/{rfqId}/stages/{stageId}/files  — #27 List files for stage
- GET    /files/{fileId}/download               — #28 Download file (stream or signed URL)
- DELETE /files/{fileId}                        — #29 Delete file (soft delete)
"""

from uuid import UUID
from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse

from src.app_context import get_file_controller
from src.controllers.file_controller import FileController
from src.translators.file_translator import StageFileListResponse

# ── Nested router for #26 (list files by stage) ──────
stage_files_router = APIRouter(prefix="/rfqs/{rfq_id}/stages/{stage_id}/files", tags=["RFQ_Stage"])


@stage_files_router.get("", response_model=StageFileListResponse)
def list_stage_files(rfq_id: UUID, stage_id: UUID, ctrl: FileController = Depends(get_file_controller)):
    """#27 — List files for a stage."""
    return ctrl.list_for_stage(rfq_id, stage_id)


# ── Flat router for #27-#28 (download/delete by file ID) ─
file_router = APIRouter(prefix="/files", tags=["File"])


@file_router.get(
    "/{file_id}/download",
    responses={
        200: {
            "content": {"application/octet-stream": {}},
            "description": "File downloaded successfully",
        }
    }
)
def download_file(file_id: UUID, ctrl: FileController = Depends(get_file_controller)):
    """#28 — Download file by ID. Returns file stream."""
    path, filename = ctrl.get_file_path(file_id)
    return FileResponse(path, filename=filename)


@file_router.delete("/{file_id}", status_code=204)
def delete_file(file_id: UUID, ctrl: FileController = Depends(get_file_controller)):
    """#29 — Soft delete file."""
    ctrl.delete(file_id)
    return Response(status_code=204)
