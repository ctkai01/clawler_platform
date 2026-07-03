import { apiClient } from '@/lib/apiClient'
import type {
  OrgEntitySelection,
  OrgKeywordSelection,
  OrgReport,
  SourceImportResult,
  SourceItem,
  SubAccount,
} from '@/types/org'

export const orgApi = {
  getReport: (days: number) => apiClient.get<OrgReport>(`/org/report?days=${days}`),

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

  listMembers: () => apiClient.get<SubAccount[]>('/org/users'),
  createMember: (body: { email: string; password: string; functional_role: string; target_ids: number[] }) =>
    apiClient.post<SubAccount>('/org/users', body),
  updateMember: (id: number, body: Partial<{ functional_role: string; target_ids: number[]; is_active: boolean }>) =>
    apiClient.patch<SubAccount>(`/org/users/${id}`, body),
  deleteMember: (id: number) => apiClient.delete<void>(`/org/users/${id}`),
}
