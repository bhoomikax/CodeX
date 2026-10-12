from pydantic import BaseModel, ConfigDict


class SampleCase(BaseModel):
    input: str
    expected_output: str


class ProblemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    platform: str
    external_id: str | None = None
    url: str | None = None
    difficulty: str
    pattern_id: int
    description: str | None = None
    test_cases_available: bool = False
    # Only cases flagged visible are exposed; hidden expected outputs stay server-side.
    sample_cases: list[SampleCase] = []
