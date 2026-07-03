import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { authApi } from './authApi'
import { setToken, ApiError } from '@/lib/apiClient'
import { useAuthStore } from '@/store/authStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Banner } from '@/components/ui/banner'
import { cn } from '@/lib/utils'
import { AuthSplitPanel } from './AuthSplitPanel'

const TIERS = [
  { value: 'basic', label: 'Basic', note: 'Bắt đầu theo dõi' },
  { value: 'pro', label: 'Pro', note: 'Nhiều nguồn crawl hơn' },
  { value: 'enterprise', label: 'Enterprise', note: 'Không giới hạn + hỗ trợ riêng' },
] as const

const schema = z.object({
  organization_name: z.string().min(1, 'Nhập tên tổ chức/thương hiệu'),
  tier: z.enum(['basic', 'pro', 'enterprise']),
  email: z.string().email('Email không hợp lệ'),
  password: z.string().min(8, 'Mật khẩu tối thiểu 8 ký tự'),
})
type FormValues = z.infer<typeof schema>

export function RegisterPage() {
  const navigate = useNavigate()
  const setUser = useAuthStore((s) => s.setUser)
  const [serverError, setServerError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { tier: 'basic' } })

  const onSubmit = async (values: FormValues) => {
    setServerError(null)
    setSubmitting(true)
    try {
      const { access_token } = await authApi.register(values)
      setToken(access_token)
      const user = await authApi.me()
      setUser(user)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : 'Đăng ký thất bại')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthSplitPanel>
      <h1 className="font-display text-2xl font-semibold text-ink">Đăng ký tổ chức</h1>
      <p className="mt-1.5 text-sm text-muted">Tạo tài khoản Chủ đại diện tổ chức của bạn.</p>

      <form className="mt-7 flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {serverError && <Banner tone="error">{serverError}</Banner>}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="organization_name">Tên tổ chức / thương hiệu</Label>
          <Input id="organization_name" placeholder="VD: Viettel" {...register('organization_name')} />
          {errors.organization_name && <span className="text-xs text-bad">{errors.organization_name.message}</span>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Gói dịch vụ</Label>
          <Controller
            control={control}
            name="tier"
            render={({ field }) => (
              <div className="grid grid-cols-3 gap-2">
                {TIERS.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => field.onChange(t.value)}
                    className={cn(
                      'rounded-lg border px-2.5 py-2 text-left transition-colors',
                      field.value === t.value
                        ? 'border-accent-ink bg-accent-soft'
                        : 'border-line bg-surface hover:border-accent/50',
                    )}
                  >
                    <div
                      className={cn('text-sm font-semibold', field.value === t.value ? 'text-accent-ink' : 'text-ink')}
                    >
                      {t.label}
                    </div>
                    <div className="mt-0.5 text-[0.68rem] leading-tight text-muted">{t.note}</div>
                  </button>
                ))}
              </div>
            )}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" {...register('email')} />
          {errors.email && <span className="text-xs text-bad">{errors.email.message}</span>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Mật khẩu</Label>
          <Input id="password" type="password" autoComplete="new-password" {...register('password')} />
          {errors.password && <span className="text-xs text-bad">{errors.password.message}</span>}
        </div>

        <Button type="submit" disabled={submitting} className="mt-2 w-full">
          {submitting ? 'Đang tạo tài khoản…' : 'Tạo tổ chức & tài khoản'}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        Đã có tài khoản?{' '}
        <Link to="/login" className="font-medium text-accent-ink hover:underline">
          Đăng nhập
        </Link>
      </p>
    </AuthSplitPanel>
  )
}
