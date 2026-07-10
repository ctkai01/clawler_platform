from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=1)
    tier: str = Field(default="basic")
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    organization_id: int | None
    organization_name: str | None
    functional_role: str | None
    accessible_target_ids: list[int] | None


class EntityGazetteerCreate(BaseModel):
    """Adds one (concept_id, surface_form) row under a canonical_name. To
    add more surface forms for an existing brand, call this again with a
    different concept_id/surface_form and the same canonical_name."""

    canonical_name: str = Field(min_length=1)
    concept_id: str = Field(min_length=1)
    surface_form: str = Field(min_length=1)
    industry_code: str | None = None
    entity_type: str = Field(default="company")


class EntityGazetteerUpdate(BaseModel):
    is_active: bool | None = None


class EntityGazetteerOut(BaseModel):
    canonical_name: str
    canonical_display_name: str | None
    industry_code: str | None
    surface_form_count: int
    is_active: bool


class KeywordCatalogCreate(BaseModel):
    category: str = Field(pattern="^(brand|competitor|industry|custom)$")
    term: str = Field(min_length=1)


class KeywordCatalogUpdate(BaseModel):
    category: str | None = Field(default=None, pattern="^(brand|competitor|industry|custom)$")
    term: str | None = None
    is_active: bool | None = None


class KeywordCatalogOut(BaseModel):
    id: int
    category: str
    term: str
    is_active: bool
    created_at: datetime


class SourceCreate(BaseModel):
    platform_type: str = Field(min_length=1)
    url: str = Field(min_length=1)
    display_name: str | None = None
    crawl_interval_sec: int = Field(default=900, ge=60)


class SourceUpdate(BaseModel):
    display_name: str = Field(min_length=1)


class SourceOut(BaseModel):
    id: int
    platform_type: str
    url: str
    display_name: str | None
    enabled: bool
    crawl_interval_sec: int
    last_crawled_at: datetime | None
    last_status: str | None


class SourceImportResult(BaseModel):
    total_rows: int
    inserted: int
    skipped: int
    errors: list[str]


class SourceStatusCount(BaseModel):
    platform_type: str
    status: str
    count: int


class FailingSourceOut(BaseModel):
    id: int
    platform_type: str
    display_name: str | None
    url: str
    last_status: str | None
    last_error: str | None
    consecutive_failures: int
    last_crawled_at: datetime | None
    fb_session_key: str | None


class CrawledSourceOut(BaseModel):
    id: int
    platform_type: str
    display_name: str | None
    url: str
    last_status: str | None
    last_crawled_at: datetime | None
    document_count: int


class DocumentThroughputPoint(BaseModel):
    day: date
    platform_type: str
    count: int


class RecentDocumentOut(BaseModel):
    id: int
    platform_type: str
    topic: str | None
    url: str
    target_name: str | None
    first_seen_at: datetime


class DagRunOut(BaseModel):
    dag_id: str
    run_id: str
    state: str
    execution_date: datetime | None
    start_date: datetime | None
    end_date: datetime | None
    duration_sec: float | None


class SystemStats(BaseModel):
    cpu_percent: float
    mem_percent: float
    mem_used_gb: float
    mem_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    load_avg_1m: float


class MonitoringOverview(BaseModel):
    sources_by_status: list[SourceStatusCount]
    failing_sources: list[FailingSourceOut]
    crawled_sources: list[CrawledSourceOut]
    document_throughput: list[DocumentThroughputPoint]
    dag_runs: list[DagRunOut]
    recent_documents: list[RecentDocumentOut]
    airflow_unreachable: bool


class OrganizationOut(BaseModel):
    id: int
    name: str


class TopicKeywordOut(BaseModel):
    id: int
    keyword: str


class TopicCreate(BaseModel):
    name: str = Field(min_length=1)


class TopicOut(BaseModel):
    id: int
    name: str
    keywords: list[TopicKeywordOut]


class TopicKeywordCreate(BaseModel):
    keyword: str = Field(min_length=1)


class TopicImportResult(BaseModel):
    total_rows: int
    topics: int
    keywords: int
    errors: list[str]


class SubAccountCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    functional_role: str = Field(pattern="^(report_viewer|configurator)$")
    target_ids: list[int] = Field(default_factory=list)


class SubAccountUpdate(BaseModel):
    functional_role: str | None = Field(default=None, pattern="^(report_viewer|configurator)$")
    target_ids: list[int] | None = None
    is_active: bool | None = None


class SubAccountOut(BaseModel):
    id: int
    email: str
    functional_role: str
    is_active: bool
    target_ids: list[int]


class OrgEntitySelection(BaseModel):
    canonical_name: str
    industry_code: str | None
    is_selected: bool


class OrgEntitySelectRequest(BaseModel):
    canonical_name: str = Field(min_length=1)


class OrgKeywordSelection(BaseModel):
    keyword_id: int
    category: str
    term: str
    is_selected: bool


class DocumentListItem(BaseModel):
    id: int
    platform_type: str
    source_type: str
    target_name: str | None
    author: str | None
    topic: str | None
    content_snippet: str
    url: str
    published_at: datetime | None
    like_count: int
    comment_count: int
    reaction_count: int
    share_count: int
    keyword_status: str
    matched_keywords: list[str]
    classification_category: str | None
    classification_sentiment: str | None
    classification_severity: int | None
    entities: list[str]


class DocumentListResponse(BaseModel):
    items: list[DocumentListItem]
    total: int


class DocumentDetailOut(BaseModel):
    id: int
    platform_type: str
    source_type: str
    target_name: str | None
    author: str | None
    topic: str | None
    content: str
    url: str
    published_at: datetime | None
    images: list[str]
    videos: list[str]
    like_count: int
    comment_count: int
    reaction_count: int
    share_count: int
    reactions: dict[str, int]
    keyword_status: str
    matched_keywords: list[str]
    classification_category: str | None
    classification_sentiment: str | None
    classification_sentiment_source: str | None
    classification_severity: int | None
    classification_reasoning: str | None
    classification_text_summary: str | None
    classification_image_summary: str | None
    entities: list[str]


class DocumentCommentOut(BaseModel):
    author: str | None
    text: str
    created_at: datetime | None
    depth: int


class AccordionCategoryCounts(BaseModel):
    facebook_group: int = 0
    facebook_page: int = 0
    forum: int = 0
    news: int = 0


class AccordionSentimentCounts(BaseModel):
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    unclassified: int = 0
    competitor: int = 0


class EngagementGrowthPoint(BaseModel):
    bucket: datetime
    like_count: int
    comment_count: int
    reaction_count: int
    share_count: int


class EntityNetworkNode(BaseModel):
    canonical_name: str
    post_count: int


class EntityNetworkEdge(BaseModel):
    source: str
    target: str
    weight: int


class EntityNetworkResponse(BaseModel):
    nodes: list[EntityNetworkNode]
    edges: list[EntityNetworkEdge]
    focus_canonical_name: str | None = None


class RelatedDocumentItem(BaseModel):
    id: int
    platform_type: str
    target_name: str | None
    topic: str | None
    content_snippet: str
    published_at: datetime | None
    classification_sentiment: str | None
    shared_entities: int
