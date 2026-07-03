import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function Pagination({
  page,
  pageCount,
  onPageChange,
}: {
  page: number
  pageCount: number
  onPageChange: (page: number) => void
}) {
  if (pageCount <= 1) return null

  return (
    <div className="flex items-center justify-between border-t border-line px-5 py-3">
      <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
        <ChevronLeft className="h-3.5 w-3.5" />
        Trước
      </Button>

      <div className="flex items-center gap-2 text-xs text-muted">
        Trang
        <input
          type="number"
          className="tabular h-7 w-14 rounded-md border border-line bg-surface px-2 text-center text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
          value={page}
          min={1}
          max={pageCount}
          onChange={(e) => {
            const next = Number(e.target.value)
            if (Number.isFinite(next) && next >= 1 && next <= pageCount) onPageChange(next)
          }}
        />
        / {pageCount.toLocaleString('vi-VN')}
      </div>

      <Button variant="outline" size="sm" disabled={page >= pageCount} onClick={() => onPageChange(page + 1)}>
        Sau
        <ChevronRight className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}
