import { apiClient } from '@/lib/apiClient'
import type { EntityGazetteerItem, KeywordCatalogItem } from '@/types/catalog'

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
}
