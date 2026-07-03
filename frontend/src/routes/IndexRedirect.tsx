import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { defaultRouteForRole } from '@/lib/roleRoutes'

/** "/" always redirects — but where depends on role (system_admin has no
 * /dashboard access), so this can't be a static <Navigate to="/dashboard">. */
export function IndexRedirect() {
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={defaultRouteForRole(user.role)} replace />
}
