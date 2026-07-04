import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { EngagementGrowthPoint } from '@/types/org'

function formatBucket(iso: string) {
  return new Date(iso).toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function EngagementGrowthChart({ data }: { data: EngagementGrowthPoint[] }) {
  if (data.length === 0) {
    return (
      <p className="text-sm text-muted">
        Chưa có dữ liệu tăng trưởng — biểu đồ sẽ có dữ liệu khi hệ thống crawl lại các bài viết này nhiều lần.
      </p>
    )
  }

  const chartData = data.map((p) => ({
    bucket: formatBucket(p.bucket),
    Thích: p.like_count,
    'Bình luận': p.comment_count,
    'Tổng reaction': p.reaction_count,
    'Chia sẻ': p.share_count,
  }))

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
          <XAxis dataKey="bucket" tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
          <YAxis tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="Thích" stroke="#c78a1f" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="Bình luận" stroke="#1f8a5f" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="Tổng reaction" stroke="#8990a0" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="Chia sẻ" stroke="#c0392b" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
