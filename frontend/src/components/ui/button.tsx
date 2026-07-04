import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium tracking-tight transition-all duration-150 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-accent active:scale-[0.98]',
  {
    variants: {
      variant: {
        primary: 'bg-accent-ink text-white shadow-sm hover:bg-[#75500c]',
        outline: 'border border-line bg-surface text-ink hover:border-accent-ink hover:text-accent-ink',
        ghost: 'text-muted hover:bg-black/[0.04] hover:text-ink',
        danger: 'border border-bad/25 bg-bad-soft text-bad hover:border-bad/50 hover:bg-bad hover:text-white',
      },
      size: {
        default: 'h-9 px-4',
        sm: 'h-7 rounded px-2.5 text-xs',
      },
    },
    defaultVariants: { variant: 'primary', size: 'default' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
