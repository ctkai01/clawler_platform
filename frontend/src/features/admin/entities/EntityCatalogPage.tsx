import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, Trash2 } from 'lucide-react'
import { adminApi } from '@/features/admin/adminApi'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Banner } from '@/components/ui/banner'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Pagination } from '@/components/ui/pagination'
import { PageHeader } from '@/components/PageHeader'
import { ApiError } from '@/lib/apiClient'

const PAGE_SIZE = 50
const ALL_INDUSTRIES = '__all__'

export function EntityCatalogPage() {
  const queryClient = useQueryClient()
  const { data: entities, isLoading } = useQuery({ queryKey: ['admin', 'entities'], queryFn: adminApi.listEntities })

  const [search, setSearch] = useState('')
  const [industryFilter, setIndustryFilter] = useState(ALL_INDUSTRIES)
  const [page, setPage] = useState(1)
  const [canonicalName, setCanonicalName] = useState('')
  const [conceptId, setConceptId] = useState('')
  const [surfaceForm, setSurfaceForm] = useState('')
  const [industryCode, setIndustryCode] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['admin', 'entities'] })

  const createMutation = useMutation({
    mutationFn: () =>
      adminApi.createEntity({
        canonical_name: canonicalName,
        concept_id: conceptId,
        surface_form: surfaceForm,
        industry_code: industryCode || undefined,
      }),
    onSuccess: () => {
      setCanonicalName('')
      setConceptId('')
      setSurfaceForm('')
      setIndustryCode('')
      setFormError(null)
      invalidate()
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : 'Tạo entity thất bại'),
  })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ canonical_name, is_active }: { canonical_name: string; is_active: boolean }) =>
      adminApi.updateEntity(canonical_name, { is_active }),
    onSuccess: invalidate,
  })

  const deleteMutation = useMutation({
    mutationFn: (canonical_name: string) => adminApi.deleteEntity(canonical_name),
    onSuccess: invalidate,
  })

  const industries = useMemo(() => {
    const set = new Set((entities ?? []).map((e) => e.industry_code).filter((v): v is string => Boolean(v)))
    return Array.from(set).sort()
  }, [entities])

  const matched = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (entities ?? []).filter((e) => {
      if (industryFilter !== ALL_INDUSTRIES && e.industry_code !== industryFilter) return false
      if (q && !e.canonical_name.toLowerCase().includes(q)) return false
      return true
    })
  }, [entities, search, industryFilter])

  const pageCount = Math.max(1, Math.ceil(matched.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visible = matched.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Danh mục Entity"
        description={`${entities?.length.toLocaleString('vi-VN') ?? '…'} entity trong entity_gazetteer (theo canonical_name).`}
      />

      <Card>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            createMutation.mutate()
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="canonical_name">Tên thương hiệu</Label>
            <Input id="canonical_name" value={canonicalName} onChange={(e) => setCanonicalName(e.target.value)} placeholder="VD: MobiFone" required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="concept_id">Concept ID</Label>
            <Input id="concept_id" value={conceptId} onChange={(e) => setConceptId(e.target.value)} placeholder="mobifone" required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="surface_form">Surface form</Label>
            <Input id="surface_form" value={surfaceForm} onChange={(e) => setSurfaceForm(e.target.value)} placeholder="mobifone" required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="industry_code">Industry code</Label>
            <Input id="industry_code" value={industryCode} onChange={(e) => setIndustryCode(e.target.value)} placeholder="TELECOM" />
          </div>
          <Button type="submit" disabled={createMutation.isPending}>
            + Thêm entity
          </Button>
        </form>
        {formError && (
          <div className="mt-3">
            <Banner tone="error">{formError}</Banner>
          </div>
        )}
        <p className="mt-3 text-xs text-muted">
          Mỗi entity có thể có nhiều <strong>surface form</strong> — tức các cách viết/biến thể mà pipeline dùng để nhận
          diện entity đó trong nội dung crawl được (VD "mobifone", "mobi fone" đều là surface form của MobiFone). Gọi lại
          form này với cùng tên thương hiệu và concept ID/surface form khác để thêm cách viết mới.
        </p>
      </Card>

      <Card className="mt-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-64 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <Input
              className="pl-9"
              placeholder="Tìm theo tên thương hiệu…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
          </div>
          <select
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
            value={industryFilter}
            onChange={(e) => {
              setIndustryFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value={ALL_INDUSTRIES}>Tất cả industry</option>
            {industries.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted">{matched.length.toLocaleString('vi-VN')} kết quả</span>
        </div>
      </Card>

      <Card className="mt-4 overflow-hidden p-0">
        {isLoading ? (
          <p className="p-5 text-sm text-muted">Đang tải…</p>
        ) : visible.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th className="px-5 py-3 font-semibold">Tên</th>
                  <th className="px-5 py-3 font-semibold" title="Số cách viết/biến thể pipeline dùng để nhận diện entity này">
                    Surface forms
                  </th>
                  <th className="px-5 py-3 font-semibold">Industry</th>
                  <th className="px-5 py-3 font-semibold">Đang bật</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((e) => (
                  <tr key={e.canonical_name} className="border-b border-line transition-colors last:border-0 hover:bg-paper/60">
                    <td className="px-5 py-3 font-medium text-ink">{e.canonical_name}</td>
                    <td className="tabular px-5 py-3 text-muted">{e.surface_form_count}</td>
                    <td className="px-5 py-3">
                      {e.industry_code ? <Badge tone="accent">{e.industry_code}</Badge> : <span className="text-muted">—</span>}
                    </td>
                    <td className="px-5 py-3">
                      <Switch
                        checked={e.is_active}
                        onChange={(checked) => toggleActiveMutation.mutate({ canonical_name: e.canonical_name, is_active: checked })}
                      />
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Button
                        variant="danger"
                        size="sm"
                        aria-label={`Xoá ${e.canonical_name}`}
                        onClick={() => deleteMutation.mutate(e.canonical_name)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="p-5 text-sm text-muted">Không có entity nào khớp.</p>
        )}
        <Pagination page={currentPage} pageCount={pageCount} onPageChange={setPage} />
      </Card>
    </div>
  )
}
