import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { ConfirmDialogProvider } from '@/components/ui/confirm-dialog'
import { ToastProvider } from '@/components/ui/toast'
import { router } from './router'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

export function AppProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <ConfirmDialogProvider>
          <RouterProvider router={router} />
        </ConfirmDialogProvider>
      </ToastProvider>
    </QueryClientProvider>
  )
}
