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
    # Number of KG relations touching this entity. Populated by
    # search_entities (used for degree-ranked results + UI badge);
    # defaults to 0 for endpoints that don't compute it.
    relation_count: int = 0

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


class KGTimelineEntity(BaseModel):
    id: int
    name_zh: str
    entity_type: str
    year_start: int
    year_end: int | None = None


class KGTimelineResponse(BaseModel):
    entities: list[KGTimelineEntity]
    total: int


class KGMentionItem(BaseModel):
    """An entity whose name_zh appears as a substring of another entity's description.

    Used for the "描述中提及" panel: surfaces soft/inferred connections so
    isolated nodes (DILA persons with no structured kg_relations) still
    have navigable context.  The relation is NOT written to kg_relations —
    it's computed on demand.
    """
    id: int
    name_zh: str
    entity_type: str
    snippet: str | None = None


class KGMentionsResponse(BaseModel):
    mentions: list[KGMentionItem]


class KGPathResponse(BaseModel):
    """Shortest undirected path between two KG entities.

    两实体间最短无向路径查询结果。"""
    found: bool
    hops: int
    nodes: list[KGGraphNode]
    links: list[KGGraphLink]
