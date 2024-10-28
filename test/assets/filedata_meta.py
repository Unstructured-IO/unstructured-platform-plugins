import math
from typing import Optional

from pydantic import BaseModel
from unstructured_ingest.v2.interfaces import FileData

from unstructured_platform_plugins.schema import FileDataMeta, NewRecord


class Input(BaseModel):
    m: int


class Output(BaseModel):
    n: float


def process_input(i: Input, file_data: FileData, filedata_meta: FileDataMeta) -> Optional[Output]:
    if i.m > 10:
        filedata_meta.terminate_current = True
        new_content = [
            NewRecord(
                file_data=FileData(
                    identifier=str(i.m + x), connector_type=file_data.connector_type
                ),
                contents=Output(n=float(i.m + x)),
            )
            for x in range(5)
        ]
        filedata_meta.new_records.extend(new_content)
        return None
    else:
        return Output(n=math.pi + i.m)
