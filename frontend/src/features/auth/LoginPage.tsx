import { useState } from 'react'
import { useNavigate, Link, useLocation } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { authApi } from './authApi'
import { setToken } from '@/lib/apiClient'
import { useAuthStore } from '@/store/authStore'
import { defaultRouteForRole } from '@/lib/roleRoutes'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Banner } from '@/components/ui/banner'
import { ApiError } from '@/lib/apiClient'
import { AuthSplitPanel } from './AuthSplitPanel'

const schema = z.object({
  email: z.string().email('Email không hợp lệ'),
  password: z.string().min(1, 'Nhập mật khẩu'),
})
type FormValues = z.infer<typeof schema>

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const setUser = useAuthStore((s) => s.setUser)
  const [serverError, setServerError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) })

  const onSubmit = async (values: FormValues) => {
    setServerError(null)
    setSubmitting(true)
    try {
      const { access_token } = await authApi.login(values)
      setToken(access_token)
      const user = await authApi.me()
      setUser(user)
      const redirectTo = (location.state as { from?: string } | null)?.from ?? defaultRouteForRole(user.role)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setServerError(err instanceof ApiError ? err.message : 'Đăng nhập thất bại')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthSplitPanel>
      <h1 className="font-display text-2xl font-semibold text-ink">Đăng nhập</h1>
      <p className="mt-1.5 text-sm text-muted">Theo dõi thương hiệu của bạn trên mạng xã hội.</p>

      <form className="mt-7 flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
        {serverError && <Banner tone="error">{serverError}</Banner>}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" {...register('email')} />
          {errors.email && <span className="text-xs text-bad">{errors.email.message}</span>}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="password">Mật khẩu</Label>
          <Input id="password" type="password" autoComplete="current-password" {...register('password')} />
          {errors.password && <span className="text-xs text-bad">{errors.password.message}</span>}
        </div>

        <Button type="submit" disabled={submitting} className="mt-2 w-full">
          {submitting ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted">
        Chưa có tài khoản?{' '}
        <Link to="/register" className="font-medium text-accent-ink hover:underline">
          Đăng ký tổ chức mới
        </Link>
      </p>
    </AuthSplitPanel>
  )
}
