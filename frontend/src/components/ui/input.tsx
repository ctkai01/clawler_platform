import * as React from 'react'
import { cn } from '@/lib/utils'

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        'flex h-9 w-full rounded-md border border-line bg-surface px-3 py-1 text-sm text-ink placeholder:text-faint transition-colors focus-visible:outline-none focus-visible:border-accent-ink focus-visible:ring-2 focus-visible:ring-accent/25 disabled:cursor-not-allowed disabled:bg-paper disabled:opacity-70',
        className,
      )}
      {...props}
    />
  )
}
