import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Pagination } from '@/components/ui/pagination'
import { Switch } from '@/components/ui/switch'
import { PLATFORM_LABEL, SENTIMENT_LABEL, sentimentTone } from '@/lib/platform'
import { EngagementGrowthChart } from '@/features/customer/documents/EngagementGrowthChart'
import type { AccordionFilterParams, AccordionSentimentKey } from '@/types/org'

// Plotly (network graph) drags in a multi-MB WebGL bundle — lazy-load it so
// the page's initial JS stays small; only paid for once a user actually
// opens "Summary" on a section.
const EntityNetworkGraph = lazy(() =>
  import('@/features/customer/documents/EntityNetworkGraph').then((m) => ({ default: m.EntityNetworkGraph })),
)

const PER_PAGE = 10

const SENTIMENT_TABS: { key: AccordionSentimentKey | 'all'; label: string }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'positive', label: 'Tích cực' },
  { key: 'negative', label: 'Tiêu cực' },
  { key: 'neutral', label: 'Trung tính' },
  { key: 'unclassified', label: 'Chưa phân loại' },
  { key: 'competitor', label: 'Đối thủ' },
]

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' })
}

export function CategorySection({
  platformType,
  count,
  filters,
  selectedId,
  onSelect,
}: {
  platformType: string
  count: number
  filters: AccordionFilterParams
  selectedId: number | null
  onSelect: (id: number) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [tab, setTab] = useState<(typeof SENTIMENT_TABS)[number]['key']>('all')
  const [page, setPage] = useState(1)

  const { data: sentimentCounts } = useQuery({
    queryKey: ['org', 'documents', 'accordion', 'sentiment-counts', platformType, filters],
    queryFn: () => orgApi.getAccordionSentimentCounts(platformType, filters),
    enabled: expanded,
  })

  const { data: growth } = useQuery({
    queryKey: ['org', 'documents', 'accordion', 'growth', platformType, filters],
    queryFn: () => orgApi.getAccordionGrowth(platformType, filters),
    enabled: expanded && summaryOpen,
  })

  const { data: network } = useQuery({
    queryKey: ['org', 'documents', 'accordion', 'network', platformType, filters],
    queryFn: () => orgApi.getAccordionNetwork(platformType, filters),
    enabled: expanded && summaryOpen,
  })

  const { data, isLoading } = useQuery({
    queryKey: ['org', 'documents', 'accordion', 'list', platformType, tab, page, filters],
    queryFn: () =>
      orgApi.listDocuments({
        page,
        page_size: PER_PAGE,
        platform_type: platformType,
        sentiment: tab === 'all' ? undefined : tab,
        search: filters.search,
        entity: filters.entity,
        entity_exact: filters.entity_exact,
        days: filters.days,
        date_from: filters.date_from,
        date_to: filters.date_to,
      }),
    enabled: expanded,
  })

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PER_PAGE))

  return (
    <div className="rounded-xl border border-line bg-surface">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left"
      >
        <span className="flex items-center gap-2 font-medium text-ink">
          {expanded ? <ChevronDown className="h-4 w-4 text-faint" /> : <ChevronRight className="h-4 w-4 text-faint" />}
          {PLATFORM_LABEL[platformType] ?? platformType}
        </span>
        <Badge tone="neutral">{count}</Badge>
      </button>

      {expanded && (
        <div className="border-t border-line p-4">
          {count === 0 ? (
            <p className="text-sm text-muted">Không có bài viết nào khớp.</p>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">Summary</span>
                <Switch checked={summaryOpen} onChange={setSummaryOpen} />
              </div>
              {summaryOpen && (
                <div className="mt-3 space-y-5 border-b border-line pb-5">
                  <div>
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                      Tăng trưởng engagement (tổng các bài đã match, theo thời gian crawl)
                    </p>
                    <EngagementGrowthChart data={growth ?? []} />
                  </div>
                  {network && (
                    <Suspense fallback={<p className="text-sm text-muted">Đang tải đồ thị…</p>}>
                      <EntityNetworkGraph network={network} />
                    </Suspense>
                  )}
                </div>
              )}

              <div className="mt-4 flex flex-wrap gap-1.5 border-b border-line pb-3">
                {SENTIMENT_TABS.map((t) => (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => {
                      setTab(t.key)
                      setPage(1)
                    }}
                    className={`cursor-pointer rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      tab === t.key ? 'bg-accent-ink text-white' : 'bg-paper text-muted hover:text-ink'
                    }`}
                  >
                    {t.label} ({t.key === 'all' ? count : (sentimentCounts?.[t.key] ?? 0)})
                  </button>
                ))}
              </div>

              <div className="mt-3">
                {isLoading ? (
                  <p className="text-sm text-muted">Đang tải…</p>
                ) : items.length === 0 ? (
                  <p className="text-sm text-muted">Không có bài viết nào khớp.</p>
                ) : (
                  <ul className="space-y-2">
                    {items.map((doc) => (
                      <li
                        key={doc.id}
                        className={`rounded-lg border p-3 transition-colors ${
                          selectedId === doc.id ? 'border-accent-ink bg-accent-soft/40' : 'border-line hover:bg-paper/60'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-medium text-ink">
                              {doc.topic || doc.content_snippet.slice(0, 100) || 'Không có tiêu đề'}
                            </p>
                            <p className="mt-0.5 text-xs text-muted">
                              {doc.target_name ?? '—'} · {formatDate(doc.published_at)}
                              {doc.classification_sentiment && (
                                <>
                                  {' · '}
                                  <Badge tone={sentimentTone(doc.classification_sentiment)}>
                                    {SENTIMENT_LABEL[doc.classification_sentiment] ?? doc.classification_sentiment}
                                  </Badge>
                                </>
                              )}
                            </p>
                          </div>
                          <Button size="sm" variant="outline" onClick={() => onSelect(doc.id)}>
                            Chi tiết →
                          </Button>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
                <Pagination page={page} pageCount={pageCount} onPageChange={setPage} />
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
