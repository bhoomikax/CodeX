from pydantic import BaseModel, ConfigDict


class PatternResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
