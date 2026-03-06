"""
File translator — converts between Pydantic schemas and the RfqFile SQLAlchemy model.

Functions:
- to_schema(model)  — RfqFile model → StageFile response schema
"""
from typing import List
from pydantic import BaseModel
from src.translators.rfq_stage_translator import StageFileResponse

class StageFileListResponse(BaseModel):
    data: List[StageFileResponse]

def to_response(file) -> StageFileResponse:
    return StageFileResponse.model_validate(file)
