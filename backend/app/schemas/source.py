from datetime import datetime

from pydantic import BaseModel, Field


class SourceDistributionResponse(BaseModel):
    id: int
    code: str
    name: str
    channel_type: str
    url: str
    format: str | None = None
    license_note: str | None = None
    is_primary_ingest: bool = False
    priority: int = 100
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceDistributionListResponse(SourceDistributionResponse):
    source_id: int
    source_code: str
    source_name: str


class DataSourceResponse(BaseModel):
    id: int
    code: str
    name_zh: str
    name_en: str | None = None
    base_url: str | None = None
    api_url: str | None = None
    description: str | None = None
    access_type: str = "external"
    region: str | None = None
    languages: str | None = None
    research_fields: str | None = None
    supports_search: bool = False
    supports_fulltext: bool = False
    has_local_fulltext: bool = False
    has_remote_fulltext: bool = False
    supports_iiif: bool = False
    supports_api: bool = False
    is_active: bool = True
    created_at: datetime
    distributions: list[SourceDistributionResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TextIdentifierResponse(BaseModel):
    id: int
    source_id: int
    source_code: str
    source_name: str
    source_uid: str
    source_url: str | None = None

    model_config = {"from_attributes": True}
