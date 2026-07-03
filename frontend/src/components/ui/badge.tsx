import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva('inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium', {
  variants: {
    tone: {
      neutral: 'bg-paper text-muted',
      accent: 'bg-accent-soft text-accent-ink',
      good: 'bg-good-soft text-good',
      bad: 'bg-bad-soft text-bad',
    },
  },
  defaultVariants: { tone: 'neutral' },
})

export function Badge({
  className,
  tone,
  dot,
  children,
}: { children: React.ReactNode; dot?: boolean; className?: string } & VariantProps<typeof badgeVariants>) {
  return (
    <span className={cn(badgeVariants({ tone }), className)}>
      {dot && (
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            tone === 'good' && 'bg-good',
            tone === 'bad' && 'bg-bad',
            tone === 'accent' && 'bg-accent',
            (!tone || tone === 'neutral') && 'bg-faint',
          )}
        />
      )}
      {children}
    </span>
  )
}
