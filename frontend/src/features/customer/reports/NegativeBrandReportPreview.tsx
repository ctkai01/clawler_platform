import { useQuery } from '@tanstack/react-query'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { SectionTitle } from './Event5gReportPreview'

export function NegativeBrandReportPreview() {
  const { data, isLoading } = useQuery({
    queryKey: ['org', 'report', 'negative-brand', 'data-weekly'],
    queryFn: () => orgApi.getNegativeBrandReportData(),
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
      <SectionTitle>1. Thông tin tổng hợp trong tuần</SectionTitle>
      <Card className="overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-5 py-3 font-semibold">Một số chỉ tiêu</th>
              <th className="px-5 py-3 font-semibold text-right">{data.period_prev_label}</th>
              <th className="px-5 py-3 font-semibold text-right">{data.period_label}</th>
              <th className="px-5 py-3 font-semibold text-right">Tỷ lệ</th>
              <th className="px-5 py-3 font-semibold text-right">So sánh</th>
            </tr>
          </thead>
          <tbody>
            {data.summary_rows.map((row, i) => (
              <tr key={i} className="border-b border-line last:border-0">
                <td className={`px-5 py-3 ${row.bold ? 'font-semibold text-ink' : 'text-muted'}`}>{row.label}</td>
                <td className={`tabular px-5 py-3 text-right ${row.bold ? 'font-semibold text-ink' : ''}`}>
                  {row.prev ?? '—'}
                </td>
                <td className={`tabular px-5 py-3 text-right ${row.bold ? 'font-semibold text-ink' : ''}`}>
                  {row.this ?? '—'}
                </td>
                <td className="tabular px-5 py-3 text-right text-muted">{row.pct ?? '—'}</td>
                <td className="tabular px-5 py-3 text-right text-muted">{row.compare ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="border-t border-line px-5 py-3 text-xs italic text-muted">
          Dòng "Ghi nhận và phối hợp xử lý" cần điền tay — hệ thống chưa có dữ liệu theo dõi xử lý.
        </p>
      </Card>

      <SectionTitle>2. Tổng quan thông tin tiêu cực thu thập</SectionTitle>
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Kênh báo chí online</p>
          <p className="mt-2 text-sm text-ink">{data.news_theme}</p>
          <p className="mt-2 text-xs text-muted">Tỷ trọng nội dung chính: {data.news_pct}</p>
        </Card>
        <Card>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted">Kênh Mạng xã hội</p>
          <p className="mt-2 text-sm text-ink">{data.social_theme}</p>
          <p className="mt-2 text-xs text-muted">Tỷ trọng nội dung chính: {data.social_pct}</p>
        </Card>
      </div>

      <SectionTitle>3. Các điểm nóng phản ánh tiêu cực</SectionTitle>
      <Card>
        <p className="text-sm text-ink">{data.hotspot_text}</p>
        <p className="mt-2 text-xs italic text-muted">
          Địa điểm do LLM trích xuất tự động khi bài viết nhắc rõ — có thể bỏ sót. Mức độ ảnh hưởng và Nguy cơ lan
          rộng vẫn cần điền tay, hệ thống chưa có dữ liệu này.
        </p>
      </Card>

      <SectionTitle>4. Xử lý và cảnh báo tình trạng phản ánh tiêu cực</SectionTitle>
      <Card>
        <p className="text-sm italic text-muted">
          Số liệu xử lý/seeding/định hướng thông tin — hệ thống chưa có dữ liệu này, cần điền tay (xem file Word).
        </p>
      </Card>

      <SectionTitle>5. Đánh giá chung</SectionTitle>
      <Card>
        {data.overview_narrative.split('\n').map((line, i) => (
          <p key={i} className="text-sm text-ink">
            {line}
          </p>
        ))}
      </Card>
    </div>
  )
}
