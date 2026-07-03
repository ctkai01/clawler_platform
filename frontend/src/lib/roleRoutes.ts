import type { Role } from '@/types/auth'

/** Where each role lands after login / at "/" — system_admin has no
 * /dashboard access (RequireRole(['org_main','org_sub'])), so it must not
 * share the customer default. */
export function defaultRouteForRole(role: Role): string {
  return role === 'system_admin' ? '/admin/entities' : '/dashboard'
}
