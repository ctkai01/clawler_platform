import { useAuthStore } from '@/store/authStore'
import { PageHeader } from '@/components/PageHeader'
import { FullReportPanel } from '@/features/customer/dashboard/FullReportPanel'

export function ReportDashboardPage() {
  const user = useAuthStore((s) => s.user)

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title={`Tổng quan — ${user?.organization_name ?? ''}`} />
      <FullReportPanel />
    </div>
  )
}
