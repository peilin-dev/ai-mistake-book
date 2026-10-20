from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def _coerce_no(v):
    # Models sometimes emit the question number as an int.
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else str(v)
    return v


UnitFloat = Annotated[float, Field(ge=0, le=1)]


class GradedQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    no: Annotated[str, BeforeValidator(_coerce_no)]
    question_text: str
    student_answer: str | None
    correct_answer: str | None
    is_subjective: bool = False
    is_correct: bool
    score: float = Field(ge=0)
    max_score: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    bbox: tuple[UnitFloat, UnitFloat, UnitFloat, UnitFloat]
    knowledge_point_id: int | None = None
    error_reason: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.score > self.max_score:
            raise ValueError("score must not exceed max_score")
        x1, y1, x2, y2 = self.bbox
        if not (x1 < x2 and y1 < y2):
            raise ValueError("bbox must satisfy x1 < x2 and y1 < y2")
        return self


class GradedPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    student_name: str | None
    questions: list[GradedQuestion]
