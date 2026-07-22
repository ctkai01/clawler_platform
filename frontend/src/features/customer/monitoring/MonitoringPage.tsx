import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Banner } from '@/components/ui/banner'
import { Button } from '@/components/ui/button'
import { Pagination } from '@/components/ui/pagination'
import { PageHeader } from '@/components/PageHeader'
import { PLATFORM_LABEL, SOURCE_STATUS_DESCRIPTION, SOURCE_STATUS_LABEL, sourceStatusTone, type BadgeTone } from '@/lib/platform'
import type { CrawledSource, DagRunItem, RecentDocument, SystemStats } from '@/types/org'
import { cn } from '@/lib/utils'

const PLATFORM_ORDER = ['facebook_group', 'facebook_page', 'facebook_profile', 'forum', 'news']
const STATUS_ORDER = ['ok', 'running', 'error', 'session_expired', 'not_a_member', 'checkpoint', 'chua_crawl']
const PLATFORM_COLOR: Record<string, string> = {
  facebook_group: '#3b5bdb',
  facebook_page: '#1f8a5f',
  forum: '#c78a1f',
  news: '#c0392b',
}

const DAG_LABEL: Record<string, string> = {
  facebook_groups_crawl: 'FB Group crawl',
  facebook_pages_crawl: 'FB Page crawl',
  facebook_profiles_crawl: 'FB Profile crawl',
  forums_crawl: 'Forum crawl',
  news_crawl: 'News crawl',
  content_pipeline: 'Content pipeline',
}

const DAG_STATE_LABEL: Record<string, string> = {
  success: 'thành công',
  failed: 'thất bại',
  running: 'đang chạy',
  queued: 'chờ chạy',
}

function dagStateTone(state: string): BadgeTone {
  if (state === 'success') return 'good'
  if (state === 'failed') return 'bad'
  if (state === 'running' || state === 'queued') return 'accent'
  return 'neutral'
}

function formatDateTime(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatDuration(sec: number | null) {
  if (sec == null) return '—'
  if (sec < 60) return `${sec.toFixed(0)}s`
  return `${Math.floor(sec / 60)}p${(sec % 60).toFixed(0).padStart(2, '0')}s`
}

function resourceTone(percent: number): string {
  if (percent >= 90) return 'bg-bad'
  if (percent >= 70) return 'bg-accent'
  return 'bg-good'
}

function ResourceBar({ label, percent, detail }: { label: string; percent: number; detail: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="font-medium text-ink">{label}</span>
        <span className="tabular text-muted">{detail}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-paper">
        <div
          className={cn('h-full rounded-full transition-all', resourceTone(percent))}
          style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
        />
      </div>
    </div>
  )
}

function SystemStatsPanel({ system }: { system: SystemStats | null }) {
  if (!system) {
    return <p className="text-sm text-muted">Không lấy được số liệu CPU/RAM của máy chủ.</p>
  }
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
      <ResourceBar label="CPU" percent={system.cpu_percent} detail={`${system.cpu_percent.toFixed(0)}% · load ${system.load_avg_1m.toFixed(2)}`} />
      <ResourceBar
        label="RAM"
        percent={system.mem_percent}
        detail={`${system.mem_used_gb.toFixed(1)} / ${system.mem_total_gb.toFixed(1)} GB`}
      />
      <ResourceBar
        label="Ổ đĩa"
        percent={system.disk_percent}
        detail={`${system.disk_used_gb.toFixed(0)} / ${system.disk_total_gb.toFixed(0)} GB`}
      />
    </div>
  )
}

function StatusMatrix({ data }: { data: { platform_type: string; status: string; count: number }[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-muted">Chưa có nguồn crawl nào.</p>
  }
  const platforms = PLATFORM_ORDER.filter((p) => data.some((d) => d.platform_type === p))
  const countOf = (platform: string, status: string) =>
    data.find((d) => d.platform_type === platform && d.status === status)?.count ?? 0

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-muted">
            <th className="py-2 pr-4">Nền tảng</th>
            {STATUS_ORDER.map((status) => (
              <th key={status} className="py-2 px-3 text-right">
                {SOURCE_STATUS_LABEL[status] ?? status}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {platforms.map((platform) => (
            <tr key={platform} className="border-b border-line last:border-0">
              <td className="py-2.5 pr-4 font-medium text-ink">{PLATFORM_LABEL[platform] ?? platform}</td>
              {STATUS_ORDER.map((status) => {
                const count = countOf(platform, status)
                return (
                  <td key={status} className="py-2.5 px-3 text-right tabular">
                    {count > 0 ? (
                      <Badge tone={sourceStatusTone(status === 'chua_crawl' ? null : status)}>{count}</Badge>
                    ) : (
                      <span className="text-faint">0</span>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ThroughputChart({ data }: { data: { day: string; platform_type: string; count: number }[] }) {
  if (data.length === 0) {
    return <p className="text-sm text-muted">Chưa có dữ liệu document trong 14 ngày qua.</p>
  }
  const days = Array.from(new Set(data.map((d) => d.day))).sort()
  const platforms = PLATFORM_ORDER.filter((p) => data.some((d) => d.platform_type === p))
  const chartData = days.map((day) => {
    const row: Record<string, string | number> = { day: new Date(day).toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' }) }
    for (const platform of platforms) {
      row[PLATFORM_LABEL[platform] ?? platform] = data.find((d) => d.day === day && d.platform_type === platform)?.count ?? 0
    }
    return row
  })

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-line)" />
          <XAxis dataKey="day" tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
          <YAxis tick={{ fontSize: 11 }} stroke="var(--color-muted)" />
          <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {platforms.map((platform) => (
            <Bar
              key={platform}
              dataKey={PLATFORM_LABEL[platform] ?? platform}
              stackId="docs"
              fill={PLATFORM_COLOR[platform] ?? '#8990a0'}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function CrawledSourcesTable({ sources }: { sources: CrawledSource[] }) {
  if (sources.length === 0) {
    return <p className="text-sm text-muted">Chưa có nguồn nào crawl thành công.</p>
  }
  return (
    <div className="max-h-96 overflow-y-auto overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-muted">
            <th className="py-2 pr-4">Nguồn</th>
            <th className="py-2 pr-4">Nền tảng</th>
            <th className="py-2 pr-4 text-right">Số document</th>
            <th className="py-2 text-right">Crawl gần nhất</th>
          </tr>
        </thead>
        <tbody>
          {sources.map((s) => (
            <tr key={s.id} className="border-b border-line last:border-0">
              <td className="py-2.5 pr-4">
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-ink hover:underline"
                >
                  {s.display_name ?? s.url}
                </a>
              </td>
              <td className="py-2.5 pr-4">
                <Badge tone="neutral">{PLATFORM_LABEL[s.platform_type] ?? s.platform_type}</Badge>
              </td>
              <td className="py-2.5 pr-4 text-right tabular">{s.document_count.toLocaleString('vi-VN')}</td>
              <td className="py-2.5 text-right tabular text-muted">{formatDateTime(s.last_crawled_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RecentDocumentsTable({ documents }: { documents: RecentDocument[] }) {
  if (documents.length === 0) {
    return <p className="text-sm text-muted">Chưa có bài viết nào.</p>
  }
  return (
    <div className="max-h-96 overflow-y-auto overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-muted">
            <th className="py-2 pr-4">Tiêu đề</th>
            <th className="py-2 pr-4">Nền tảng</th>
            <th className="py-2 pr-4">Nguồn</th>
            <th className="py-2 pr-4 text-right">Publish At</th>
            <th className="py-2 text-right">Thêm vào lúc</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((d) => (
            <tr key={d.id} className="border-b border-line last:border-0">
              <td className="max-w-sm truncate py-2.5 pr-4">
                <a
                  href={d.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-ink hover:underline"
                  title={d.topic || d.url}
                >
                  {d.topic || d.url}
                </a>
              </td>
              <td className="py-2.5 pr-4">
                <Badge tone="neutral">{PLATFORM_LABEL[d.platform_type] ?? d.platform_type}</Badge>
              </td>
              <td className="max-w-40 truncate py-2.5 pr-4 text-xs text-muted">{d.target_name ?? '—'}</td>
              <td className="py-2.5 pr-4 text-right tabular text-muted">{formatDateTime(d.published_at)}</td>
              <td className="py-2.5 text-right tabular text-muted">{formatDateTime(d.first_seen_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DagRunTable({ runs }: { runs: DagRunItem[] }) {
  if (runs.length === 0) {
    return <p className="text-sm text-muted">Chưa có lịch sử chạy DAG.</p>
  }
  const byDag = new Map<string, DagRunItem[]>()
  for (const run of runs) {
    if (!byDag.has(run.dag_id)) byDag.set(run.dag_id, [])
    byDag.get(run.dag_id)!.push(run)
  }

  return (
    <div className="space-y-5">
      {Array.from(byDag.entries()).map(([dagId, dagRuns]) => (
        <div key={dagId}>
          <p className="mb-2 text-sm font-medium text-ink">{DAG_LABEL[dagId] ?? dagId}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-muted">
                  <th className="py-1.5 pr-4" title="Giờ thực sự bắt đầu chạy — có thể trễ hơn khung giờ lịch, vì Airflow chỉ tạo run sau khi khung giờ đó kết thúc">
                    Thời điểm chạy
                  </th>
                  <th className="py-1.5 pr-4">Trạng thái</th>
                  <th className="py-1.5 text-right">Thời lượng</th>
                </tr>
              </thead>
              <tbody>
                {dagRuns.map((run) => (
                  <tr key={run.run_id} className="border-b border-line last:border-0">
                    <td className="py-1.5 pr-4 tabular text-muted">{formatDateTime(run.start_date ?? run.execution_date)}</td>
                    <td className="py-1.5 pr-4">
                      <Badge tone={dagStateTone(run.state)}>{DAG_STATE_LABEL[run.state] ?? run.state}</Badge>
                    </td>
                    <td className="py-1.5 text-right tabular text-muted">{formatDuration(run.duration_sec)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  )
}

const FAILING_PAGE_SIZE = 10

export function MonitoringPage() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['org', 'monitoring', 'overview'],
    queryFn: orgApi.getMonitoringOverview,
    refetchInterval: 60_000,
  })
  const [failingPage, setFailingPage] = useState(1)

  const { data: system } = useQuery({
    queryKey: ['org', 'monitoring', 'system'],
    queryFn: orgApi.getMonitoringSystem,
    refetchInterval: 2_000,
    retry: false,
  })

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Giám sát crawl"
        description="Trạng thái nguồn crawl, lịch sử chạy DAG, và số liệu document theo thời gian."
        action={
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            Làm mới
          </Button>
        }
      />

      <div className="mb-6">
        <Card>
          <h3 className="mb-4 font-display text-base font-semibold text-ink">Tài nguyên máy chủ</h3>
          <SystemStatsPanel system={system ?? null} />
        </Card>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted">Đang tải…</p>
      ) : !data ? (
        <p className="text-sm text-bad">Không tải được dữ liệu giám sát.</p>
      ) : (
        <div className="space-y-6">
          {data.airflow_unreachable && (
            <Banner tone="flag">
              Không kết nối được tới Airflow — mục "Lịch sử chạy DAG" tạm thời trống. Trạng thái nguồn crawl và số liệu
              document vẫn chính xác.
            </Banner>
          )}

          <Card>
            <h3 className="mb-4 font-display text-base font-semibold text-ink">Tổng quan trạng thái nguồn</h3>
            <StatusMatrix data={data.sources_by_status} />
          </Card>

          <Card>
            <h3 className="mb-1 font-display text-base font-semibold text-ink">Danh sách lỗi cần xử lý</h3>
            <p className="mb-4 text-xs text-muted">
              {data.failing_sources.length} nguồn đang lỗi hoặc hết phiên đăng nhập, sắp theo số lần lỗi liên tiếp.
            </p>
            {data.failing_sources.length === 0 ? (
              <p className="text-sm text-good">Không có nguồn nào đang lỗi.</p>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-muted">
                        <th className="py-2 pr-4">Nguồn</th>
                        <th className="py-2 pr-4">Trạng thái</th>
                        <th className="py-2 pr-4">Tài khoản FB</th>
                        <th className="py-2 pr-4">Lỗi gần nhất</th>
                        <th className="py-2 pr-4 text-right">Số lần lỗi liên tiếp</th>
                        <th className="py-2 text-right">Crawl gần nhất</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.failing_sources
                        .slice((failingPage - 1) * FAILING_PAGE_SIZE, failingPage * FAILING_PAGE_SIZE)
                        .map((s) => (
                          <tr key={s.id} className="border-b border-line last:border-0 align-top">
                            <td className="py-2.5 pr-4">
                              <div className="font-medium text-ink">{s.display_name ?? s.url}</div>
                              <div className="text-xs text-muted">{PLATFORM_LABEL[s.platform_type] ?? s.platform_type}</div>
                            </td>
                            <td className="py-2.5 pr-4">
                              <Badge tone={sourceStatusTone(s.last_status)} title={SOURCE_STATUS_DESCRIPTION[s.last_status ?? '']}>
                                {SOURCE_STATUS_LABEL[s.last_status ?? ''] ?? s.last_status}
                              </Badge>
                            </td>
                            <td className="py-2.5 pr-4 text-xs text-muted">{s.fb_session_key ?? '—'}</td>
                            <td className="py-2.5 pr-4 max-w-xs truncate text-xs text-muted" title={s.last_error ?? ''}>
                              {s.last_error ?? '—'}
                            </td>
                            <td className="py-2.5 pr-4 text-right tabular">{s.consecutive_failures}</td>
                            <td className="py-2.5 text-right tabular text-muted">{formatDateTime(s.last_crawled_at)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
                <Pagination
                  page={failingPage}
                  pageCount={Math.max(1, Math.ceil(data.failing_sources.length / FAILING_PAGE_SIZE))}
                  onPageChange={setFailingPage}
                />
              </>
            )}
          </Card>

          <Card>
            <h3 className="mb-1 font-display text-base font-semibold text-ink">Nguồn đã crawl thành công</h3>
            <p className="mb-4 text-xs text-muted">
              {data.crawled_sources.length} nguồn, sắp theo lần crawl gần nhất.
            </p>
            <CrawledSourcesTable sources={data.crawled_sources} />
          </Card>

          <Card>
            <h3 className="mb-1 font-display text-base font-semibold text-ink">Bài viết mới thêm vào hệ thống</h3>
            <p className="mb-4 text-xs text-muted">
              {data.recent_documents.length} bài gần nhất, sắp theo thời điểm crawl được.
            </p>
            <RecentDocumentsTable documents={data.recent_documents} />
          </Card>

          <Card>
            <h3 className="mb-1 font-display text-base font-semibold text-ink">Số liệu document theo thời gian</h3>
            <p className="mb-4 text-xs text-muted">Số document mới crawl được mỗi ngày, 14 ngày gần nhất, theo nền tảng.</p>
            <ThroughputChart data={data.document_throughput} />
          </Card>

          <Card>
            <h3 className="mb-1 font-display text-base font-semibold text-ink">Số liệu document sau khi lọc từ khoá</h3>
            <p className="mb-4 text-xs text-muted">
              Chỉ tính document đã khớp từ khoá thương hiệu/đối thủ (keyword_status = &quot;matched&quot;) — phản ánh khối
              lượng thực sự liên quan, không tính bài crawl được nhưng không khớp từ khoá nào.
            </p>
            <ThroughputChart data={data.document_throughput_matched} />
          </Card>

          <Card>
            <h3 className="mb-1 font-display text-base font-semibold text-ink">Số liệu document theo ngày đăng bài</h3>
            <p className="mb-4 text-xs text-muted">
              Gộp theo ngày bài viết THỰC SỰ được đăng (Publish At), không phải ngày crawl được — dùng để xem thực tế
              đã thu thập được bao nhiêu bài cho từng ngày trong quá khứ (vd 13-19/7), khác với 2 biểu đồ trên vốn
              luôn dồn hết vào ngày crawl (hôm nay).
            </p>
            <ThroughputChart data={data.document_publish_timeline} />
          </Card>

          <Card>
            <h3 className="mb-1 font-display text-base font-semibold text-ink">
              Số liệu document theo ngày đăng bài (sau khi lọc từ khoá)
            </h3>
            <p className="mb-4 text-xs text-muted">
              Giống biểu đồ trên nhưng chỉ tính document đã khớp từ khoá thương hiệu/đối thủ (keyword_status =
              &quot;matched&quot;) — số thực sự liên quan cho từng ngày.
            </p>
            <ThroughputChart data={data.document_publish_timeline_matched} />
          </Card>

          <Card>
            <h3 className="mb-1 font-display text-base font-semibold text-ink">Lịch sử chạy DAG</h3>
            <p className="mb-4 text-xs text-muted">5 lần chạy gần nhất mỗi DAG crawl + content_pipeline.</p>
            <DagRunTable runs={data.dag_runs} />
          </Card>
        </div>
      )}
    </div>
  )
}
