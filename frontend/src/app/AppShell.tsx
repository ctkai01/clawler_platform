import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/store/authStore'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'

interface NavItem {
  to: string
  label: string
}

function useNavItems(): NavItem[] {
  const user = useAuthStore((s) => s.user)
  if (!user) return []

  if (user.role === 'system_admin') {
    return [
      { to: '/admin/entities', label: 'Entity' },
      { to: '/admin/keywords', label: 'Keyword' },
    ]
  }

  const items: NavItem[] = [
    { to: '/dashboard', label: 'Tổng quan' },
    { to: '/documents', label: 'Bài viết' },
  ]
  const canConfigure = user.role === 'org_main' || user.functional_role === 'configurator'
  if (canConfigure) {
    items.push(
      { to: '/tracking/entities-keywords', label: 'Entity / Keyword' },
      { to: '/tracking/sources', label: 'Nguồn crawl' },
    )
  }
  if (user.role === 'org_main') {
    items.push({ to: '/members', label: 'Thành viên' })
  }
  return items
}

const ROLE_LABEL: Record<string, string> = {
  system_admin: 'System Admin',
  org_main: 'Tài khoản Chủ',
  org_sub: 'Tài khoản Con',
}

export function AppShell() {
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const navigate = useNavigate()
  const navItems = useNavItems()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-svh bg-paper">
      <aside className="flex w-60 shrink-0 flex-col bg-ink text-white">
        <div className="px-5 py-6">
          <div className="font-display flex items-baseline gap-1.5 text-[1.05rem] font-semibold tracking-tight">
            <span className="text-accent">◈</span> Listening Post
          </div>
          <div className="mt-0.5 text-[0.7rem] uppercase tracking-wider text-white/40">Crawl Platform</div>
        </div>

        <nav className="flex-1 px-3">
          <ul className="flex flex-col gap-0.5">
            {navItems.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    cn(
                      'block rounded-md border-l-2 border-transparent px-3 py-2 text-sm text-white/60 transition-colors hover:border-white/20 hover:text-white',
                      isActive && 'border-accent bg-white/6 font-medium text-white',
                    )
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        {user && (
          <div className="border-t border-white/10 px-5 py-4">
            <div className="truncate text-sm font-medium text-white">{user.organization_name ?? 'Hệ thống'}</div>
            <div className="mt-0.5 truncate text-xs text-white/50">{user.email}</div>
            <div className="mt-2 flex items-center justify-between">
              <Badge tone="accent" className="bg-accent/15 text-accent">
                {ROLE_LABEL[user.role]}
              </Badge>
              <button
                type="button"
                onClick={handleLogout}
                className="text-xs font-medium text-white/50 transition-colors hover:text-white"
              >
                Đăng xuất
              </button>
            </div>
          </div>
        )}
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto px-10 py-8">
        <Outlet />
      </main>
    </div>
  )
}
