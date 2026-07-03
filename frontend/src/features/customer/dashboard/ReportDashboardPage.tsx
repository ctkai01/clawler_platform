import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { orgApi } from '@/features/customer/orgApi'
import { useAuthStore } from '@/store/authStore'
import { Card } from '@/components/ui/card'
import { PageHeader } from '@/components/PageHeader'

const DAY_OPTIONS = [7, 14, 30, 90, 365]

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-l-2 border-line pl-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className="tabular mt-1 text-3xl font-medium text-ink">{value.toLocaleString('vi-VN')}</div>
    </div>
  )
}

export function ReportDashboardPage() {
  const user = useAuthStore((s) => s.user)
  const [days, setDays] = useState(7)
  const { data, isLoading } = useQuery({
    queryKey: ['org', 'report', days],
    queryFn: () => orgApi.getReport(days),
  })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={`Tổng quan — ${user?.organization_name ?? ''}`}
        action={
          <select
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
          >
            {DAY_OPTIONS.map((d) => (
              <option key={d} value={d}>
                {d} ngày gần nhất
              </option>
            ))}
          </select>
        }
      />

      {isLoading || !data ? (
        <Card>
          <p className="text-sm text-muted">Đang tải…</p>
        </Card>
      ) : (
        <>
          <Card>
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              <Kpi label="Tổng số tin" value={data.total_posts} />
              <Kpi label="Bình luận" value={data.total_comments} />
              <Kpi label="Quan tâm" value={data.total_reactions} />
              <Kpi label="Chia sẻ" value={data.total_shares} />
            </div>
          </Card>

          <Card className="mt-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted">Phân bố sắc thái</div>
            <div className="mt-3 flex h-2.5 gap-0.5 overflow-hidden rounded-full bg-paper">
              {(() => {
                const total = data.sentiment_positive + data.sentiment_negative + data.sentiment_neutral || 1
                const seg = [
                  { n: data.sentiment_positive, cls: 'bg-good' },
                  { n: data.sentiment_neutral, cls: 'bg-faint' },
                  { n: data.sentiment_negative, cls: 'bg-bad' },
                ]
                return seg.map((s, i) => (
                  <div key={i} className={`h-full ${s.cls}`} style={{ width: `${(s.n / total) * 100}%` }} />
                ))
              })()}
            </div>
            <div className="mt-3 flex gap-5 text-xs text-muted">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-good" /> Tích cực · <span className="tabular">{data.sentiment_positive}</span>
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-faint" /> Trung tính · <span className="tabular">{data.sentiment_neutral}</span>
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-bad" /> Tiêu cực · <span className="tabular">{data.sentiment_negative}</span>
              </span>
            </div>
          </Card>

          {user?.role === 'org_sub' && (
            <p className="mt-3 text-xs text-muted">Số liệu chỉ tính trên các nguồn crawl bạn được cấp quyền xem.</p>
          )}
        </>
      )}
    </div>
  )
}
