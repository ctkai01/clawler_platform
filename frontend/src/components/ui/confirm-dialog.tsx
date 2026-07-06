import { createContext, useCallback, useContext, useState } from 'react'
import { Button } from '@/components/ui/button'

interface ConfirmOptions {
  title?: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: 'default' | 'danger'
}

interface ConfirmContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>
}

const ConfirmContext = createContext<ConfirmContextValue | null>(null)

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<{ options: ConfirmOptions; resolve: (v: boolean) => void } | null>(null)

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setState({ options, resolve })
    })
  }, [])

  const respond = (result: boolean) => {
    state?.resolve(result)
    setState(null)
  }

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {state && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4"
          onClick={() => respond(false)}
        >
          <div
            role="alertdialog"
            aria-modal="true"
            className="w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {state.options.title && (
              <p className="font-display text-base font-semibold text-ink">{state.options.title}</p>
            )}
            <p className={state.options.title ? 'mt-1.5 text-sm text-muted' : 'text-sm text-ink'}>
              {state.options.description}
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => respond(false)}>
                {state.options.cancelLabel ?? 'Huỷ'}
              </Button>
              <Button
                variant={state.options.tone === 'danger' ? 'danger' : 'primary'}
                size="sm"
                onClick={() => respond(true)}
              >
                {state.options.confirmLabel ?? 'Xác nhận'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}

export function useConfirm(): (options: ConfirmOptions) => Promise<boolean> {
  const ctx = useContext(ConfirmContext)
  if (!ctx) throw new Error('useConfirm phải dùng trong <ConfirmDialogProvider>')
  return ctx.confirm
}
