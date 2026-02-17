from typing import Any

from pydantic import BaseModel, Field
from unstructured_ingest.data_types.file_data import FileData


class NewRecord(BaseModel):
    file_data: FileData
    contents: Any


class FileDataMeta(BaseModel):
    terminate_current: bool = False
    new_records: list[NewRecord] = Field(default_factory=list)
