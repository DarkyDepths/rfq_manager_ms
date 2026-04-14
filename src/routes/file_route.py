"""
File routes â€” FastAPI router for File endpoints.

Endpoints:
- GET    /rfqs/{rfqId}/stages/{stageId}/files  â€” #28 List files for stage
- GET    /files/{fileId}/download               â€” #29 Download file (stream or signed URL)
- DELETE /files/{fileId}                        â€” #30 Delete file (soft delete)
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import FileResponse

from src.app_context import get_file_controller
from src.controllers.file_controller import FileController
from src.translators.file_translator import StageFileListResponse
from src.utils.auth import AuthContext, Permissions, require_permission

# â”€â”€ Nested router for #28 (list files by stage) â”€â”€â”€â”€â”€â”€
stage_files_router = APIRouter(prefix="/rfqs/{rfq_id}/stages/{stage_id}/files", tags=["RFQ_Stage"])


@stage_files_router.get("", response_model=StageFileListResponse)
def list_stage_files(
    rfq_id: UUID,
    stage_id: UUID,
    _auth=Depends(require_permission(Permissions.FILE_LIST)),
    ctrl: FileController = Depends(get_file_controller),
):
    """#28 â€” List files for a stage."""
    return ctrl.list_for_stage(rfq_id, stage_id)


# â”€â”€ Flat router for #29-#30 (download/delete by file ID) â”€
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
def download_file(
    file_id: UUID,
    _auth=Depends(require_permission(Permissions.FILE_DOWNLOAD)),
    ctrl: FileController = Depends(get_file_controller),
):
    """#29 â€” Download file by ID. Returns file stream."""
    path, filename = ctrl.get_file_path(file_id)
    return FileResponse(path, filename=filename)


@file_router.delete("/{file_id}", status_code=204)
def delete_file(
    file_id: UUID,
    auth: AuthContext = Depends(require_permission(Permissions.FILE_DELETE)),
    ctrl: FileController = Depends(get_file_controller),
):
    """#30 â€” Soft delete file."""
    ctrl.delete(
        file_id,
        actor_team=auth.team,
        actor_permissions=auth.permissions,
    )
    return Response(status_code=204)
