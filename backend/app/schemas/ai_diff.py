from pydantic import BaseModel, Field


class AiDiffChunk(BaseModel):
    """One paragraph the user selected for cross-version analysis."""
    text_id: int
    juan_num: int
    chunk_index: int
    lang: str = Field(..., description="One of lzh/pi/sa/bo/en")
    text: str = Field(..., min_length=1, max_length=3000)


class AiDiffRequest(BaseModel):
    chunks: list[AiDiffChunk] = Field(..., min_length=2, max_length=4)


class AiDiffResponse(BaseModel):
    cached: bool
    prompt_version: str
    model: str
    analysis: dict
    """Free-shape analysis object from the LLM. V1 prompt asks for keys:
    `summary` (str), `differences` (list[str]), `doctrinal_notes` (str).
    Stored as JSON; frontend renders defensively.
    """
