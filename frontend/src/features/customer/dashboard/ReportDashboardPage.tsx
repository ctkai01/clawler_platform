import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Download, ExternalLink, FileSearch, Search } from 'lucide-react'
import { Bar, BarChart, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { orgApi } from '@/features/customer/orgApi'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Pagination } from '@/components/ui/pagination'
import { PageHeader } from '@/components/PageHeader'

const DAY_OPTIONS = [1, 7, 14, 30, 90, 365]
const SENTIMENT_COLORS = { positive: '#1f8a5f', neutral: '#8990a0', negative: '#c0392b' }

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="border-l-2 border-line pl-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted">{label}</div>
      <div className="tabular mt-1 text-3xl font-medium text-ink">{value.toLocaleString('vi-VN')}</div>
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mt-6 mb-2 font-display text-base font-semibold text-ink">{children}</h2>
}

export function ReportDashboardPage() {
  const user = useAuthStore((s) => s.user)
  const [days, setDays] = useState(7)
  const [entityInput, setEntityInput] = useState('')
  const [entity, setEntity] = useState('')
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    const t = setTimeout(() => setEntity(entityInput.trim()), 350)
    return () => clearTimeout(t)
  }, [entityInput])

  const handleExport = async () => {
    setExporting(true)
    try {
      await orgApi.exportReport(days, entity || undefined)
    } catch {
      window.alert('Xuất Excel thất bại, vui lòng thử lại.')
    } finally {
      setExporting(false)
    }
  }

  const { data, isLoading } = useQuery({
    queryKey: ['org', 'report', days, entity],
    queryFn: () => orgApi.getReport(days, entity || undefined),
  })

  const pieData = data
    ? [
        { name: 'Tích cực', value: data.sentiment_positive, color: SENTIMENT_COLORS.positive },
        { name: 'Trung tính', value: data.sentiment_neutral, color: SENTIMENT_COLORS.neutral },
        { name: 'Tiêu cực', value: data.sentiment_negative, color: SENTIMENT_COLORS.negative },
      ]
    : []

  const topicChartData = data
    ? data.topics.map((topic, i) => ({
        topic,
        'Tiêu cực': data.topic_negative_counts[i],
        'Trung lập': data.topic_neutral_counts[i],
        'Tích cực': data.topic_positive_counts[i],
      }))
    : []

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title={`Tổng quan — ${user?.organization_name ?? ''}`}
        action={
          <Button variant="outline" onClick={handleExport} disabled={exporting || isLoading}>
            <Download className="h-4 w-4" />
            {exporting ? 'Đang xuất…' : 'Xuất Excel'}
          </Button>
        }
      />

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex min-w-52 flex-1 flex-col gap-1.5">
            <Label htmlFor="report-entity">Entity</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
              <Input
                id="report-entity"
                className="pl-9"
                placeholder="vd: MobiFone (để trống = tất cả)"
                value={entityInput}
                onChange={(e) => setEntityInput(e.target.value)}
              />
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="report-days">Số ngày</Label>
            <select
              id="report-days"
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
          </div>
        </div>
      </Card>

      {isLoading || !data ? (
        <Card className="mt-4">
          <p className="text-sm text-muted">Đang tải…</p>
        </Card>
      ) : (
        <>
          <SectionTitle>
            I. Tổng số thông tin{entity ? ` về ${entity}` : ''} trên mạng xã hội
          </SectionTitle>
          <Card>
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              <Kpi label="Tổng số tin" value={data.total_posts} />
              <Kpi label="Bình luận" value={data.total_comments} />
              <Kpi label="Tổng reaction" value={data.total_reactions} />
              <Kpi label="Chia sẻ" value={data.total_shares} />
            </div>
            <div className="mt-6 h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                    {pieData.map((seg) => (
                      <Cell key={seg.name} fill={seg.color} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <SectionTitle>II. Thông tin theo chủ đề (entity)</SectionTitle>
          <Card className="overflow-x-auto p-0">
            {data.topic_detail.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                    <th className="px-5 py-3 font-semibold">Chủ đề</th>
                    <th className="px-5 py-3 font-semibold">Bài đăng</th>
                    <th className="px-5 py-3 font-semibold">Bình luận</th>
                    <th className="px-5 py-3 font-semibold">Tổng số tương tác</th>
                  </tr>
                </thead>
                <tbody>
                  {data.topic_detail.map((row) => (
                    <tr key={row.topic} className="border-b border-line last:border-0">
                      <td className="px-5 py-3 font-medium text-ink">{row.topic}</td>
                      <td className="tabular px-5 py-3">{row.posts.toLocaleString('vi-VN')}</td>
                      <td className="tabular px-5 py-3">{row.comments.toLocaleString('vi-VN')}</td>
                      <td className="tabular px-5 py-3">{row.total_engagement.toLocaleString('vi-VN')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="p-5 text-sm text-muted">Không có dữ liệu entity trong khoảng thời gian này.</p>
            )}
          </Card>

          <SectionTitle>III. So sánh sắc thái theo chủ đề</SectionTitle>
          <Card>
            {topicChartData.length > 0 ? (
              <div style={{ height: Math.max(220, topicChartData.length * 40) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topicChartData} layout="vertical" margin={{ left: 24 }}>
                    <XAxis type="number" tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
                    <YAxis type="category" dataKey="topic" width={160} tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="Tiêu cực" stackId="s" fill={SENTIMENT_COLORS.negative} />
                    <Bar dataKey="Trung lập" stackId="s" fill={SENTIMENT_COLORS.neutral} />
                    <Bar dataKey="Tích cực" stackId="s" fill={SENTIMENT_COLORS.positive} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-sm text-muted">Không có dữ liệu.</p>
            )}
          </Card>

          <SectionTitle>IV. Thông tin tiêu cực{entity ? ` về ${entity}` : ''}</SectionTitle>
          <Card className="p-0">
            <p className="px-5 pt-5 text-sm text-muted">
              Tổng bài viết tiêu cực: <strong className="tabular text-ink">{data.negative_count}</strong> bài viết
            </p>
            <PaginatedPostTable
              sentiment="negative"
              days={days}
              entity={entity}
              emptyText="Không có bài viết tiêu cực trong khoảng thời gian này."
            />
          </Card>

          <SectionTitle>V. Thông tin tích cực{entity ? ` về ${entity}` : ''}</SectionTitle>
          <Card className="p-0">
            <p className="px-5 pt-5 text-sm text-muted">
              Tổng bài viết tích cực: <strong className="tabular text-ink">{data.positive_count}</strong> bài viết
            </p>
            <PaginatedPostTable
              sentiment="positive"
              days={days}
              entity={entity}
              emptyText="Không có bài viết tích cực trong khoảng thời gian này."
            />
          </Card>

          {user?.role === 'org_sub' && (
            <p className="mt-4 text-xs text-muted">Số liệu chỉ tính trên các nguồn crawl bạn được cấp quyền xem.</p>
          )}
        </>
      )}
    </div>
  )
}

const REPORT_POSTS_PAGE_SIZE = 10

function PaginatedPostTable({
  sentiment,
  days,
  entity,
  emptyText,
}: {
  sentiment: 'positive' | 'negative'
  days: number
  entity: string
  emptyText: string
}) {
  const [page, setPage] = useState(1)

  useEffect(() => {
    setPage(1)
  }, [sentiment, days, entity])

  const { data, isLoading } = useQuery({
    queryKey: ['org', 'report', 'posts', sentiment, days, entity, page],
    queryFn: () =>
      orgApi.getReportPosts({
        sentiment,
        days,
        entity: entity || undefined,
        page,
        page_size: REPORT_POSTS_PAGE_SIZE,
      }),
  })

  const posts = data?.items ?? []
  const pageCount = Math.max(1, Math.ceil((data?.total ?? 0) / REPORT_POSTS_PAGE_SIZE))

  if (isLoading) {
    return <p className="p-5 text-sm text-muted">Đang tải…</p>
  }
  if (posts.length === 0) {
    return <p className="p-5 text-sm text-muted">{emptyText}</p>
  }
  return (
    <div className="mt-3">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-5 py-3 font-semibold">Tiêu đề bài đăng</th>
              <th className="px-5 py-3 font-semibold">Kênh</th>
              <th className="px-5 py-3 font-semibold">Người đăng</th>
              <th className="px-5 py-3 font-semibold">Tổng số tương tác</th>
              <th className="px-5 py-3 font-semibold"></th>
            </tr>
          </thead>
          <tbody>
            {posts.map((p) => (
              <tr key={p.id} className="border-b border-line last:border-0">
                <td className="max-w-xs px-5 py-3">
                  <a
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-accent-ink hover:underline"
                  >
                    {p.title}
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                </td>
                <td className="px-5 py-3 text-muted">{p.channel_label}</td>
                <td className="px-5 py-3 text-muted">{p.author || '—'}</td>
                <td className="tabular px-5 py-3">{p.engagement_total.toLocaleString('vi-VN')}</td>
                <td className="px-5 py-3 text-right">
                  <Link
                    to={`/documents?id=${p.id}`}
                    className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-medium text-accent-ink hover:underline"
                  >
                    <FileSearch className="h-3.5 w-3.5" />
                    Chi tiết
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination page={page} pageCount={pageCount} onPageChange={setPage} />
    </div>
  )
}
