"""
File controller — business logic for the File resource.

Orchestrates:
- List files for a stage (WHERE deleted_at IS NULL)
- Download file (stream from local storage or generate signed Azure Blob URL)
- Soft-delete file (set deleted_at = NOW())

Dependencies: FileDatasource
"""

import os
from sqlalchemy.orm import Session

from src.datasources.file_datasource import FileDatasource
from src.datasources.rfq_stage_datasource import RfqStageDatasource
from src.translators import file_translator
from src.utils.errors import NotFoundError


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
        if not os.path.exists(file.file_path):
            raise NotFoundError(f"File '{file.filename}' not found on disk")
        return file.file_path, file.filename

    def delete(self, file_id):
        file = self.ds.get_by_id(file_id)
        if not file:
            raise NotFoundError(f"File '{file_id}' not found")
        self.ds.soft_delete(file)
        self.session.commit()
