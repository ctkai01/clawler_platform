import * as React from 'react'
import { cn } from '@/lib/utils'

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-xl border border-line bg-surface p-6 shadow-[0_1px_2px_rgba(23,27,35,0.04),0_1px_8px_rgba(23,27,35,0.03)]',
        className,
      )}
      {...props}
    />
  )
}
