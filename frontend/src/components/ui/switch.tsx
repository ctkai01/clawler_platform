import { cn } from '@/lib/utils'

export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (checked: boolean) => void
  label?: string
}) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2">
      <span
        role="switch"
        aria-checked={checked}
        tabIndex={0}
        onClick={() => onChange(!checked)}
        onKeyDown={(e) => {
          if (e.key === ' ' || e.key === 'Enter') {
            e.preventDefault()
            onChange(!checked)
          }
        }}
        className={cn(
          'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40',
          checked ? 'bg-good' : 'bg-line',
        )}
      >
        <span
          className={cn(
            'inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform',
            checked ? 'translate-x-[18px]' : 'translate-x-1',
          )}
        />
      </span>
      {label && <span className="text-xs text-muted">{label}</span>}
    </label>
  )
}
