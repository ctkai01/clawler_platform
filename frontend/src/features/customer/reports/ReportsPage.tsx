import { useState } from 'react'
import { Download } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useToast } from '@/components/ui/toast'
import { PageHeader } from '@/components/PageHeader'
import { FullReportPanel } from '@/features/customer/dashboard/FullReportPanel'
import { cn } from '@/lib/utils'

type ReportKind = 'full-social' | 'export-5g' | 'coming-soon'

interface ReportCatalogItem {
  id: string
  name: string
  target: string
  timing: string
  kind: ReportKind
}

const REPORT_SECTIONS: { title: string; items: ReportCatalogItem[] }[] = [
  {
    title: 'Báo cáo ngày',
    items: [
      {
        id: 'daily-social',
        name: 'Báo cáo mạng xã hội về MobiFone',
        target: 'MobiFone',
        timing: 'Các ngày làm việc trong tuần',
        kind: 'full-social',
      },
      {
        id: 'daily-5g',
        name: 'BC sự vụ: BC 5G MobiFone ngày',
        target: 'MobiFone + Đối thủ',
        timing: 'Các ngày làm việc trong tuần',
        kind: 'export-5g',
      },
    ],
  },
  {
    title: 'Báo cáo tuần',
    items: [
      { id: 'weekly-negative', name: 'Báo cáo tiêu cực về thương hiệu', target: 'MobiFone', timing: 'Gửi vào thứ Hai hàng tuần', kind: 'coming-soon' },
      { id: 'weekly-competitor', name: 'Báo cáo đối thủ ++', target: 'Đối thủ', timing: 'Gửi vào thứ Hai hàng tuần', kind: 'coming-soon' },
      { id: 'weekly-trend', name: 'Báo cáo xu hướng', target: 'MobiFone + Đối thủ', timing: 'Gửi vào thứ Hai hàng tuần', kind: 'coming-soon' },
      { id: 'weekly-direction', name: 'Báo cáo định hướng', target: 'MobiFone', timing: 'Gửi vào thứ Năm hàng tuần', kind: 'coming-soon' },
      { id: 'weekly-5g', name: 'Báo cáo tuần 5G', target: 'MobiFone + Đối thủ', timing: 'Gửi vào thứ Hai hàng tuần', kind: 'coming-soon' },
      { id: 'weekly-review', name: 'Báo cáo tuần kiểm điểm công việc gửi LĐ Ban', target: 'Nội bộ', timing: '—', kind: 'coming-soon' },
    ],
  },
  {
    title: 'Báo cáo tháng',
    items: [
      { id: 'monthly-brand', name: 'Báo cáo tháng thương hiệu MobiFone', target: 'MobiFone', timing: 'Gửi vào ngày 22 hàng tháng', kind: 'coming-soon' },
      { id: 'monthly-competitor', name: 'Báo cáo đối thủ ++ tháng', target: 'Đối thủ', timing: '—', kind: 'coming-soon' },
    ],
  },
]

const ALL_ITEMS = REPORT_SECTIONS.flatMap((s) => s.items)

function Event5gReportDemo() {
  const { toast } = useToast()
  const [exporting, setExporting] = useState(false)

  const handleExport = async () => {
    setExporting(true)
    try {
      await orgApi.exportEventReportWord('5g_mobifone')
    } catch {
      toast('Xuất báo cáo 5G thất bại, vui lòng thử lại.', 'error')
    } finally {
      setExporting(false)
    }
  }

  return (
    <Card>
      <h3 className="font-display text-base font-semibold text-ink">BC sự vụ: BC 5G MobiFone ngày</h3>
      <p className="mt-1 text-sm text-muted">
        So sánh thông tin 5G của MobiFone với đối thủ (Viettel, VinaPhone...) trên cả báo chí và mạng xã hội, kèm đánh giá
        tổng quan sinh bằng LLM.
      </p>
      <Button className="mt-4" variant="outline" size="sm" onClick={handleExport} disabled={exporting}>
        <Download className="h-3.5 w-3.5" />
        {exporting ? 'Đang xuất…' : 'Xuất Word'}
      </Button>
    </Card>
  )
}

export function ReportsPage() {
  const [activeId, setActiveId] = useState(ALL_ITEMS[0].id)
  const activeItem = ALL_ITEMS.find((i) => i.id === activeId) ?? ALL_ITEMS[0]

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title="Báo cáo" description="Danh mục các báo cáo định kỳ của tổ chức." />
      <div className="flex gap-6">
        <nav className="w-72 shrink-0 space-y-5">
          {REPORT_SECTIONS.map((section) => (
            <div key={section.title}>
              <p className="mb-1.5 px-1 text-xs font-semibold uppercase tracking-wide text-muted">{section.title}</p>
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setActiveId(item.id)}
                    className={cn(
                      'flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors',
                      activeId === item.id ? 'bg-ink text-white' : 'text-ink hover:bg-paper',
                    )}
                  >
                    <span className="truncate">{item.name}</span>
                    {item.kind === 'coming-soon' && (
                      <Badge tone="neutral" className={activeId === item.id ? 'bg-white/15 text-white' : ''}>
                        Sắp có
                      </Badge>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="min-w-0 flex-1">
          {activeItem.kind !== 'full-social' && (
            <p className="mb-3 text-xs text-muted">
              Đối tượng: <strong className="text-ink">{activeItem.target}</strong> · {activeItem.timing}
            </p>
          )}
          {activeItem.kind === 'full-social' && <FullReportPanel actions="word-only" />}
          {activeItem.kind === 'export-5g' && <Event5gReportDemo />}
          {activeItem.kind === 'coming-soon' && (
            <Card>
              <p className="text-sm text-muted">Báo cáo này chưa được xây dựng — sẽ cập nhật khi có mẫu cụ thể.</p>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}
