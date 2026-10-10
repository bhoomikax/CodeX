from pydantic import BaseModel


class ProblemResponse(BaseModel):
    id: int
    title: str
    platform: str
    external_id: str | None = None
    url: str | None = None
    difficulty: str
    pattern_id: int
    description: str | None = None
    description: str | None = None

    class Config:
        from_attributes = True