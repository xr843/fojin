from datetime import datetime

from pydantic import BaseModel


class WorkDetailResponse(BaseModel):
    """FRBR Work 详情：聚合作品的全部元数据 + 见证本计数。"""

    id: int
    slug: str
    title_primary: str
    title_sa: str | None = None
    title_pi: str | None = None
    sc_root_uid: str | None = None
    toh_number: str | None = None
    category: str | None = None
    note: str | None = None
    created_at: datetime
    witness_count: int = 0

    model_config = {"from_attributes": True}


class WorkWitnessResponse(BaseModel):
    """Work 的单个见证本，已 join BuddhistText 富化标题 / 内容标志。"""

    text_id: int
    cbeta_id: str | None = None
    title: str | None = None
    lang: str
    canon: str | None = None
    role: str
    confidence: str
    has_content: bool = False


class WorkListItem(BaseModel):
    """Work 列表项：精简元数据 + 见证本计数 + 涵盖语言。"""

    slug: str
    title_primary: str
    title_sa: str | None = None
    witness_count: int = 0
    langs: list[str] = []


class WorkListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[WorkListItem]


class WorkByTextResponse(BaseModel):
    """给定一条经文，返回它所属作品 + 全部见证本（含自身，前端按需排除自身）。"""

    slug: str
    title_primary: str
    title_sa: str | None = None
    witness_count: int = 0
    witnesses: list[WorkWitnessResponse] = []
