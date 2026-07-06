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
  industry_code: string | null
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

export interface TopicDetailRow {
  topic: string
  posts: number
  comments: number
  total_engagement: number
}

export interface ReportPostItem {
  id: number
  title: string
  url: string
  channel_label: string
  author: string | null
  engagement_total: number
}

export interface OrgReport {
  total_posts: number
  total_comments: number
  total_reactions: number
  total_shares: number
  sentiment_positive: number
  sentiment_negative: number
  sentiment_neutral: number
  topic_detail: TopicDetailRow[]
  keyword_topic_detail: TopicDetailRow[]
  topics: string[]
  topic_positive_counts: number[]
  topic_neutral_counts: number[]
  topic_negative_counts: number[]
  negative_count: number
  positive_count: number
  negative_posts: ReportPostItem[]
  positive_posts: ReportPostItem[]
}

export interface ReportPostsResponse {
  items: ReportPostItem[]
  total: number
}

export interface DocumentListItem {
  id: number
  platform_type: string
  source_type: string
  target_name: string | null
  author: string | null
  topic: string | null
  content_snippet: string
  url: string
  published_at: string | null
  like_count: number
  comment_count: number
  reaction_count: number
  share_count: number
  keyword_status: string
  matched_keywords: string[]
  classification_category: string | null
  classification_sentiment: string | null
  classification_severity: number | null
  entities: string[]
}

export interface DocumentListResponse {
  items: DocumentListItem[]
  total: number
}

export interface DocumentDetail {
  id: number
  platform_type: string
  source_type: string
  target_name: string | null
  author: string | null
  topic: string | null
  content: string
  url: string
  published_at: string | null
  images: string[]
  videos: string[]
  like_count: number
  comment_count: number
  reaction_count: number
  share_count: number
  reactions: Record<string, number>
  keyword_status: string
  matched_keywords: string[]
  classification_category: string | null
  classification_sentiment: string | null
  classification_sentiment_source: string | null
  classification_severity: number | null
  classification_reasoning: string | null
  entities: string[]
}

export interface DocumentComment {
  author: string | null
  text: string
  created_at: string | null
  depth: number
}

export interface DocumentListParams {
  page: number
  page_size?: number
  entity?: string
  entity_exact?: boolean
  keyword?: string
  platform_type?: string
  sentiment?: string
  search?: string
  days?: number
  date_from?: string
  date_to?: string
}

export interface AccordionFilterParams {
  search?: string
  entity?: string
  entity_exact?: boolean
  days?: number
  date_from?: string
  date_to?: string
}

export interface AccordionCategoryCounts {
  facebook_group: number
  facebook_page: number
  forum: number
  news: number
}

export type AccordionSentimentKey = 'positive' | 'negative' | 'neutral' | 'unclassified'

export interface AccordionSentimentCounts {
  positive: number
  negative: number
  neutral: number
  unclassified: number
}

export interface EngagementGrowthPoint {
  bucket: string
  like_count: number
  comment_count: number
  reaction_count: number
  share_count: number
}

export interface EntityNetworkNode {
  canonical_name: string
  post_count: number
}

export interface EntityNetworkEdge {
  source: string
  target: string
  weight: number
}

export interface EntityNetworkResponse {
  nodes: EntityNetworkNode[]
  edges: EntityNetworkEdge[]
  focus_canonical_name?: string | null
}

export interface RelatedDocumentItem {
  id: number
  platform_type: string
  target_name: string | null
  topic: string | null
  content_snippet: string
  published_at: string | null
  classification_sentiment: string | null
  shared_entities: number
}
