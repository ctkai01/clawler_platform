import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Pagination } from '@/components/ui/pagination'
import { PageHeader } from '@/components/PageHeader'
import { cn } from '@/lib/utils'
import type { OrgEntitySelection, OrgKeywordSelection } from '@/types/org'

const ALL_INDUSTRIES = '__all__'
const TRACKED_PAGE_SIZE = 20
const BROWSE_PAGE_SIZE = 20

// No bulk endpoint server-side, so "select all" fires one request per item.
// Chunked (not one big Promise.all) so selecting hundreds of entities
// doesn't fire hundreds of requests simultaneously.
async function runChunked<T>(items: T[], run: (item: T) => Promise<unknown>, chunkSize = 15): Promise<void> {
  for (let i = 0; i < items.length; i += chunkSize) {
    await Promise.all(items.slice(i, i + chunkSize).map(run))
  }
}

export function EntityKeywordPicker() {
  const queryClient = useQueryClient()
  const [entitySearch, setEntitySearch] = useState('')
  const [industryFilter, setIndustryFilter] = useState(ALL_INDUSTRIES)
  const [trackedSearch, setTrackedSearch] = useState('')
  const [trackedPage, setTrackedPage] = useState(1)
  const [browsePage, setBrowsePage] = useState(1)
  const [keywordSearch, setKeywordSearch] = useState('')

  const { data: entities, isLoading: loadingEntities } = useQuery({
    queryKey: ['org', 'entities'],
    queryFn: orgApi.listEntities,
  })
  const { data: keywords, isLoading: loadingKeywords } = useQuery({
    queryKey: ['org', 'keywords'],
    queryFn: orgApi.listKeywords,
  })

  const toggleEntity = useMutation({
    mutationFn: ({ name, selected }: { name: string; selected: boolean }) =>
      selected ? orgApi.deselectEntity(name) : orgApi.selectEntity(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org', 'entities'] }),
  })

  const toggleKeyword = useMutation({
    mutationFn: ({ id, selected }: { id: number; selected: boolean }) =>
      selected ? orgApi.deselectKeyword(id) : orgApi.selectKeyword(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org', 'keywords'] }),
  })

  // Used for "chọn tất cả" on whatever set is on screen right now (current
  // page of browse results) — bounded, so this one stays a flat Promise.all.
  const bulkToggleEntities = useMutation({
    mutationFn: async ({ items, select }: { items: OrgEntitySelection[]; select: boolean }) => {
      await Promise.all(
        items.map((e) => (select ? orgApi.selectEntity(e.canonical_name) : orgApi.deselectEntity(e.canonical_name))),
      )
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org', 'entities'] }),
  })

  // Used for "chọn tất cả toàn bộ" — every result matching the current
  // search/industry filter, across all pages (can be hundreds), hence chunked.
  const bulkToggleAllMatched = useMutation({
    mutationFn: async ({ items, select }: { items: OrgEntitySelection[]; select: boolean }) => {
      await runChunked(items, (e) => (select ? orgApi.selectEntity(e.canonical_name) : orgApi.deselectEntity(e.canonical_name)))
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org', 'entities'] }),
  })

  const bulkToggleKeywords = useMutation({
    mutationFn: async ({ items, select }: { items: OrgKeywordSelection[]; select: boolean }) => {
      await Promise.all(
        items.map((k) => (select ? orgApi.selectKeyword(k.keyword_id) : orgApi.deselectKeyword(k.keyword_id))),
      )
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['org', 'keywords'] }),
  })

  const industries = useMemo(() => {
    const set = new Set((entities ?? []).map((e) => e.industry_code).filter((v): v is string => Boolean(v)))
    return Array.from(set).sort()
  }, [entities])

  const selectedEntities = useMemo(() => entities?.filter((e) => e.is_selected) ?? [], [entities])
  const filteredTrackedEntities = useMemo(() => {
    const q = trackedSearch.trim().toLowerCase()
    if (!q) return selectedEntities
    return selectedEntities.filter((e) => e.canonical_name.toLowerCase().includes(q))
  }, [selectedEntities, trackedSearch])
  const trackedPageCount = Math.max(1, Math.ceil(filteredTrackedEntities.length / TRACKED_PAGE_SIZE))
  const trackedCurrentPage = Math.min(trackedPage, trackedPageCount)
  const visibleTrackedEntities = filteredTrackedEntities.slice(
    (trackedCurrentPage - 1) * TRACKED_PAGE_SIZE,
    trackedCurrentPage * TRACKED_PAGE_SIZE,
  )

  const browsing = entitySearch.trim().length > 0 || industryFilter !== ALL_INDUSTRIES
  const matched = useMemo(() => {
    if (!entities) return []
    const q = entitySearch.trim().toLowerCase()
    return entities.filter((e) => {
      if (industryFilter !== ALL_INDUSTRIES && e.industry_code !== industryFilter) return false
      if (q && !e.canonical_name.toLowerCase().includes(q)) return false
      return true
    })
  }, [entities, entitySearch, industryFilter])
  const browsePageCount = Math.max(1, Math.ceil(matched.length / BROWSE_PAGE_SIZE))
  const browseCurrentPage = Math.min(browsePage, browsePageCount)
  const browseResults = matched.slice((browseCurrentPage - 1) * BROWSE_PAGE_SIZE, browseCurrentPage * BROWSE_PAGE_SIZE)
  const allBrowseResultsSelected = browseResults.length > 0 && browseResults.every((e) => e.is_selected)
  const allMatchedSelected = matched.length > 0 && matched.every((e) => e.is_selected)
  const filteredKeywords = useMemo(() => {
    const q = keywordSearch.trim().toLowerCase()
    if (!q) return keywords ?? []
    return (keywords ?? []).filter((k) => k.term.toLowerCase().includes(q))
  }, [keywords, keywordSearch])
  const allKeywordsSelected = filteredKeywords.length > 0 && filteredKeywords.every((k) => k.is_selected)

  const EntityPill = ({ name, industryCode, selected }: { name: string; industryCode: string | null; selected: boolean }) => (
    <button
      type="button"
      onClick={() => toggleEntity.mutate({ name, selected })}
      className={cn(
        'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
        selected
          ? 'border-accent-ink bg-accent-ink text-white'
          : 'border-line bg-surface text-muted hover:border-accent-ink hover:text-accent-ink',
      )}
    >
      {name}
      {industryCode && <span className="ml-1.5 text-[10px] opacity-70">{industryCode}</span>}
    </button>
  )

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Entity / Keyword theo dõi"
        description={`Chọn từ ${entities?.length.toLocaleString('vi-VN') ?? '…'} entity trong entity_gazetteer.`}
      />

      <Card className="p-0">
        <div className="p-6 pb-0">
          <div className="flex items-center justify-between">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Entity đang theo dõi</div>
            {selectedEntities.length > 0 && (
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted">
                  {selectedEntities.length.toLocaleString('vi-VN')} entity
                  {bulkToggleAllMatched.isPending && ' · đang xoá…'}
                </span>
                <button
                  type="button"
                  disabled={bulkToggleAllMatched.isPending}
                  onClick={() => bulkToggleAllMatched.mutate({ items: selectedEntities, select: false })}
                  className="text-xs font-medium text-bad hover:underline disabled:opacity-50"
                >
                  Reset
                </button>
              </div>
            )}
          </div>
          {selectedEntities.length > 0 && (
            <div className="relative mt-3 max-w-sm">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
              <Input
                className="pl-9"
                placeholder="Tìm trong entity đang theo dõi…"
                value={trackedSearch}
                onChange={(e) => {
                  setTrackedSearch(e.target.value)
                  setTrackedPage(1)
                }}
              />
            </div>
          )}
          {loadingEntities ? (
            <p className="mt-2 text-sm text-muted">Đang tải…</p>
          ) : (
            <div className="mt-3 flex flex-wrap gap-2">
              {visibleTrackedEntities.length > 0 ? (
                visibleTrackedEntities.map((e) => (
                  <EntityPill key={e.canonical_name} name={e.canonical_name} industryCode={e.industry_code} selected />
                ))
              ) : selectedEntities.length > 0 ? (
                <p className="text-sm text-muted">Không có entity đang theo dõi nào khớp tìm kiếm.</p>
              ) : (
                <p className="text-sm text-muted">Chưa chọn entity nào — tìm hoặc lọc theo ngành bên dưới để thêm.</p>
              )}
            </div>
          )}
        </div>
        <Pagination page={trackedCurrentPage} pageCount={trackedPageCount} onPageChange={setTrackedPage} />

        <div className="flex flex-wrap items-center gap-3 border-t border-line p-6">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <Input
              className="pl-9"
              placeholder="Tìm entity (VD: MobiFone, Viettel…)"
              value={entitySearch}
              onChange={(e) => {
                setEntitySearch(e.target.value)
                setBrowsePage(1)
              }}
            />
          </div>
          <select
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
            value={industryFilter}
            onChange={(e) => {
              setIndustryFilter(e.target.value)
              setBrowsePage(1)
            }}
          >
            <option value={ALL_INDUSTRIES}>Tất cả ngành</option>
            {industries.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </div>

        {browsing && (
          <div className="border-t border-line pt-3">
            {browseResults.length > 0 ? (
              <>
                <div className="mb-2 flex items-center justify-between px-6">
                  <span className="text-xs text-muted">
                    {matched.length.toLocaleString('vi-VN')} kết quả
                    {bulkToggleAllMatched.isPending && ' · đang chọn…'}
                  </span>
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      disabled={bulkToggleEntities.isPending || bulkToggleAllMatched.isPending}
                      onClick={() => bulkToggleEntities.mutate({ items: browseResults, select: !allBrowseResultsSelected })}
                      className="text-xs font-medium text-accent-ink hover:underline disabled:opacity-50"
                    >
                      {allBrowseResultsSelected ? 'Bỏ chọn (trang này)' : `Chọn trang này (${browseResults.length})`}
                    </button>
                    {browsePageCount > 1 && (
                      <button
                        type="button"
                        disabled={bulkToggleEntities.isPending || bulkToggleAllMatched.isPending}
                        onClick={() => bulkToggleAllMatched.mutate({ items: matched, select: !allMatchedSelected })}
                        className="text-xs font-medium text-accent-ink hover:underline disabled:opacity-50"
                      >
                        {allMatchedSelected ? 'Bỏ chọn toàn bộ' : `Chọn tất cả toàn bộ (${matched.length.toLocaleString('vi-VN')})`}
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 px-6 pb-6">
                  {browseResults.map((e) => (
                    <EntityPill key={e.canonical_name} name={e.canonical_name} industryCode={e.industry_code} selected={e.is_selected} />
                  ))}
                </div>
                <Pagination page={browseCurrentPage} pageCount={browsePageCount} onPageChange={setBrowsePage} />
              </>
            ) : (
              <p className="px-6 pb-6 text-sm text-muted">Không có entity nào khớp.</p>
            )}
          </div>
        )}
      </Card>

      <Card className="mt-4">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold uppercase tracking-wide text-muted">Keyword</div>
          {filteredKeywords.length > 0 && (
            <button
              type="button"
              disabled={bulkToggleKeywords.isPending}
              onClick={() => bulkToggleKeywords.mutate({ items: filteredKeywords, select: !allKeywordsSelected })}
              className="text-xs font-medium text-accent-ink hover:underline disabled:opacity-50"
            >
              {allKeywordsSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả'}
            </button>
          )}
        </div>
        {keywords && keywords.length > 0 && (
          <div className="relative mt-3 max-w-sm">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <Input
              className="pl-9"
              placeholder="Tìm keyword…"
              value={keywordSearch}
              onChange={(e) => setKeywordSearch(e.target.value)}
            />
          </div>
        )}
        {loadingKeywords ? (
          <p className="mt-2 text-sm text-muted">Đang tải…</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {filteredKeywords.map((k) => (
              <button
                key={k.keyword_id}
                type="button"
                onClick={() => toggleKeyword.mutate({ id: k.keyword_id, selected: k.is_selected })}
                className={cn(
                  'rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors',
                  k.is_selected
                    ? 'border-accent-ink bg-accent-ink text-white'
                    : 'border-line bg-surface text-muted hover:border-accent-ink hover:text-accent-ink',
                )}
              >
                {k.term}
                <span className="ml-1.5 text-[10px] opacity-70">{k.category}</span>
              </button>
            ))}
            {keywords?.length === 0 && <p className="text-sm text-muted">Chưa có keyword nào trong danh mục.</p>}
            {keywords && keywords.length > 0 && filteredKeywords.length === 0 && (
              <p className="text-sm text-muted">Không có keyword nào khớp tìm kiếm.</p>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}
