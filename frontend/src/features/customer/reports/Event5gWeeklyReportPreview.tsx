import { useQuery } from '@tanstack/react-query'
import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { ComparisonTable, MatchTable, SectionTitle } from './Event5gReportPreview'

const SENTIMENT_COLORS = { positive: '#1f8a5f', neutral: '#8990a0', negative: '#c0392b' }

export function Event5gWeeklyReportPreview() {
  const { data, isLoading } = useQuery({
    queryKey: ['org', 'report', 'event', '5g_mobifone', 'data-weekly'],
    queryFn: () => orgApi.getEventWeeklyReportData('5g_mobifone'),
  })

  if (isLoading || !data) {
    return (
      <Card className="mt-4">
        <p className="text-sm text-muted">Đang tải…</p>
      </Card>
    )
  }

  const brands = Object.keys(data.brand_counts)
  const brandChartData = brands.map((brand) => ({
    brand,
    'Tiêu cực': data.brand_counts[brand].negative,
    'Trung lập': data.brand_counts[brand].neutral,
    'Tích cực': data.brand_counts[brand].positive,
  }))

  return (
    <div className="mt-4">
      <SectionTitle>So sánh sắc thái bài đăng theo nhà mạng</SectionTitle>
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
