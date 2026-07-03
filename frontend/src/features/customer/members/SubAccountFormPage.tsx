import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Banner } from '@/components/ui/banner'
import { Badge } from '@/components/ui/badge'
import { PageHeader } from '@/components/PageHeader'
import { PLATFORM_LABEL } from '@/lib/platform'
import { cn } from '@/lib/utils'
import { ApiError } from '@/lib/apiClient'

const ROLES = [
  { value: 'report_viewer', label: 'Xem báo cáo', note: 'Report Viewer — chỉ xem số liệu' },
  { value: 'configurator', label: 'Cấu hình nguồn crawl', note: 'Configurator — thêm/xoá nguồn, chọn entity/keyword' },
] as const

export function SubAccountFormPage() {
  const { id } = useParams()
  const isEdit = Boolean(id)
  const memberId = id ? Number(id) : null
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: sources } = useQuery({ queryKey: ['org', 'sources'], queryFn: orgApi.listSources })
  const { data: members } = useQuery({ queryKey: ['org', 'members'], queryFn: orgApi.listMembers, enabled: isEdit })
  const existing = members?.find((m) => m.id === memberId)

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [functionalRole, setFunctionalRole] = useState<string>('report_viewer')
  const [targetIds, setTargetIds] = useState<number[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (existing) {
      setEmail(existing.email)
      setFunctionalRole(existing.functional_role)
      setTargetIds(existing.target_ids)
    }
  }, [existing])

  const toggleTarget = (targetId: number) => {
    setTargetIds((prev) => (prev.includes(targetId) ? prev.filter((t) => t !== targetId) : [...prev, targetId]))
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      isEdit && memberId
        ? orgApi.updateMember(memberId, { functional_role: functionalRole, target_ids: targetIds })
        : orgApi.createMember({ email, password, functional_role: functionalRole, target_ids: targetIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['org', 'members'] })
      navigate('/members')
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : 'Lưu tài khoản con thất bại'),
  })

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title={isEdit ? 'Sửa tài khoản con' : 'Tạo tài khoản con'} />

      <Card>
        <form
          className="flex flex-col gap-5"
          onSubmit={(e) => {
            e.preventDefault()
            saveMutation.mutate()
          }}
        >
          {error && <Banner tone="error">{error}</Banner>}

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" value={email} disabled={isEdit} onChange={(e) => setEmail(e.target.value)} required />
          </div>

          {!isEdit && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="password">Mật khẩu</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <Label>Vai trò chức năng</Label>
            <div className="flex flex-col gap-2">
              {ROLES.map((r) => (
                <button
                  key={r.value}
                  type="button"
                  onClick={() => setFunctionalRole(r.value)}
                  className={cn(
                    'rounded-lg border px-3.5 py-2.5 text-left transition-colors',
                    functionalRole === r.value ? 'border-accent-ink bg-accent-soft' : 'border-line bg-surface hover:border-accent/50',
                  )}
                >
                  <div className={cn('text-sm font-semibold', functionalRole === r.value ? 'text-accent-ink' : 'text-ink')}>
                    {r.label}
                  </div>
                  <div className="mt-0.5 text-xs text-muted">{r.note}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label>Nguồn crawl được phép truy cập</Label>
            <div className="max-h-56 overflow-y-auto rounded-md border border-line">
              {sources && sources.length > 0 ? (
                sources.map((s) => (
                  <label
                    key={s.id}
                    className="flex cursor-pointer items-center gap-3 border-b border-line px-3.5 py-2.5 text-sm transition-colors last:border-0 hover:bg-paper/60"
                  >
                    <input
                      type="checkbox"
                      className="accent-accent-ink"
                      checked={targetIds.includes(s.id)}
                      onChange={() => toggleTarget(s.id)}
                    />
                    <span className="font-medium text-ink">{s.display_name ?? s.url}</span>
                    <Badge tone="neutral" className="ml-auto">
                      {PLATFORM_LABEL[s.platform_type] ?? s.platform_type}
                    </Badge>
                  </label>
                ))
              ) : (
                <p className="p-3.5 text-sm text-muted">Chưa có nguồn crawl nào — thêm ở trang "Nguồn crawl" trước.</p>
              )}
            </div>
          </div>

          <Button type="submit" disabled={saveMutation.isPending} className="mt-1">
            {saveMutation.isPending ? 'Đang lưu…' : 'Lưu'}
          </Button>
        </form>
      </Card>
    </div>
  )
}
