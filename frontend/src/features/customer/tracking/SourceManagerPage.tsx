import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Download, Pencil, Search, Trash2, Upload, X } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { useAuthStore } from '@/store/authStore'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Banner } from '@/components/ui/banner'
import { Badge } from '@/components/ui/badge'
import { Pagination } from '@/components/ui/pagination'
import { useToast } from '@/components/ui/toast'
import { PageHeader } from '@/components/PageHeader'
import { PLATFORM_LABEL, SOURCE_STATUS_DESCRIPTION, SOURCE_STATUS_LABEL, sourceStatusTone } from '@/lib/platform'
import { ApiError } from '@/lib/apiClient'
import type { SourceImportResult } from '@/types/org'

const PLATFORM_TYPES = ['facebook_group', 'facebook_page', 'forum', 'news']
const ALL_PLATFORMS = '__all__'
const PAGE_SIZE = 10

const CSV_TEMPLATE = `platform_type,url,display_name
facebook_group,https://facebook.com/groups/vi-du,Ví dụ FB Group
facebook_page,https://facebook.com/vi-du,Ví dụ FB Page
forum,https://forum.vi-du.com/board,Ví dụ Forum
news,https://vi-du.vn,Ví dụ News
`

function downloadCsvTemplate() {
  const blob = new Blob([CSV_TEMPLATE], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'nguon-crawl-mau.csv'
  a.click()
  URL.revokeObjectURL(url)
}

export function SourceManagerPage() {
  const user = useAuthStore((s) => s.user)
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { data: sources, isLoading } = useQuery({ queryKey: ['org', 'sources'], queryFn: orgApi.listSources })
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [platformFilter, setPlatformFilter] = useState(ALL_PLATFORMS)
  const [platformType, setPlatformType] = useState(PLATFORM_TYPES[0])
  const [url, setUrl] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<SourceImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['org', 'sources'] })

  const createMutation = useMutation({
    mutationFn: () => orgApi.createSource({ platform_type: platformType, url, display_name: displayName || undefined }),
    onSuccess: () => {
      setUrl('')
      setDisplayName('')
      setFormError(null)
      invalidate()
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : 'Thêm nguồn crawl thất bại'),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => orgApi.deleteSource(id),
    onSuccess: invalidate,
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Xoá nguồn crawl thất bại', 'error'),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, displayName }: { id: number; displayName: string }) => orgApi.updateSource(id, displayName),
    onSuccess: () => {
      setEditingId(null)
      invalidate()
    },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Sửa tên nguồn crawl thất bại', 'error'),
  })

  const startEdit = (id: number, currentName: string | null) => {
    setEditingId(id)
    setEditValue(currentName ?? '')
  }
  const cancelEdit = () => setEditingId(null)
  const saveEdit = (id: number) => {
    const trimmed = editValue.trim()
    if (!trimmed) return
    updateMutation.mutate({ id, displayName: trimmed })
  }

  const importMutation = useMutation({
    mutationFn: (file: File) => orgApi.importSources(file),
    onSuccess: (result) => {
      setImportResult(result)
      setImportError(null)
      invalidate()
    },
    onError: (err) => {
      setImportError(err instanceof ApiError ? err.message : 'Import CSV thất bại')
      setImportResult(null)
    },
  })

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) importMutation.mutate(file)
    e.target.value = '' // allow re-selecting the same file later
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return (sources ?? []).filter((s) => {
      if (platformFilter !== ALL_PLATFORMS && s.platform_type !== platformFilter) return false
      if (q && !(s.display_name?.toLowerCase().includes(q) || s.url.toLowerCase().includes(q))) return false
      return true
    })
  }, [sources, search, platformFilter])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Nguồn crawl"
        description={
          user?.role === 'org_sub'
            ? 'Chỉ hiển thị các nguồn bạn được cấp quyền.'
            : `${sources?.length ?? 0} nguồn đang theo dõi`
        }
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
            <Label htmlFor="platform_type">Nền tảng</Label>
            <select
              id="platform_type"
              className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
              value={platformType}
              onChange={(e) => setPlatformType(e.target.value)}
            >
              {PLATFORM_TYPES.map((p) => (
                <option key={p} value={p}>
                  {PLATFORM_LABEL[p]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex min-w-52 flex-1 flex-col gap-1.5">
            <Label htmlFor="url">URL</Label>
            <Input id="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="display_name">Tên hiển thị</Label>
            <Input
              id="display_name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Tuỳ chọn"
            />
          </div>
          <Button type="submit" disabled={createMutation.isPending}>
            + Thêm nguồn
          </Button>
        </form>
        {formError && (
          <div className="mt-3">
            <Banner tone="error">{formError}</Banner>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">Hoặc nhập hàng loạt</span>
          <input ref={fileInputRef} type="file" accept=".csv" className="hidden" onChange={handleFileSelected} />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={importMutation.isPending}
            onClick={() => fileInputRef.current?.click()}
          >
            <Upload className="h-3.5 w-3.5" />
            {importMutation.isPending ? 'Đang import…' : 'Import CSV'}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={downloadCsvTemplate}>
            <Download className="h-3.5 w-3.5" />
            Tải file mẫu
          </Button>
        </div>

        {importError && (
          <div className="mt-3">
            <Banner tone="error">{importError}</Banner>
          </div>
        )}
        {importResult && (
          <div className="mt-3 rounded-md border border-line bg-paper p-3 text-sm">
            <div className="flex flex-wrap gap-3">
              <span>
                Đã đọc <strong className="tabular">{importResult.total_rows}</strong> dòng
              </span>
              <span className="text-good">
                Thêm mới <strong className="tabular">{importResult.inserted}</strong>
              </span>
              {importResult.skipped > 0 && (
                <span className="text-muted">
                  Bỏ qua <strong className="tabular">{importResult.skipped}</strong>
                </span>
              )}
            </div>
            {importResult.errors.length > 0 && (
              <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-muted">
                {importResult.errors.map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <p className="mt-3 text-xs text-muted">
          File CSV cần cột <code className="rounded bg-paper px-1 py-0.5">platform_type</code> (facebook_group /
          facebook_page / forum / news) và <code className="rounded bg-paper px-1 py-0.5">url</code>, cột{' '}
          <code className="rounded bg-paper px-1 py-0.5">display_name</code> tuỳ chọn.
        </p>
      </Card>

      <Card className="mt-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-64 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
            <Input
              className="pl-9"
              placeholder="Tìm theo tên hoặc URL…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
            />
          </div>
          <select
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
            value={platformFilter}
            onChange={(e) => {
              setPlatformFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value={ALL_PLATFORMS}>Tất cả nền tảng</option>
            {PLATFORM_TYPES.map((p) => (
              <option key={p} value={p}>
                {PLATFORM_LABEL[p]}
              </option>
            ))}
          </select>
          <span className="text-xs text-muted">{filtered.length.toLocaleString('vi-VN')} kết quả</span>
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
                  <th className="px-5 py-3 font-semibold">Nền tảng</th>
                  <th className="px-5 py-3 font-semibold">URL</th>
                  <th className="px-5 py-3 font-semibold">Trạng thái</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((s) => (
                  <tr key={s.id} className="border-b border-line transition-colors last:border-0 hover:bg-paper/60">
                    <td className="px-5 py-3 font-medium text-ink">
                      {editingId === s.id ? (
                        <Input
                          autoFocus
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') saveEdit(s.id)
                            if (e.key === 'Escape') cancelEdit()
                          }}
                          className="h-8 text-sm"
                        />
                      ) : (
                        s.display_name ?? '—'
                      )}
                    </td>
                    <td className="px-5 py-3">
                      <Badge tone="neutral">{PLATFORM_LABEL[s.platform_type] ?? s.platform_type}</Badge>
                    </td>
                    <td className="max-w-56 truncate px-5 py-3" title={s.url}>
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent-ink hover:underline"
                      >
                        {s.url}
                      </a>
                    </td>
                    <td className="px-5 py-3">
                      <Badge
                        tone={sourceStatusTone(s.last_status)}
                        dot
                        title={SOURCE_STATUS_DESCRIPTION[s.last_status ?? 'chua_crawl']}
                      >
                        {s.last_status ? (SOURCE_STATUS_LABEL[s.last_status] ?? s.last_status) : 'chưa crawl'}
                      </Badge>
                    </td>
                    <td className="px-5 py-3 text-right">
                      {editingId === s.id ? (
                        <div className="flex justify-end gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            aria-label="Lưu"
                            disabled={updateMutation.isPending}
                            onClick={() => saveEdit(s.id)}
                          >
                            <Check className="h-3.5 w-3.5" />
                          </Button>
                          <Button variant="outline" size="sm" aria-label="Huỷ" onClick={cancelEdit}>
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      ) : (
                        <div className="flex justify-end gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            aria-label={`Sửa ${s.display_name ?? s.url}`}
                            onClick={() => startEdit(s.id, s.display_name)}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            aria-label={`Xoá ${s.display_name ?? s.url}`}
                            disabled={deleteMutation.isPending && deleteMutation.variables === s.id}
                            onClick={() => deleteMutation.mutate(s.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="p-5 text-sm text-muted">
            {sources && sources.length > 0 ? 'Không có nguồn nào khớp.' : 'Chưa có nguồn crawl nào.'}
          </p>
        )}
        <Pagination page={currentPage} pageCount={pageCount} onPageChange={setPage} />
      </Card>
    </div>
  )
}
