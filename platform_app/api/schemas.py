from __future__ import annotations

from datetime import datetime

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
    crawl_interval_sec: int = Field(default=3600, ge=60)


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
    is_selected: bool


class OrgEntitySelectRequest(BaseModel):
    canonical_name: str = Field(min_length=1)


class OrgKeywordSelection(BaseModel):
    keyword_id: int
    category: str
    term: str
    is_selected: bool
