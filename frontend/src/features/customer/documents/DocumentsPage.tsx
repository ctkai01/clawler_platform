import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { PageHeader } from '@/components/PageHeader'
import { CategorySection } from '@/features/customer/documents/CategorySection'
import { DetailPanel } from '@/features/customer/documents/DetailPanel'
import type { AccordionFilterParams } from '@/types/org'

const CATEGORIES = ['facebook_group', 'facebook_page', 'forum', 'news']

export function DocumentsPage() {
  const [searchInput, setSearchInput] = useState('')
  const [entityInput, setEntityInput] = useState('')
  const [entityExact, setEntityExact] = useState(false)
  const [filters, setFilters] = useState<AccordionFilterParams>({})
  const [selectedId, setSelectedId] = useState<number | null>(null)

  useEffect(() => {
    const t = setTimeout(() => {
      setFilters({
        search: searchInput.trim() || undefined,
        entity: entityInput.trim() || undefined,
        entity_exact: entityExact,
      })
    }, 350)
    return () => clearTimeout(t)
  }, [searchInput, entityInput, entityExact])

  const { data: counts } = useQuery({
    queryKey: ['org', 'documents', 'accordion', 'counts', filters],
    queryFn: () => orgApi.getAccordionCounts(filters),
  })

  return (
    <div className="mx-auto max-w-7xl">
      <PageHeader
        title="Bài viết đã crawl"
        description="Duyệt bài viết theo nguồn (FB Group / FB Page / Forum / News), lọc theo từ khóa hoặc entity."
      />

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex min-w-52 flex-1 flex-col gap-1.5">
            <Label htmlFor="doc-search">Search từ khóa</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
              <Input
                id="doc-search"
                className="pl-9"
                placeholder="Tìm trong tiêu đề / nội dung…"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </div>
          </div>
          <div className="flex min-w-52 flex-1 flex-col gap-1.5">
            <Label htmlFor="doc-entity">Entity</Label>
            <Input
              id="doc-entity"
              placeholder="vd: MobiFone, Viettel…"
              value={entityInput}
              onChange={(e) => setEntityInput(e.target.value)}
            />
          </div>
          <Switch checked={entityExact} onChange={setEntityExact} label="Khớp chính xác" />
        </div>
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="space-y-3">
          {CATEGORIES.map((category) => (
            <CategorySection
              key={category}
              platformType={category}
              count={counts?.[category as keyof typeof counts] ?? 0}
              filters={filters}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          ))}
        </div>

        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-muted">Chi tiết</p>
          <DetailPanel
            documentId={selectedId}
            onSelect={setSelectedId}
            focusEntity={filters.entity}
            focusEntityExact={filters.entity_exact}
          />
        </div>
      </div>
    </div>
  )
}
