import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { orgApi } from '@/features/customer/orgApi'
import { useAuthStore } from '@/store/authStore'
import { Card } from '@/components/ui/card'
import { Banner } from '@/components/ui/banner'
import { PageHeader } from '@/components/PageHeader'
import { ApiError } from '@/lib/apiClient'

const MODE_LABEL: Record<string, { title: string; description: string }> = {
  normal: {
    title: 'Normal',
    description: 'Phân loại sắc thái bằng luật/từ khóa, không gọi LLM — nhanh và miễn phí.',
  },
  llm_text: {
    title: 'LLM Text',
    description: 'Dùng LLM đọc tiêu đề + nội dung văn bản để phân loại sắc thái, chủ đề, mức độ nghiêm trọng.',
  },
  llm_image: {
    title: 'LLM Image',
    description: 'Dùng LLM đọc cả văn bản lẫn hình ảnh đính kèm bài viết — chính xác hơn với bài chủ yếu là ảnh, chậm và tốn chi phí hơn.',
  },
}

export function SettingsPage() {
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.role === 'org_main'
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['org', 'settings', 'classify-mode'],
    queryFn: orgApi.getClassifyMode,
  })

  const mutation = useMutation({
    mutationFn: (mode: string) => orgApi.updateClassifyMode(mode),
    onSuccess: (result) => {
      queryClient.setQueryData(['org', 'settings', 'classify-mode'], result)
    },
  })

  const modes = data?.modes ?? ['normal', 'llm_text', 'llm_image']
  const currentMode = data?.mode

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Cài đặt"
        description="Cấu hình chế độ phân loại sắc thái cho tổ chức của bạn."
      />

      <Card>
        {isLoading ? (
          <p className="text-sm text-muted">Đang tải…</p>
        ) : (
          <>
            <p className="mb-4 text-sm font-medium text-ink">Chế độ phân loại (classify mode)</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {modes.map((mode) => {
                const info = MODE_LABEL[mode] ?? { title: mode, description: '' }
                const selected = mode === currentMode
                return (
                  <button
                    key={mode}
                    type="button"
                    disabled={!canEdit || mutation.isPending}
                    onClick={() => mutation.mutate(mode)}
                    className={`rounded-lg border p-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      canEdit ? 'cursor-pointer' : 'cursor-default'
                    } ${
                      selected
                        ? 'border-accent-ink bg-accent-soft/40'
                        : `border-line ${canEdit ? 'hover:border-accent-ink/50 hover:bg-paper/60' : ''}`
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-display font-semibold text-ink">{info.title}</span>
                      {selected && <span className="text-xs font-medium text-accent-ink">Đang dùng</span>}
                    </div>
                    <p className="mt-1.5 text-xs leading-relaxed text-muted">{info.description}</p>
                  </button>
                )
              })}
            </div>
            {!canEdit && (
              <p className="mt-4 text-xs text-muted">Chỉ Tài khoản Chủ mới có thể đổi chế độ phân loại.</p>
            )}
            {mutation.isError && (
              <div className="mt-4">
                <Banner tone="error">
                  {mutation.error instanceof ApiError ? mutation.error.message : 'Cập nhật chế độ phân loại thất bại'}
                </Banner>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  )
}
