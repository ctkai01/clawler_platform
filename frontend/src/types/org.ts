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

export interface SourceStatusCount {
  platform_type: string
  status: string
  count: number
}

export interface FailingSource {
  id: number
  platform_type: string
  display_name: string | null
  url: string
  last_status: string | null
  last_error: string | null
  consecutive_failures: number
  last_crawled_at: string | null
  fb_session_key: string | null
}

export interface CrawledSource {
  id: number
  platform_type: string
  display_name: string | null
  url: string
  last_status: string | null
  last_crawled_at: string | null
  document_count: number
}

export interface DocumentThroughputPoint {
  day: string
  platform_type: string
  count: number
}

export interface RecentDocument {
  id: number
  platform_type: string
  topic: string | null
  url: string
  target_name: string | null
  first_seen_at: string
}

export interface DagRunItem {
  dag_id: string
  run_id: string
  state: string
  execution_date: string | null
  start_date: string | null
  end_date: string | null
  duration_sec: number | null
}

export interface SystemStats {
  cpu_percent: number
  mem_percent: number
  mem_used_gb: number
  mem_total_gb: number
  disk_percent: number
  disk_used_gb: number
  disk_total_gb: number
  load_avg_1m: number
}

export interface MonitoringOverview {
  sources_by_status: SourceStatusCount[]
  failing_sources: FailingSource[]
  crawled_sources: CrawledSource[]
  document_throughput: DocumentThroughputPoint[]
  dag_runs: DagRunItem[]
  recent_documents: RecentDocument[]
  airflow_unreachable: boolean
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

export interface TopicSentimentRow {
  topic: string
  positive: number
  neutral: number
  negative: number
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
  keyword_topic_sentiment: TopicSentimentRow[]
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
  classification_text_summary: string | null
  classification_image_summary: string | null
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

export type AccordionSentimentKey = 'positive' | 'negative' | 'neutral' | 'unclassified' | 'competitor'

export interface AccordionSentimentCounts {
  positive: number
  negative: number
  neutral: number
  unclassified: number
  competitor: number
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

// --- Báo cáo sự vụ/tiêu cực/đối thủ — JSON preview (khớp compute_*_data ở org.py) ---

export interface EventMatchItem {
  document_id: number
  brand: string
  topic: string | null
  content: string | null
  url: string
  author: string | null
  platform_type: string
  published_at: string
  engagement_total: number
  target_name: string
  sentiment: 'positive' | 'neutral' | 'negative'
  impact_level: string
  reasoning: string
  handling_status: string
  reach_tier: string | null
}

export interface EventComparisonSide {
  yesterday_total: number
  today_total: number
  yesterday_sentiment: { positive: number; neutral: number; negative: number }
  today_sentiment: { positive: number; neutral: number; negative: number }
}

export interface EventComparison {
  yesterday_label: string
  today_label: string
  news: EventComparisonSide
  social: EventComparisonSide
}

export interface EventReportData {
  org_name: string
  event_label: string
  report_date: string
  comparison: EventComparison
  overview_narrative: string
  mobifone_news: EventMatchItem[]
  competitor_news: Record<string, EventMatchItem[]>
  social_matches: EventMatchItem[]
}

export interface EventWeeklyReportData {
  org_name: string
  event_label: string
  period_label: string
  comparison: EventComparison
  overview_narrative: string
  mobifone_news: EventMatchItem[]
  competitor_news: Record<string, EventMatchItem[]>
  social_matches: EventMatchItem[]
  brand_counts: Record<string, { positive: number; neutral: number; negative: number }>
}

export interface NegativeBrandSummaryRow {
  stt: string
  label: string
  prev: number | null
  this: number | null
  pct: string | null
  compare: string | null
  bold?: boolean
}

export interface NegativeBrandReportData {
  org_name: string
  period_label: string
  period_prev_label: string
  summary_rows: NegativeBrandSummaryRow[]
  news_theme: string
  news_pct: string
  social_theme: string
  social_pct: string
  hotspot_text: string
  overview_narrative: string
}

export interface CompetitorPostItem {
  id: number
  topic: string | null
  content: string | null
  url: string
  author: string | null
  platform_type: string
  images: string[]
  target_name: string
  engagement_total: number
}

export interface CompetitorChannelReportData {
  org_name: string
  period_label: string
  brands: string[]
  brand_counts: Record<string, { positive: number; neutral: number; negative: number }>
  positive_bullets: string
  negative_bullets: string
  own_positive_posts: ReportPostItem[]
  own_negative_posts: ReportPostItem[]
  competitor_posts: Record<string, { positive: CompetitorPostItem[]; negative: CompetitorPostItem[] }>
  channel_breakdowns: Record<string, { Facebook: number; News: number; Forum: number }>
  channel_bullets: string[]
}
