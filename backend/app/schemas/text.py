from datetime import datetime

from pydantic import BaseModel


class TextBase(BaseModel):
    taisho_id: str | None = None
    cbeta_id: str
    title_zh: str
    title_sa: str | None = None
    title_bo: str | None = None
    title_pi: str | None = None
    translator: str | None = None
    dynasty: str | None = None
    fascicle_count: int | None = None
    category: str | None = None
    subcategory: str | None = None
    cbeta_url: str | None = None


class TextIdentifierBrief(BaseModel):
    source_code: str
    source_name: str
    source_uid: str
    source_url: str | None = None


class TextResponseBase(TextBase):
    """Base response without lazy-loaded fields (safe for from_attributes)."""
    id: int
    has_content: bool = False
    content_char_count: int = 0
    lang: str = "lzh"
    created_at: datetime

    model_config = {"from_attributes": True}


class TextResponse(TextResponseBase):
    """Extended response; source_name and identifiers are set manually when needed."""
    source_name: str | None = None
    identifiers: list[TextIdentifierBrief] = []


class JuanInfo(BaseModel):
    juan_num: int
    char_count: int


class JuanListResponse(BaseModel):
    text_id: int
    title_zh: str
    total_juans: int
    juans: list[JuanInfo]


class JuanLanguagesResponse(BaseModel):
    text_id: int
    juan_num: int
    languages: list[str]
    default_lang: str


class JuanContentResponse(BaseModel):
    text_id: int
    cbeta_id: str
    title_zh: str
    juan_num: int
    total_juans: int
    content: str
    char_count: int
    lang: str = "lzh"
    prev_juan: int | None = None
    next_juan: int | None = None


class RelatedTranslation(BaseModel):
    id: int
    title: str
    lang: str
    relation_type: str


class SearchHit(BaseModel):
    id: int
    taisho_id: str | None = None
    cbeta_id: str
    title_zh: str
    translator: str | None = None
    dynasty: str | None = None
    category: str | None = None
    cbeta_url: str | None = None
    has_content: bool = False
    source_code: str | None = None
    score: float | None = None
    highlight: dict[str, list[str]] | None = None
    related_translations: list[RelatedTranslation] = []


class SearchResponse(BaseModel):
    total: int
    page: int
    size: int
    results: list[SearchHit]
    suggestion: str | None = None


class CrossLanguageSearchHit(BaseModel):
    id: int
    taisho_id: str | None = None
    cbeta_id: str
    title_zh: str
    title_en: str | None = None
    title_sa: str | None = None
    title_pi: str | None = None
    title_bo: str | None = None
    translator: str | None = None
    dynasty: str | None = None
    category: str | None = None
    cbeta_url: str | None = None
    has_content: bool = False
    source_code: str | None = None
    lang: str = "lzh"
    score: float | None = None
    highlight: dict[str, list[str]] | None = None
    related_translations: list[RelatedTranslation] = []


class CrossLanguageSearchResponse(BaseModel):
    total: int
    page: int
    size: int
    results: list[CrossLanguageSearchHit]
    suggestion: str | None = None
