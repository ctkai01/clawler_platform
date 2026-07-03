export type Role = 'system_admin' | 'org_main' | 'org_sub'
export type FunctionalRole = 'report_viewer' | 'configurator'

export interface SessionUser {
  id: number
  email: string
  role: Role
  organization_id: number | null
  organization_name: string | null
  functional_role: FunctionalRole | null
  accessible_target_ids: number[] | null
}
