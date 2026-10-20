from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelResult
from app.config import get_settings
from app.models import UsageRecord


async def record_usage(db: AsyncSession, teacher_id: int, purpose: str, result: ModelResult) -> None:
    """Add a usage row and flush; the caller commits. Models without a price cost 0."""
    price_in, price_out = get_settings().PRICE_FEN_PER_1K.get(result.model, (0.0, 0.0))
    cost = result.input_tokens / 1000 * price_in + result.output_tokens / 1000 * price_out
    db.add(UsageRecord(
        teacher_id=teacher_id,
        provider=result.provider,
        model=result.model,
        purpose=purpose,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_fen=round(cost, 4),
    ))
    await db.flush()