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
