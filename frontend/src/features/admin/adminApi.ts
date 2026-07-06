import { apiClient } from '@/lib/apiClient'
import type {
  EntityGazetteerItem,
  KeywordCatalogItem,
  OrganizationItem,
  TopicImportResult,
  TopicItem,
} from '@/types/catalog'

export const adminApi = {
  listEntities: () => apiClient.get<EntityGazetteerItem[]>('/admin/entities'),
  createEntity: (body: { canonical_name: string; concept_id: string; surface_form: string; industry_code?: string }) =>
    apiClient.post<EntityGazetteerItem>('/admin/entities', body),
  updateEntity: (canonicalName: string, body: Partial<Pick<EntityGazetteerItem, 'is_active'>>) =>
    apiClient.patch<EntityGazetteerItem>(`/admin/entities/${encodeURIComponent(canonicalName)}`, body),
  deleteEntity: (canonicalName: string) => apiClient.delete<void>(`/admin/entities/${encodeURIComponent(canonicalName)}`),

  listKeywords: () => apiClient.get<KeywordCatalogItem[]>('/admin/keywords'),
  createKeyword: (body: { category: string; term: string }) =>
    apiClient.post<KeywordCatalogItem>('/admin/keywords', body),
  updateKeyword: (id: number, body: Partial<Pick<KeywordCatalogItem, 'is_active'>>) =>
    apiClient.patch<KeywordCatalogItem>(`/admin/keywords/${id}`, body),
  deleteKeyword: (id: number) => apiClient.delete<void>(`/admin/keywords/${id}`),

  listOrganizations: () => apiClient.get<OrganizationItem[]>('/admin/organizations'),

  listTopics: (organizationId: number) => apiClient.get<TopicItem[]>(`/admin/organizations/${organizationId}/topics`),
  createTopic: (organizationId: number, name: string) =>
    apiClient.post<TopicItem>(`/admin/organizations/${organizationId}/topics`, { name }),
  deleteTopic: (organizationId: number, topicId: number) =>
    apiClient.delete<void>(`/admin/organizations/${organizationId}/topics/${topicId}`),
  createTopicKeyword: (organizationId: number, topicId: number, keyword: string) =>
    apiClient.post<{ id: number; keyword: string }>(
      `/admin/organizations/${organizationId}/topics/${topicId}/keywords`,
      { keyword },
    ),
  deleteTopicKeyword: (organizationId: number, topicId: number, keywordId: number) =>
    apiClient.delete<void>(`/admin/organizations/${organizationId}/topics/${topicId}/keywords/${keywordId}`),
  importTopics: (organizationId: number, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient.postForm<TopicImportResult>(`/admin/organizations/${organizationId}/topics/import`, formData)
  },
}
