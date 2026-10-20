import logging
from typing import Annotated

from fastapi import HTTPException
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelCallError, ModelOutputError, VisionModel
from app.ai.registry import get_model
from app.ai.usage import record_usage
from app.grading.crop import prepare_image
from app.grading.prompts import build_answer_key_prompt
from app.grading.schema import _coerce_no

log = logging.getLogger(__name__)

ATTEMPTS = 2

def _clean_no(v: str) -> str:
    v = v.strip()
    if not 1 <= len(v) <= 32:
        raise ValueError("question_no must be 1-32 characters")
    return v


QuestionNo = Annotated[str, BeforeValidator(_coerce_no), AfterValidator(_clean_no)]


def get_answer_key_model() -> VisionModel:
    """FastAPI dependency; tests override it."""
    return get_model("answer_key")


class AnswerKeyItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question_no: QuestionNo
    answer: str
    max_score: float = Field(ge=0)
    is_subjective: bool = False


class ExtractedKey(BaseModel):
    model_config = ConfigDict(extra="ignore")

    questions: list[AnswerKeyItem]


async def extract_answer_key(
    db: AsyncSession, model: VisionModel, teacher_id: int, image: bytes
) -> list[AnswerKeyItem]:
    """Ask the model for the answer key. Usage of every returned call is recorded (flushed, not
    committed); failures raise HTTPException with the status to report."""
    try:
        prepared = prepare_image(image)
    except Exception:
        raise HTTPException(status_code=415, detail="无法解析图片") from None
    prompt = build_answer_key_prompt()
    for attempt in range(ATTEMPTS):
        try:
            result = await model.complete_json(prompt, [prepared])
        except ModelCallError:
            raise HTTPException(status_code=503, detail="批改服务暂不可用，请稍后重试") from None
        except ModelOutputError:
            log.warning("answer key attempt %s: model output is not JSON", attempt + 1)
            continue
        await record_usage(db, teacher_id, "answer_key", result)
        try:
            items = ExtractedKey.model_validate(result.data).questions
        except ValidationError:
            log.warning("answer key attempt %s: output failed validation", attempt + 1)
            continue
        if not items:
            raise HTTPException(status_code=422, detail="未识别到题目")
        return items
    raise HTTPException(status_code=502, detail="答案卷识别失败，请重拍")
