import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { PageHeader } from '@/components/PageHeader'

const ROLE_LABEL: Record<string, string> = {
  report_viewer: 'Xem báo cáo',
  configurator: 'Cấu hình nguồn crawl',
}

export function SubAccountListPage() {
  const queryClient = useQueryClient()
  const { data: members, isLoading } = useQuery({ queryKey: ['org', 'members'], queryFn: orgApi.listMembers })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['org', 'members'] })

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => orgApi.updateMember(id, { is_active }),
    onSuccess: invalidate,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => orgApi.deleteMember(id),
    onSuccess: invalidate,
  })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Thành viên"
        description={`${members?.length ?? 0} tài khoản con`}
        action={
          <Link to="/members/new">
            <Button size="sm">+ Tạo tài khoản con</Button>
          </Link>
        }
      />

      <Card className="overflow-hidden p-0">
        {isLoading ? (
          <p className="p-5 text-sm text-muted">Đang tải…</p>
        ) : members && members.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                  <th className="px-5 py-3 font-semibold">Email</th>
                  <th className="px-5 py-3 font-semibold">Quyền</th>
                  <th className="px-5 py-3 font-semibold">Nguồn crawl</th>
                  <th className="px-5 py-3 font-semibold">Đang bật</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {members.map((m) => (
                  <tr key={m.id} className="border-b border-line transition-colors last:border-0 hover:bg-paper/60">
                    <td className="px-5 py-3 font-medium text-ink">{m.email}</td>
                    <td className="px-5 py-3">
                      <Badge tone={m.functional_role === 'configurator' ? 'accent' : 'neutral'}>
                        {ROLE_LABEL[m.functional_role]}
                      </Badge>
                    </td>
                    <td className="tabular px-5 py-3 text-muted">{m.target_ids.length}</td>
                    <td className="px-5 py-3">
                      <Switch
                        checked={m.is_active}
                        onChange={(checked) => toggleActiveMutation.mutate({ id: m.id, is_active: checked })}
                      />
                    </td>
                    <td className="px-5 py-3 text-right">
                      <Link to={`/members/${m.id}/edit`} className="mr-4 text-sm font-medium text-accent-ink hover:underline">
                        Sửa
                      </Link>
                      <Button variant="danger" size="sm" aria-label={`Xoá ${m.email}`} onClick={() => deleteMutation.mutate(m.id)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="p-5 text-sm text-muted">Chưa có tài khoản con nào.</p>
        )}
      </Card>
    </div>
  )
}
