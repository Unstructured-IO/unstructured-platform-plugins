from pydantic import BaseModel


# This is a stand in until a supported schema is published external to this repo
class UsageData(BaseModel):
    value: int
    name: str
