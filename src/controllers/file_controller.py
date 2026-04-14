"""
File controller — business logic for the File resource.

Orchestrates:
- List files for a stage (WHERE deleted_at IS NULL)
- Download file (stream from local storage or generate signed Azure Blob URL)
- Soft-delete file (set deleted_at = NOW())

Dependencies: FileDatasource
"""

import os
from typing import Sequence
from sqlalchemy.orm import Session

from src.datasources.file_datasource import FileDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.translators import file_translator
from src.utils.errors import ForbiddenError, NotFoundError
from src.utils.file_storage import resolve_stored_file_path

def _resolve_physical_path(stored_path: str) -> str:
    return resolve_stored_file_path(stored_path).as_posix()

class FileController:

    def __init__(self, datasource: FileDatasource, stage_datasource: RfqStageDatasource, session: Session):
        self.ds = datasource
        self.stage_ds = stage_datasource
        self.session = session

    def list_for_stage(self, rfq_id, stage_id) -> dict:
        stage = self.stage_ds.get_by_id(stage_id)
        if not stage or stage.rfq_id != rfq_id:
            raise NotFoundError(f"Stage '{stage_id}' not found in RFQ '{rfq_id}'")

        files = self.ds.list_by_stage(stage_id)
        return {"data": [file_translator.to_response(f) for f in files]}

    def get_file_path(self, file_id) -> tuple[str, str]:
        """Returns the file path and original filename for download."""
        file = self.ds.get_by_id(file_id)
        if not file:
            raise NotFoundError(f"File '{file_id}' not found")
            
        physical_path = _resolve_physical_path(file.file_path)
            
        if not os.path.exists(physical_path):
            raise NotFoundError(f"File '{file.filename}' not found on disk")
        return physical_path, file.filename

    def delete(
        self,
        file_id,
        *,
        actor_team: str | None = None,
        actor_permissions: Sequence[str] | None = None,
    ):
        file = self.ds.get_by_id(file_id)
        if not file:
            raise NotFoundError(f"File '{file_id}' not found")
        stage = self.stage_ds.get_by_id(file.rfq_stage_id)
        if not stage:
            raise NotFoundError(f"Stage '{file.rfq_stage_id}' not found for file '{file_id}'")
        self._validate_delete_scope(stage.assigned_team, actor_team, actor_permissions)
        self.ds.soft_delete(file)
        self.session.commit()

    @staticmethod
    def _validate_delete_scope(
        stage_team: str | None,
        actor_team: str | None,
        actor_permissions: Sequence[str] | None,
    ) -> None:
        normalized_stage_team = (stage_team or "").strip().lower()
        normalized_actor_team = (actor_team or "").strip().lower()
        permissions = {
            permission.strip()
            for permission in (actor_permissions or [])
            if permission and permission.strip()
        }

        if not normalized_stage_team:
            raise ForbiddenError("File delete denied: stage has no assigned team")

        if normalized_actor_team and normalized_actor_team == normalized_stage_team:
            return

        if {
            "*",
            "file:*",
            "file:delete:any",
            "rfq:*",
        }.intersection(permissions):
            return

        raise ForbiddenError(
            f"File delete denied: actor team '{actor_team or 'unknown'}' does not match assigned team '{stage_team}'"
        )
