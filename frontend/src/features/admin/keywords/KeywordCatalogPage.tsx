import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { adminApi } from '@/features/admin/adminApi'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Banner } from '@/components/ui/banner'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { PageHeader } from '@/components/PageHeader'
import { ApiError } from '@/lib/apiClient'

const CATEGORIES = [
  { value: 'brand', label: 'Brand' },
  { value: 'competitor', label: 'Competitor' },
  { value: 'industry', label: 'Industry' },
  { value: 'custom', label: 'Custom' },
] as const

const CATEGORY_LABEL: Record<string, string> = Object.fromEntries(CATEGORIES.map((c) => [c.value, c.label]))

export function KeywordCatalogPage() {
  const queryClient = useQueryClient()
  const { data: keywords, isLoading } = useQuery({ queryKey: ['admin', 'keywords'], queryFn: adminApi.listKeywords })

  const [category, setCategory] = useState<string>('brand')
  const [term, setTerm] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['admin', 'keywords'] })

  const createMutation = useMutation({
    mutationFn: () => adminApi.createKeyword({ category, term }),
    onSuccess: () => {
      setTerm('')
      setFormError(null)
      invalidate()
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : 'Tạo từ khóa thất bại'),
  })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => adminApi.updateKeyword(id, { is_active }),
    onSuccess: invalidate,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminApi.deleteKeyword(id),
    onSuccess: invalidate,
  })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Danh mục Keyword" description="Từ khóa mẫu khách hàng có thể chọn theo dõi." />

      <Card>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            createMutation.mutate()
          }}
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="category">Nhóm</Label>
            <select
              id="category"
              className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="term">Từ khóa</Label>
            <Input id="term" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="VD: gói cước" required />
          </div>
          <Button type="submit" disabled={createMutation.isPending}>
            + Thêm từ khóa
          </Button>
        </form>
        {formError && (
          <div className="mt-3">
            <Banner tone="error">{formError}</Banner>
          </div>
        )}
      </Card>

      <Card className="mt-4 overflow-hidden p-0">
        {isLoading ? (
          <p className="p-5 text-sm text-muted">Đang tải…</p>
        ) : keywords && keywords.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th className="px-5 py-3 font-semibold">Nhóm</th>
                  <th className="px-5 py-3 font-semibold">Từ khóa</th>
                  <th className="px-5 py-3 font-semibold">Đang bật</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {keywords.map((k) => (
                  <tr key={k.id} className="border-b border-line transition-colors last:border-0 hover:bg-paper/60">
                    <td className="px-5 py-3">
                      <Badge tone="accent">{CATEGORY_LABEL[k.category]}</Badge>
                    </td>
                    <td className="px-5 py-3 font-medium text-ink">{k.term}</td>
                    <td className="px-5 py-3">
                      <Switch
                        checked={k.is_active}
                        onChange={(checked) => toggleActiveMutation.mutate({ id: k.id, is_active: checked })}
                      />
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Button variant="danger" size="sm" aria-label={`Xoá ${k.term}`} onClick={() => deleteMutation.mutate(k.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="p-5 text-sm text-muted">Chưa có từ khóa nào.</p>
        )}
      </Card>
    </div>
  )
}
