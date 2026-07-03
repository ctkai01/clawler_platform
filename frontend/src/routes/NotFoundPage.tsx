import { Link } from 'react-router-dom'

export function NotFoundPage() {
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-3 bg-paper px-4 text-center">
      <div className="font-mono text-sm text-muted">404</div>
      <h1 className="font-display text-xl font-semibold text-ink">Không tìm thấy trang</h1>
      <Link to="/" className="mt-1 text-sm font-medium text-accent-ink hover:underline">
        Về trang chủ
      </Link>
    </div>
  )
}
