from datetime import datetime

from pydantic import BaseModel


class GaijiResponse(BaseModel):
    id: int
    cb_code: str
    composition: str | None = None
    unicode_char: str | None = None
    unicode_codepoint: str | None = None
    norm_unicode_char: str | None = None
    norm_big5_char: str | None = None
    pua_codepoint: str | None = None
    description: str | None = None
    image_url: str | None = None
    moe_variant_id: str | None = None
    source: str = "cbeta"
    upstream_version: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
