import { useQuery } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import type { EventMatchItem } from '@/types/org'

export const SENTIMENT_LABEL: Record<string, string> = { positive: 'Tích cực', neutral: 'Trung lập', negative: 'Tiêu cực' }
export const SENTIMENT_TONE: Record<string, string> = {
  positive: 'text-[#1f8a5f]',
  neutral: 'text-muted',
  negative: 'text-[#c0392b]',
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h3 className="mt-6 mb-2 font-display text-sm font-semibold text-ink">{children}</h3>
}

export function MatchTable({ rows, emptyText }: { rows: EventMatchItem[]; emptyText: string }) {
  if (rows.length === 0) {
    return <p className="p-5 text-sm text-muted">{emptyText}</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            <th className="px-5 py-3 font-semibold">Nguồn</th>
            <th className="px-5 py-3 font-semibold">Nội dung</th>
            <th className="px-5 py-3 font-semibold">Sắc thái</th>
            <th className="px-5 py-3 font-semibold">Mức độ ảnh hưởng</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.document_id} className="border-b border-line last:border-0">
              <td className="px-5 py-3 text-ink">{m.target_name}</td>
              <td className="max-w-sm px-5 py-3">
                <a
                  href={m.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-start gap-1 font-medium text-accent-ink hover:underline"
                >
                  <span className="line-clamp-2">{m.topic || m.content?.slice(0, 80) || m.url}</span>
                  <ExternalLink className="mt-0.5 h-3 w-3 shrink-0" />
                </a>
              </td>
              <td className={`px-5 py-3 font-medium ${SENTIMENT_TONE[m.sentiment] ?? ''}`}>
                {SENTIMENT_LABEL[m.sentiment] ?? m.sentiment}
              </td>
              <td className="px-5 py-3 text-muted">{m.impact_level}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ComparisonTable({
  labelA,
  labelB,
  news,
  social,
}: {
  labelA: string
  labelB: string
  news: { yesterday_total: number; today_total: number; yesterday_sentiment: Record<string, number>; today_sentiment: Record<string, number> }
  social: { yesterday_total: number; today_total: number; yesterday_sentiment: Record<string, number>; today_sentiment: Record<string, number> }
}) {
  const rows: { label: string; a: number; b: number; bold?: boolean }[] = [
    { label: 'Thu thập trên kênh Báo chí', a: news.yesterday_total, b: news.today_total, bold: true },
    { label: 'Tích cực', a: news.yesterday_sentiment.positive, b: news.today_sentiment.positive },
    { label: 'Trung lập', a: news.yesterday_sentiment.neutral, b: news.today_sentiment.neutral },
    { label: 'Tiêu cực', a: news.yesterday_sentiment.negative, b: news.today_sentiment.negative },
    { label: 'Thu thập trên kênh Mạng xã hội', a: social.yesterday_total, b: social.today_total, bold: true },
    { label: 'Tích cực', a: social.yesterday_sentiment.positive, b: social.today_sentiment.positive },
    { label: 'Trung lập', a: social.yesterday_sentiment.neutral, b: social.today_sentiment.neutral },
    { label: 'Tiêu cực', a: social.yesterday_sentiment.negative, b: social.today_sentiment.negative },
  ]
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
            <th className="px-5 py-3 font-semibold">Nguồn</th>
            <th className="px-5 py-3 font-semibold text-right">{labelA}</th>
            <th className="px-5 py-3 font-semibold text-right">{labelB}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              <td className={`px-5 py-3 ${row.bold ? 'font-semibold text-ink' : 'text-muted'}`}>{row.label}</td>
              <td className={`tabular px-5 py-3 text-right ${row.bold ? 'font-semibold text-ink' : ''}`}>{row.a}</td>
              <td className={`tabular px-5 py-3 text-right ${row.bold ? 'font-semibold text-ink' : ''}`}>{row.b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Event5gReportPreview() {
  const { data, isLoading } = useQuery({
    queryKey: ['org', 'report', 'event', '5g_mobifone', 'data'],
    queryFn: () => orgApi.getEventReportData('5g_mobifone'),
  })

  if (isLoading || !data) {
    return (
      <Card className="mt-4">
        <p className="text-sm text-muted">Đang tải…</p>
      </Card>
    )
  }

  return (
    <div className="mt-4">
      <SectionTitle>So sánh {data.comparison.yesterday_label} / {data.comparison.today_label}</SectionTitle>
      <Card className="overflow-x-auto p-0">
        <ComparisonTable
          labelA={data.comparison.yesterday_label}
          labelB={data.comparison.today_label}
          news={data.comparison.news}
          social={data.comparison.social}
        />
      </Card>

      <SectionTitle>Đánh giá chung</SectionTitle>
      <Card>
        {data.overview_narrative.split('\n').map((line, i) => (
          <p key={i} className="text-sm text-ink">
            {line}
          </p>
        ))}
      </Card>

      <SectionTitle>Thông tin về {data.event_label} {data.org_name} trên kênh báo chí online</SectionTitle>
      <Card className="p-0">
        <MatchTable rows={data.mobifone_news} emptyText="Không có tin nào." />
      </Card>

      {Object.entries(data.competitor_news).map(([brand, rows]) => (
        <div key={brand}>
          <SectionTitle>Đối thủ: {brand}</SectionTitle>
          <Card className="p-0">
            <MatchTable rows={rows} emptyText="Không có tin nào." />
          </Card>
        </div>
      ))}

      <SectionTitle>Thông tin trên kênh mạng xã hội</SectionTitle>
      <Card className="p-0">
        <MatchTable rows={data.social_matches} emptyText="Không có phản ánh nào." />
      </Card>
    </div>
  )
}
