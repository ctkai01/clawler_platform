import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { Bar, BarChart, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { SectionTitle } from './Event5gReportPreview'
import type { CompetitorPostItem, ReportPostItem } from '@/types/org'

const SENTIMENT_COLORS = { positive: '#1f8a5f', neutral: '#8990a0', negative: '#c0392b' }
const CHANNEL_COLORS = { Facebook: '#3b5bdb', News: '#1f2937', Forum: '#c78a1f' }

function OwnPostTable({ posts, emptyText }: { posts: ReportPostItem[]; emptyText: string }) {
  if (posts.length === 0) {
    return <p className="p-5 text-sm text-muted">{emptyText}</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            <th className="px-5 py-3 font-semibold">Tiêu đề bài đăng</th>
            <th className="px-5 py-3 font-semibold">Kênh</th>
            <th className="px-5 py-3 font-semibold text-right">Tổng số tương tác</th>
          </tr>
        </thead>
        <tbody>
          {posts.map((p) => (
            <tr key={p.id} className="border-b border-line last:border-0">
              <td className="max-w-sm px-5 py-3">
                <a
                  href={p.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-start gap-1 font-medium text-accent-ink hover:underline"
                >
                  <span className="line-clamp-2">{p.title}</span>
                  <ExternalLink className="mt-0.5 h-3 w-3 shrink-0" />
                </a>
              </td>
              <td className="px-5 py-3 text-muted">{p.channel_label}</td>
              <td className="tabular px-5 py-3 text-right">{p.engagement_total.toLocaleString('vi-VN')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CompetitorPostList({ posts, emptyText }: { posts: CompetitorPostItem[]; emptyText: string }) {
  if (posts.length === 0) {
    return <p className="text-sm text-muted">{emptyText}</p>
  }
  return (
    <ul className="space-y-3">
      {posts.map((p) => (
        <li key={p.id}>
          <a
            href={p.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-start gap-1 text-sm font-medium text-accent-ink hover:underline"
          >
            <span className="line-clamp-2">{p.topic || p.content?.slice(0, 80) || p.url}</span>
            <ExternalLink className="mt-0.5 h-3 w-3 shrink-0" />
          </a>
          {p.images.length > 0 && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={p.images[0]}
              alt=""
              className="mt-2 max-h-40 rounded-md border border-line object-cover"
              onError={(e) => {
                e.currentTarget.style.display = 'none'
              }}
            />
          )}
        </li>
      ))}
    </ul>
  )
}

export function CompetitorChannelReportPreview({ period }: { period: 'weekly' | 'monthly' }) {
  const { data, isLoading } = useQuery({
    queryKey: ['org', 'report', 'competitor-channels', 'data', period],
    queryFn: () =>
      period === 'weekly' ? orgApi.getCompetitorChannelReportData() : orgApi.getCompetitorChannelReportDataMonthly(),
  })

  if (isLoading || !data) {
    return (
      <Card className="mt-4">
        <p className="text-sm text-muted">Đang tải…</p>
      </Card>
    )
  }

  const brands = data.brands
  const brandChartData = brands.map((brand) => ({
    brand,
    'Tiêu cực': data.brand_counts[brand].negative,
    'Trung lập': data.brand_counts[brand].neutral,
    'Tích cực': data.brand_counts[brand].positive,
  }))
  const positiveChartData = brands.map((brand) => ({ brand, count: data.brand_counts[brand].positive }))
  const negativeChartData = brands.map((brand) => ({ brand, count: data.brand_counts[brand].negative }))

  return (
    <div className="mt-4">
      <SectionTitle>1. Tổng thông tin thu thập</SectionTitle>
      <Card>
        <div style={{ height: Math.max(180, brands.length * 48) }}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={brandChartData} layout="vertical" margin={{ left: 24 }}>
              <XAxis type="number" tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
              <YAxis type="category" dataKey="brand" width={100} tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Tiêu cực" stackId="s" fill={SENTIMENT_COLORS.negative} />
              <Bar dataKey="Trung lập" stackId="s" fill={SENTIMENT_COLORS.neutral} />
              <Bar dataKey="Tích cực" stackId="s" fill={SENTIMENT_COLORS.positive} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Card>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Thu thập thông tin tích cực</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={positiveChartData}>
                <XAxis dataKey="brand" tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
                <YAxis tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="count" fill={SENTIMENT_COLORS.positive} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Thu thập thông tin tiêu cực</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={negativeChartData}>
                <XAxis dataKey="brand" tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
                <YAxis tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="count" fill={SENTIMENT_COLORS.negative} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <Card>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Thông tin tích cực</p>
          {data.positive_bullets.split('\n').map((line, i) => (
            <p key={i} className="text-sm text-ink">
              {line}
            </p>
          ))}
        </Card>
        <Card>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Thông tin tiêu cực</p>
          {data.negative_bullets.split('\n').map((line, i) => (
            <p key={i} className="text-sm text-ink">
              {line}
            </p>
          ))}
        </Card>
      </div>

      <SectionTitle>2. Các thông tin về {data.org_name} trên MXH</SectionTitle>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Tích cực</p>
      <Card className="p-0">
        <OwnPostTable posts={data.own_positive_posts} emptyText="Không có bài viết tích cực." />
      </Card>
      <p className="mt-4 mb-1 text-xs font-semibold uppercase tracking-wide text-muted">Tiêu cực</p>
      <Card className="p-0">
        <OwnPostTable posts={data.own_negative_posts} emptyText="Không có bài viết tiêu cực." />
      </Card>

      <SectionTitle>3. Top các bài đăng nổi bật của thương hiệu cùng ngành</SectionTitle>
      {brands
        .filter((b) => b !== data.org_name)
        .map((brand) => (
          <div key={brand} className="mt-3 grid gap-4 sm:grid-cols-2">
            <Card>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{brand} — Tích cực</p>
              <CompetitorPostList posts={data.competitor_posts[brand]?.positive ?? []} emptyText="Không có bài nào." />
            </Card>
            <Card>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">{brand} — Tiêu cực</p>
              <CompetitorPostList posts={data.competitor_posts[brand]?.negative ?? []} emptyText="Không có bài nào." />
            </Card>
          </div>
        ))}

      <SectionTitle>4. Thông tin theo kênh về thương hiệu cùng ngành</SectionTitle>
      <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${brands.length}, minmax(0, 1fr))` }}>
        {brands.map((brand) => {
          const breakdown = data.channel_breakdowns[brand]
          const total = breakdown.Facebook + breakdown.News + breakdown.Forum
          const pieData = (['Facebook', 'News', 'Forum'] as const)
            .filter((c) => breakdown[c] > 0)
            .map((c) => ({ name: c, value: breakdown[c], color: CHANNEL_COLORS[c] }))
          return (
            <Card key={brand}>
              <p className="text-center text-xs font-semibold text-ink">{brand}</p>
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={35} outerRadius={60} paddingAngle={2}>
                      {pieData.map((seg) => (
                        <Cell key={seg.name} fill={seg.color} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <p className="text-center text-xs text-muted">{total.toLocaleString('vi-VN')} bài đăng</p>
            </Card>
          )
        })}
      </div>
      <Card className="mt-3">
        {data.channel_bullets.length > 0 ? (
          data.channel_bullets.map((line, i) => (
            <p key={i} className="text-sm text-ink">
              {line}
            </p>
          ))
        ) : (
          <p className="text-sm text-muted">Không có dữ liệu để so sánh kênh.</p>
        )}
      </Card>
    </div>
  )
}
