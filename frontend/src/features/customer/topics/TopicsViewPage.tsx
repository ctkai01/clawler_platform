import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { orgApi } from '@/features/customer/orgApi'
import { Card } from '@/components/ui/card'
import { Pagination } from '@/components/ui/pagination'
import { PageHeader } from '@/components/PageHeader'
import type { TopicItem } from '@/types/catalog'

const TOPIC_KEYWORDS_PAGE_SIZE = 30

function TopicViewCard({ topic }: { topic: TopicItem }) {
  const [page, setPage] = useState(1)
  const pageCount = Math.max(1, Math.ceil(topic.keywords.length / TOPIC_KEYWORDS_PAGE_SIZE))
  const paged = topic.keywords.slice((page - 1) * TOPIC_KEYWORDS_PAGE_SIZE, page * TOPIC_KEYWORDS_PAGE_SIZE)

  return (
    <Card>
      <p className="font-display font-semibold text-ink">{topic.name}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {topic.keywords.length === 0 ? (
          <p className="text-xs text-muted">Chưa có từ khóa nào.</p>
        ) : (
          paged.map((kw) => (
            <span key={kw.id} className="rounded-full bg-accent-soft px-2 py-0.5 text-xs text-accent-ink">
              {kw.keyword}
            </span>
          ))
        )}
      </div>
      {topic.keywords.length > TOPIC_KEYWORDS_PAGE_SIZE && (
        <div className="-mx-6 mt-3">
          <Pagination page={page} pageCount={pageCount} onPageChange={setPage} />
        </div>
      )}
    </Card>
  )
}

export function TopicsViewPage() {
  const { data: topics, isLoading } = useQuery({
    queryKey: ['org', 'topics'],
    queryFn: orgApi.listTopics,
  })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title="Chủ đề"
        description="Chủ đề/từ khóa do quản trị viên cấu hình cho tổ chức của bạn, dùng để tự động gắn chủ đề cho bài viết trong báo cáo — chỉ xem, không chỉnh sửa được ở đây."
      />
      <div className="space-y-3">
        {isLoading ? (
          <p className="text-sm text-muted">Đang tải…</p>
        ) : !topics || topics.length === 0 ? (
          <Card>
            <p className="text-sm text-muted">Chưa có chủ đề nào được cấu hình cho tổ chức của bạn.</p>
          </Card>
        ) : (
          topics.map((topic) => <TopicViewCard key={topic.id} topic={topic} />)
        )}
      </div>
    </div>
  )
}
