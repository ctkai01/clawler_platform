import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { useAuthStore } from '@/store/authStore'
import { Card } from '@/components/ui/card'
import { Banner } from '@/components/ui/banner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
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

function ClassifyModeCard({ canEdit }: { canEdit: boolean }) {
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
          {!canEdit && <p className="mt-4 text-xs text-muted">Chỉ Tài khoản Chủ mới có thể đổi chế độ phân loại.</p>}
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
  )
}

function EmailTagInput({
  emails,
  onChange,
  disabled,
  id,
  placeholder,
}: {
  emails: string[]
  onChange: (emails: string[]) => void
  disabled?: boolean
  id?: string
  placeholder?: string
}) {
  const [draft, setDraft] = useState('')

  function commit() {
    const trimmed = draft.trim().replace(/,+$/, '')
    if (trimmed && !emails.includes(trimmed)) {
      onChange([...emails, trimmed])
    }
    setDraft('')
  }

  return (
    <div
      className={`flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-line bg-surface px-2 py-1.5 transition-colors focus-within:border-accent-ink focus-within:ring-2 focus-within:ring-accent/25 ${
        disabled ? 'cursor-not-allowed bg-paper opacity-70' : ''
      }`}
    >
      {emails.map((email) => (
        <span
          key={email}
          className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-xs text-accent-ink"
        >
          {email}
          {!disabled && (
            <button
              type="button"
              onClick={() => onChange(emails.filter((e) => e !== email))}
              aria-label={`Xoá ${email}`}
              className="cursor-pointer rounded-full hover:text-bad"
            >
              <X className="h-3 w-3" />
            </button>
          )}
        </span>
      ))}
      <input
        id={id}
        type="email"
        value={draft}
        disabled={disabled}
        placeholder={emails.length === 0 ? placeholder : undefined}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            commit()
          } else if (e.key === 'Backspace' && draft === '' && emails.length > 0) {
            onChange(emails.slice(0, -1))
          }
        }}
        onBlur={commit}
        className="min-w-32 flex-1 border-none bg-transparent text-sm text-ink placeholder:text-faint focus:outline-none disabled:cursor-not-allowed"
      />
    </div>
  )
}

function ReportEmailCard({ canEdit }: { canEdit: boolean }) {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['org', 'settings', 'report-email'],
    queryFn: orgApi.getReportEmail,
  })

  const [recipient, setRecipient] = useState('')
  const [ccEmails, setCcEmails] = useState<string[]>([])
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    if (!data) return
    setRecipient(data.recipient_email ?? '')
    setCcEmails(data.cc_emails)
    setEnabled(data.enabled)
  }, [data])

  const mutation = useMutation({
    mutationFn: () =>
      orgApi.updateReportEmail({
        recipient_email: recipient.trim(),
        cc_emails: ccEmails,
        enabled,
      }),
    onSuccess: (result) => {
      queryClient.setQueryData(['org', 'settings', 'report-email'], result)
    },
  })

  return (
    <Card className="mt-4">
      {isLoading ? (
        <p className="text-sm text-muted">Đang tải…</p>
      ) : (
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            mutation.mutate()
          }}
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-ink">Gửi báo cáo qua email hàng ngày</p>
            <Switch checked={enabled} onChange={setEnabled} disabled={!canEdit} />
          </div>
          <p className="-mt-2 text-xs text-muted">
            Mỗi ngày lúc 8:00, hệ thống tự gửi file Excel báo cáo (giống nút "Xuất Excel") của ngày hôm trước tới email
            bên dưới.
          </p>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="report-email-to">Email nhận báo cáo</Label>
            <Input
              id="report-email-to"
              type="email"
              placeholder="vd: chi.marketing@congty.com"
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              disabled={!canEdit}
              required={enabled}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="report-email-cc">CC (nhập email rồi nhấn Enter)</Label>
            <EmailTagInput
              id="report-email-cc"
              emails={ccEmails}
              onChange={setCcEmails}
              disabled={!canEdit}
              placeholder="vd: a@congty.com"
            />
          </div>

          {canEdit && (
            <div>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? 'Đang lưu…' : 'Lưu'}
              </Button>
            </div>
          )}
          {!canEdit && <p className="text-xs text-muted">Chỉ Tài khoản Chủ mới có thể đổi cài đặt này.</p>}

          {mutation.isSuccess && (
            <Banner tone="flag">Đã lưu cài đặt email báo cáo.</Banner>
          )}
          {mutation.isError && (
            <Banner tone="error">
              {mutation.error instanceof ApiError ? mutation.error.message : 'Lưu cài đặt thất bại'}
            </Banner>
          )}
        </form>
      )}
    </Card>
  )
}

export function SettingsPage() {
  const user = useAuthStore((s) => s.user)
  const canEdit = user?.role === 'org_main'

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Cài đặt" description="Cấu hình phân loại sắc thái và báo cáo email cho tổ chức của bạn." />
      <ClassifyModeCard canEdit={canEdit} />
      <ReportEmailCard canEdit={canEdit} />
    </div>
  )
}
