import { apiClient } from '@/lib/apiClient'
import type {
  AccordionCategoryCounts,
  AccordionFilterParams,
  AccordionSentimentCounts,
  DocumentComment,
  DocumentDetail,
  DocumentListParams,
  DocumentListResponse,
  EngagementGrowthPoint,
  EntityNetworkResponse,
  OrgEntitySelection,
  OrgKeywordSelection,
  OrgReport,
  RelatedDocumentItem,
  ReportPostsResponse,
  SourceImportResult,
  SourceItem,
  SubAccount,
} from '@/types/org'

export interface ClassifyModeSetting {
  mode: string
  modes: string[]
}

export interface ReportEmailSetting {
  recipient_email: string | null
  cc_emails: string[]
  enabled: boolean
}

function accordionQuery(params: AccordionFilterParams, extra?: Record<string, string | number>): string {
  const search = new URLSearchParams()
  if (params.search) search.set('search', params.search)
  if (params.entity) search.set('entity', params.entity)
  search.set('entity_exact', String(params.entity_exact ?? false))
  if (params.date_from || params.date_to) {
    if (params.date_from) search.set('date_from', params.date_from)
    if (params.date_to) search.set('date_to', params.date_to)
  } else if (params.days) {
    search.set('days', String(params.days))
  }
  if (extra) {
    for (const [key, value] of Object.entries(extra)) search.set(key, String(value))
  }
  return search.toString()
}

export const orgApi = {
  getReport: (days: number, entity?: string) => {
    const search = new URLSearchParams()
    search.set('days', String(days))
    if (entity) search.set('entity', entity)
    return apiClient.get<OrgReport>(`/org/report?${search.toString()}`)
  },
  exportReport: (days: number, entity?: string) => {
    const search = new URLSearchParams()
    search.set('days', String(days))
    if (entity) search.set('entity', entity)
    return apiClient.download(`/org/report/export?${search.toString()}`, `bao-cao-${days}ngay.xlsx`)
  },
  sendReportEmailNow: (days: number, entity?: string) => {
    const search = new URLSearchParams()
    search.set('days', String(days))
    if (entity) search.set('entity', entity)
    return apiClient.post<{ sent_to: string; cc: string[] }>(`/org/report/send-email?${search.toString()}`)
  },
  getReportPosts: (params: {
    sentiment: 'positive' | 'negative'
    days: number
    entity?: string
    page: number
    page_size?: number
  }) => {
    const search = new URLSearchParams()
    search.set('sentiment', params.sentiment)
    search.set('days', String(params.days))
    if (params.entity) search.set('entity', params.entity)
    search.set('page', String(params.page))
    search.set('page_size', String(params.page_size ?? 10))
    return apiClient.get<ReportPostsResponse>(`/org/report/posts?${search.toString()}`)
  },

  listSources: () => apiClient.get<SourceItem[]>('/org/sources'),
  createSource: (body: { platform_type: string; url: string; display_name?: string }) =>
    apiClient.post<SourceItem>('/org/sources', body),
  deleteSource: (id: number) => apiClient.delete<void>(`/org/sources/${id}`),
  importSources: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.postForm<SourceImportResult>('/org/sources/import', formData)
  },

  listEntities: () => apiClient.get<OrgEntitySelection[]>('/org/entities'),
  selectEntity: (canonicalName: string) => apiClient.post<void>('/org/entities/select', { canonical_name: canonicalName }),
  deselectEntity: (canonicalName: string) =>
    apiClient.post<void>('/org/entities/deselect', { canonical_name: canonicalName }),

  listKeywords: () => apiClient.get<OrgKeywordSelection[]>('/org/keywords'),
  selectKeyword: (id: number) => apiClient.post<void>(`/org/keywords/${id}/select`),
  deselectKeyword: (id: number) => apiClient.delete<void>(`/org/keywords/${id}/select`),

  listDocuments: (params: DocumentListParams) => {
    const search = new URLSearchParams()
    search.set('page', String(params.page))
    if (params.page_size) search.set('page_size', String(params.page_size))
    if (params.entity) search.set('entity', params.entity)
    if (params.entity_exact !== undefined) search.set('entity_exact', String(params.entity_exact))
    if (params.keyword) search.set('keyword', params.keyword)
    if (params.platform_type) search.set('platform_type', params.platform_type)
    if (params.sentiment) search.set('sentiment', params.sentiment)
    if (params.search) search.set('search', params.search)
    if (params.date_from || params.date_to) {
      if (params.date_from) search.set('date_from', params.date_from)
      if (params.date_to) search.set('date_to', params.date_to)
    } else if (params.days) {
      search.set('days', String(params.days))
    }
    return apiClient.get<DocumentListResponse>(`/org/documents?${search.toString()}`)
  },
  getDocument: (id: number) => apiClient.get<DocumentDetail>(`/org/documents/${id}`),
  getDocumentComments: (id: number) => apiClient.get<DocumentComment[]>(`/org/documents/${id}/comments`),

  getAccordionCounts: (params: AccordionFilterParams) =>
    apiClient.get<AccordionCategoryCounts>(`/org/documents/accordion/counts?${accordionQuery(params)}`),
  getAccordionSentimentCounts: (platformType: string, params: AccordionFilterParams) =>
    apiClient.get<AccordionSentimentCounts>(
      `/org/documents/accordion/sentiment-counts?${accordionQuery(params, { platform_type: platformType })}`,
    ),
  getAccordionGrowth: (platformType: string, params: AccordionFilterParams) =>
    apiClient.get<EngagementGrowthPoint[]>(
      `/org/documents/accordion/growth?${accordionQuery(params, { platform_type: platformType })}`,
    ),
  getAccordionNetwork: (platformType: string, params: AccordionFilterParams, maxNodes = 20) =>
    apiClient.get<EntityNetworkResponse>(
      `/org/documents/accordion/network?${accordionQuery(params, { platform_type: platformType, max_nodes: maxNodes })}`,
    ),
  getRelatedDocuments: (id: number, sentiments?: string[], limit = 10) => {
    const search = new URLSearchParams()
    search.set('limit', String(limit))
    for (const s of sentiments ?? []) search.append('sentiment', s)
    return apiClient.get<RelatedDocumentItem[]>(`/org/documents/${id}/related?${search.toString()}`)
  },
  getDocumentEntityNetwork: (id: number, focus?: string, focusExact?: boolean) => {
    const search = new URLSearchParams()
    if (focus) search.set('focus', focus)
    if (focusExact !== undefined) search.set('focus_exact', String(focusExact))
    return apiClient.get<EntityNetworkResponse>(`/org/documents/${id}/entity-network?${search.toString()}`)
  },

  getClassifyMode: () => apiClient.get<ClassifyModeSetting>('/org/settings/classify-mode'),
  updateClassifyMode: (mode: string) =>
    apiClient.patch<ClassifyModeSetting>('/org/settings/classify-mode', { mode }),

  getReportEmail: () => apiClient.get<ReportEmailSetting>('/org/settings/report-email'),
  updateReportEmail: (body: { recipient_email: string; cc_emails: string[]; enabled: boolean }) =>
    apiClient.patch<ReportEmailSetting>('/org/settings/report-email', body),

  listMembers: () => apiClient.get<SubAccount[]>('/org/users'),
  createMember: (body: { email: string; password: string; functional_role: string; target_ids: number[] }) =>
    apiClient.post<SubAccount>('/org/users', body),
  updateMember: (id: number, body: Partial<{ functional_role: string; target_ids: number[]; is_active: boolean }>) =>
    apiClient.patch<SubAccount>(`/org/users/${id}`, body),
  deleteMember: (id: number) => apiClient.delete<void>(`/org/users/${id}`),
}
