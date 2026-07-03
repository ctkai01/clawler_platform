import { Link } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { defaultRouteForRole } from '@/lib/roleRoutes'

export function ForbiddenPage() {
  const user = useAuthStore((s) => s.user)
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-3 bg-paper px-4 text-center">
      <div className="font-mono text-sm font-medium text-flag">403</div>
      <h1 className="font-display text-xl font-semibold text-ink">Không có quyền truy cập</h1>
      <p className="max-w-sm text-sm text-muted">
        Tài khoản của bạn không có quyền xem trang này. Liên hệ tài khoản Chủ của tổ chức nếu bạn cần được cấp thêm quyền.
      </p>
      <Link
        to={user ? defaultRouteForRole(user.role) : '/login'}
        className="mt-1 text-sm font-medium text-accent-ink hover:underline"
      >
        Về trang chính
      </Link>
    </div>
  )
}
