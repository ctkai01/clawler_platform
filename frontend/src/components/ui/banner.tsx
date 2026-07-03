import { cn } from '@/lib/utils'

export function Banner({ tone = 'error', children }: { tone?: 'error' | 'flag'; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        'rounded-md border px-3 py-2 text-sm',
        tone === 'error' && 'border-bad/25 bg-bad-soft text-bad',
        tone === 'flag' && 'border-accent/30 bg-accent-soft text-accent-ink',
      )}
    >
      {children}
    </div>
  )
}
