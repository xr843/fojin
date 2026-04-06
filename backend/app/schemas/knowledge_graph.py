from pydantic import BaseModel


class KGEntityResponse(BaseModel):
    id: int
    entity_type: str
    name_zh: str
    name_sa: str | None = None
    name_pi: str | None = None
    name_bo: str | None = None
    name_en: str | None = None
    description: str | None = None
    properties: dict | None = None
    text_id: int | None = None
    external_ids: dict | None = None

    model_config = {"from_attributes": True}


class EntityRelationItem(BaseModel):
    predicate: str
    direction: str  # "outgoing" or "incoming"
    target_id: int
    target_name: str
    target_type: str
    confidence: float = 1.0
    source: str | None = None


class KGEntityDetailResponse(KGEntityResponse):
    relations: list[EntityRelationItem] = []


class KGRelationResponse(BaseModel):
    id: int
    subject_id: int
    predicate: str
    object_id: int
    properties: dict | None = None
    source: str | None = None
    confidence: float = 1.0

    model_config = {"from_attributes": True}


class KGGraphNode(BaseModel):
    id: int
    name: str
    entity_type: str
    description: str | None = None


class KGGraphLink(BaseModel):
    source: int
    target: int
    predicate: str
    confidence: float = 1.0
    provenance: str | None = None
    evidence: str | None = None


class KGGraphResponse(BaseModel):
    nodes: list[KGGraphNode]
    links: list[KGGraphLink]
    truncated: bool = False


class KGSearchResponse(BaseModel):
    total: int
    results: list[KGEntityResponse]


class KGGeoEntity(BaseModel):
    id: int
    entity_type: str
    name_zh: str
    name_en: str | None = None
    description: str | None = None
    latitude: float
    longitude: float
    year_start: int | None = None
    year_end: int | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None


class KGGeoResponse(BaseModel):
    entities: list[KGGeoEntity]
    total: int


class KGLineageArc(BaseModel):
    teacher_id: int
    teacher_name: str
    teacher_lat: float
    teacher_lng: float
    student_id: int
    student_name: str
    student_lat: float
    student_lng: float
    year: int | None = None
    school: str | None = None


class KGLineageArcsResponse(BaseModel):
    arcs: list[KGLineageArc]
    total: int
