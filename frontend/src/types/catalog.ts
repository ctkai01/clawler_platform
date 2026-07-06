export interface EntityGazetteerItem {
  canonical_name: string
  canonical_display_name: string | null
  industry_code: string | null
  surface_form_count: number
  is_active: boolean
}

export interface KeywordCatalogItem {
  id: number
  category: 'brand' | 'competitor' | 'industry' | 'custom'
  term: string
  is_active: boolean
  created_at: string
}

export interface OrganizationItem {
  id: number
  name: string
}

export interface TopicKeywordItem {
  id: number
  keyword: string
}

export interface TopicItem {
  id: number
  name: string
  keywords: TopicKeywordItem[]
}

export interface TopicImportResult {
  total_rows: number
  topics: number
  keywords: number
  errors: string[]
}
