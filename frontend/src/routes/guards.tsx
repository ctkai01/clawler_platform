import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import type { FunctionalRole, Role } from '@/types/auth'

/** Lớp 1: đã đăng nhập. Không redirect trong lúc còn đang bootstrap token
 * từ localStorage — tránh văng người dùng đã đăng nhập ra /login khi họ
 * reload trang. */
export function RequireAuth() {
  const { user, isBootstrapping } = useAuthStore()
  if (isBootstrapping) return null
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}

/** Lớp 2: đúng role hệ thống. */
export function RequireRole({ allow }: { allow: Role[] }) {
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  if (!allow.includes(user.role)) return <Navigate to="/403" replace />
  return <Outlet />
}

/** Lớp 3: quyền chức năng (report_viewer/configurator) — chỉ áp cho
 * org_sub, org_main mặc nhiên có mọi quyền chức năng trong tổ chức mình. */
export function RequireFunctionalPermission({ allow }: { allow: FunctionalRole[] }) {
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'org_sub' && !allow.includes(user.functional_role as FunctionalRole)) {
    return <Navigate to="/403" replace />
  }
  return <Outlet />
}
