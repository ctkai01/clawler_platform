export interface SourceItem {
  id: number
  platform_type: string
  url: string
  display_name: string | null
  enabled: boolean
  crawl_interval_sec: number
  last_crawled_at: string | null
  last_status: string | null
}

export interface OrgEntitySelection {
  canonical_name: string
  is_selected: boolean
}

export interface OrgKeywordSelection {
  keyword_id: number
  category: string
  term: string
  is_selected: boolean
}

export interface SubAccount {
  id: number
  email: string
  functional_role: 'report_viewer' | 'configurator'
  is_active: boolean
  target_ids: number[]
}

export interface SourceImportResult {
  total_rows: number
  inserted: number
  skipped: number
  errors: string[]
}

export interface OrgReport {
  total_posts: number
  total_comments: number
  total_reactions: number
  total_shares: number
  sentiment_positive: number
  sentiment_negative: number
  sentiment_neutral: number
}
