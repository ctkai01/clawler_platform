import { createBrowserRouter } from 'react-router-dom'
import { RequireAuth, RequireRole, RequireFunctionalPermission } from '@/routes/guards'
import { ForbiddenPage } from '@/routes/ForbiddenPage'
import { NotFoundPage } from '@/routes/NotFoundPage'
import { IndexRedirect } from '@/routes/IndexRedirect'
import { LoginPage } from '@/features/auth/LoginPage'
import { RegisterPage } from '@/features/auth/RegisterPage'
import { AppShell } from '@/app/AppShell'
import { EntityCatalogPage } from '@/features/admin/entities/EntityCatalogPage'
import { KeywordCatalogPage } from '@/features/admin/keywords/KeywordCatalogPage'
import { ReportDashboardPage } from '@/features/customer/dashboard/ReportDashboardPage'
import { DocumentsPage } from '@/features/customer/documents/DocumentsPage'
import { SettingsPage } from '@/features/customer/settings/SettingsPage'
import { EntityKeywordPicker } from '@/features/customer/tracking/EntityKeywordPicker'
import { SourceManagerPage } from '@/features/customer/tracking/SourceManagerPage'
import { SubAccountListPage } from '@/features/customer/members/SubAccountListPage'
import { SubAccountFormPage } from '@/features/customer/members/SubAccountFormPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/register', element: <RegisterPage /> },
  { path: '/403', element: <ForbiddenPage /> },

  {
    element: <RequireAuth />, // lớp 1: đã đăng nhập
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <IndexRedirect /> },
          {
            element: <RequireRole allow={['system_admin']} />, // lớp 2: đúng role
            children: [
              { path: 'admin/entities', element: <EntityCatalogPage /> },
              { path: 'admin/keywords', element: <KeywordCatalogPage /> },
            ],
          },
          {
            element: <RequireRole allow={['org_main', 'org_sub']} />,
            children: [
              { path: 'dashboard', element: <ReportDashboardPage /> },
              { path: 'documents', element: <DocumentsPage /> },
              { path: 'settings', element: <SettingsPage /> },
              {
                element: <RequireFunctionalPermission allow={['configurator']} />, // lớp 3
                children: [
                  { path: 'tracking/entities-keywords', element: <EntityKeywordPicker /> },
                  { path: 'tracking/sources', element: <SourceManagerPage /> },
                ],
              },
              {
                element: <RequireRole allow={['org_main']} />,
                children: [
                  { path: 'members', element: <SubAccountListPage /> },
                  { path: 'members/new', element: <SubAccountFormPage /> },
                  { path: 'members/:id/edit', element: <SubAccountFormPage /> },
                ],
              },
            ],
          },
        ],
      },
    ],
  },

  { path: '*', element: <NotFoundPage /> },
])
