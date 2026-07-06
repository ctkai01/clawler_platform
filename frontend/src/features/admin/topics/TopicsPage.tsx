import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Trash2, Upload } from 'lucide-react'
import { adminApi } from '@/features/admin/adminApi'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Banner } from '@/components/ui/banner'
import { Badge } from '@/components/ui/badge'
import { Pagination } from '@/components/ui/pagination'
import { PageHeader } from '@/components/PageHeader'
import { useConfirm } from '@/components/ui/confirm-dialog'
import { useToast } from '@/components/ui/toast'
import { ApiError } from '@/lib/apiClient'
import type { TopicItem } from '@/types/catalog'

const KEYWORDS_PAGE_SIZE = 30

function TopicCard({ organizationId, topic }: { organizationId: number; topic: TopicItem }) {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const confirm = useConfirm()
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const pageCount = Math.max(1, Math.ceil(topic.keywords.length / KEYWORDS_PAGE_SIZE))

  useEffect(() => {
    if (page > pageCount) setPage(pageCount)
  }, [pageCount, page])

  const pagedKeywords = topic.keywords.slice((page - 1) * KEYWORDS_PAGE_SIZE, page * KEYWORDS_PAGE_SIZE)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['admin', 'topics', organizationId] })

  const addKeyword = useMutation({
    mutationFn: (kw: string) => adminApi.createTopicKeyword(organizationId, topic.id, kw),
    onSuccess: () => {
      setKeyword('')
      invalidate()
    },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Thêm từ khóa thất bại', 'error'),
  })

  const deleteKeyword = useMutation({
    mutationFn: (keywordId: number) => adminApi.deleteTopicKeyword(organizationId, topic.id, keywordId),
    onSuccess: invalidate,
  })

  const deleteTopic = useMutation({
    mutationFn: () => adminApi.deleteTopic(organizationId, topic.id),
    onSuccess: invalidate,
  })

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <p className="font-display font-semibold text-ink">{topic.name}</p>
        <Button
          variant="danger"
          size="sm"
          aria-label={`Xoá chủ đề ${topic.name}`}
          onClick={async () => {
            const ok = await confirm({
              title: 'Xoá chủ đề',
              description: `Xoá chủ đề "${topic.name}" và toàn bộ từ khóa của nó?`,
              confirmLabel: 'Xoá',
              tone: 'danger',
            })
            if (ok) deleteTopic.mutate()
          }}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {topic.keywords.length === 0 ? (
          <p className="text-xs text-muted">Chưa có từ khóa nào.</p>
        ) : (
          pagedKeywords.map((kw) => (
            <span
              key={kw.id}
              className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-xs text-accent-ink"
            >
              {kw.keyword}
              <button
                type="button"
                onClick={() => deleteKeyword.mutate(kw.id)}
                aria-label={`Xoá ${kw.keyword}`}
                className="cursor-pointer rounded-full hover:text-bad"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </span>
          ))
        )}
      </div>
      {topic.keywords.length > KEYWORDS_PAGE_SIZE && (
        <div className="-mx-6 mt-3">
          <Pagination page={page} pageCount={pageCount} onPageChange={setPage} />
        </div>
      )}

      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          if (keyword.trim()) addKeyword.mutate(keyword.trim())
        }}
      >
        <Input
          placeholder="Thêm từ khóa…"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="h-8 text-sm"
        />
        <Button type="submit" size="sm" disabled={addKeyword.isPending}>
          + Thêm
        </Button>
      </form>
    </Card>
  )
}

export function TopicsPage() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const confirm = useConfirm()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const { data: organizations, isLoading: loadingOrgs } = useQuery({
    queryKey: ['admin', 'organizations'],
    queryFn: adminApi.listOrganizations,
  })

  const [organizationId, setOrganizationId] = useState<number | null>(null)
  const [newTopicName, setNewTopicName] = useState('')

  const { data: topics, isLoading: loadingTopics } = useQuery({
    queryKey: ['admin', 'topics', organizationId],
    queryFn: () => adminApi.listTopics(organizationId!),
    enabled: organizationId !== null,
  })

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['admin', 'topics', organizationId] })

  const createTopic = useMutation({
    mutationFn: (name: string) => adminApi.createTopic(organizationId!, name),
    onSuccess: () => {
      setNewTopicName('')
      invalidate()
    },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Tạo chủ đề thất bại', 'error'),
  })

  const importCsv = useMutation({
    mutationFn: (file: File) => adminApi.importTopics(organizationId!, file),
    onSuccess: (result) => {
      invalidate()
      toast(
        `Đã import ${result.topics} chủ đề, ${result.keywords} từ khóa` +
          (result.errors.length ? ` (${result.errors.length} dòng lỗi)` : '.'),
      )
    },
    onError: (err) => toast(err instanceof ApiError ? err.message : 'Import thất bại', 'error'),
  })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Chủ đề"
        description="Danh sách chủ đề + từ khóa theo từng tổ chức, dùng để gắn chủ đề cho bài viết trong báo cáo."
        action={
          <a
            href="/mau_import_chu_de_tu_khoa.csv"
            download
            className="inline-flex h-9 items-center gap-2 rounded-md border border-line bg-surface px-4 text-sm font-medium text-ink transition-colors hover:border-accent-ink hover:text-accent-ink"
          >
            <Download className="h-4 w-4" />
            Tải file mẫu CSV
          </a>
        }
      />

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex min-w-52 flex-1 flex-col gap-1.5">
            <Label htmlFor="topic-org">Tổ chức</Label>
            <select
              id="topic-org"
              className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/25"
              value={organizationId ?? ''}
              disabled={loadingOrgs}
              onChange={(e) => setOrganizationId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— Chọn tổ chức —</option>
              {organizations?.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name}
                </option>
              ))}
            </select>
          </div>
          {organizationId !== null && (
            <div className="flex flex-col gap-1.5">
              <Label>Import CSV (cột chu_de, tu_khoa)</Label>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) importCsv.mutate(file)
                  e.target.value = ''
                }}
              />
              <Button
                type="button"
                variant="outline"
                disabled={importCsv.isPending}
                onClick={async () => {
                  const ok = await confirm({
                    title: 'Import CSV',
                    description:
                      'Import sẽ THAY THẾ toàn bộ chủ đề/từ khóa hiện có của tổ chức này bằng nội dung file CSV. Tiếp tục?',
                    confirmLabel: 'Tiếp tục',
                  })
                  if (ok) fileInputRef.current?.click()
                }}
              >
                <Upload className="h-4 w-4" />
                {importCsv.isPending ? 'Đang import…' : 'Import CSV'}
              </Button>
            </div>
          )}
        </div>
      </Card>

      {organizationId === null ? (
        <Card className="mt-4">
          <p className="text-sm text-muted">Chọn một tổ chức để quản lý chủ đề.</p>
        </Card>
      ) : (
        <>
          <Card className="mt-4">
            <form
              className="flex items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault()
                if (newTopicName.trim()) createTopic.mutate(newTopicName.trim())
              }}
            >
              <div className="flex min-w-52 flex-1 flex-col gap-1.5">
                <Label htmlFor="new-topic">Chủ đề mới</Label>
                <Input
                  id="new-topic"
                  placeholder="vd: MẠNG LƯỚI"
                  value={newTopicName}
                  onChange={(e) => setNewTopicName(e.target.value)}
                />
              </div>
              <Button type="submit" disabled={createTopic.isPending}>
                + Thêm chủ đề
              </Button>
            </form>
            {createTopic.isError && (
              <div className="mt-3">
                <Banner tone="error">
                  {createTopic.error instanceof ApiError ? createTopic.error.message : 'Tạo chủ đề thất bại'}
                </Banner>
              </div>
            )}
          </Card>

          <div className="mt-4 space-y-3">
            {loadingTopics ? (
              <p className="text-sm text-muted">Đang tải…</p>
            ) : !topics || topics.length === 0 ? (
              <Card>
                <p className="text-sm text-muted">Chưa có chủ đề nào cho tổ chức này.</p>
              </Card>
            ) : (
              topics.map((topic) => <TopicCard key={topic.id} organizationId={organizationId} topic={topic} />)
            )}
          </div>

          {topics && topics.length > 0 && (
            <p className="mt-3 text-xs text-muted">
              <Badge tone="neutral">{topics.length} chủ đề</Badge> — bài viết không khớp từ khóa nào sẽ được tính là
              "KHÁC" trong báo cáo.
            </p>
          )}
        </>
      )}
    </div>
  )
}
