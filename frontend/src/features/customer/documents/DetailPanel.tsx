import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ExternalLink, FileSearch, Heart, MessageCircle, Share2, ThumbsUp } from 'lucide-react'
import { orgApi } from '@/features/customer/orgApi'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { PLATFORM_LABEL, CATEGORY_LABEL, SENTIMENT_LABEL, sentimentTone } from '@/lib/platform'

// Plotly (network graph) drags in a multi-MB WebGL bundle — lazy-load it so
// the page's initial JS stays small; only paid for once a document with 2+
// entities is actually opened.
const EntityNetworkGraph = lazy(() =>
  import('@/features/customer/documents/EntityNetworkGraph').then((m) => ({ default: m.EntityNetworkGraph })),
)

function formatDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('vi-VN', { dateStyle: 'medium', timeStyle: 'short' })
}

function EmptyState({ icon, title, subtitle }: { icon: React.ReactNode; title: string; subtitle: string }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-line p-12 text-center">
      <div className="mb-3 text-faint">{icon}</div>
      <p className="font-medium text-ink">{title}</p>
      <p className="mt-1.5 max-w-xs text-sm text-muted">{subtitle}</p>
    </div>
  )
}

const RELATED_SENTIMENT_OPTIONS: { key: string; label: string; sentiments?: string[] }[] = [
  { key: 'all', label: 'Tất cả' },
  { key: 'positive', label: 'Tích cực', sentiments: ['positive'] },
  { key: 'negative', label: 'Tiêu cực', sentiments: ['negative'] },
]

export function DetailPanel({
  documentId,
  onSelect,
  focusEntity,
  focusEntityExact,
}: {
  documentId: number | null
  onSelect: (id: number) => void
  focusEntity?: string
  focusEntityExact?: boolean
}) {
  const [relatedFilter, setRelatedFilter] = useState('all')

  const { data: doc, isLoading } = useQuery({
    queryKey: ['org', 'documents', documentId],
    queryFn: () => orgApi.getDocument(documentId!),
    enabled: documentId != null,
  })
  const { data: comments } = useQuery({
    queryKey: ['org', 'documents', documentId, 'comments'],
    queryFn: () => orgApi.getDocumentComments(documentId!),
    enabled: documentId != null,
  })
  const { data: entityNetwork } = useQuery({
    queryKey: ['org', 'documents', documentId, 'entity-network', focusEntity, focusEntityExact],
    queryFn: () => orgApi.getDocumentEntityNetwork(documentId!, focusEntity, focusEntityExact),
    enabled: documentId != null,
  })
  const activeSentiments = RELATED_SENTIMENT_OPTIONS.find((o) => o.key === relatedFilter)?.sentiments
  const { data: related } = useQuery({
    queryKey: ['org', 'documents', documentId, 'related', relatedFilter],
    queryFn: () => orgApi.getRelatedDocuments(documentId!, activeSentiments, 10),
    enabled: documentId != null,
  })

  if (documentId == null) {
    return (
      <EmptyState
        icon={<FileSearch className="h-9 w-9" />}
        title="Chưa chọn bài viết"
        subtitle='Bấm "Chi tiết →" trên 1 bài viết ở danh sách bên trái để xem nội dung đầy đủ tại đây.'
      />
    )
  }

  if (isLoading || !doc) {
    return <p className="text-sm text-muted">Đang tải…</p>
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line bg-surface p-5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-display text-lg font-semibold text-ink">{doc.topic || 'Không có tiêu đề'}</h2>
          <a href={doc.url} target="_blank" rel="noopener noreferrer" className="shrink-0">
            <Button variant="outline" size="sm">
              <ExternalLink className="h-3.5 w-3.5" />
              Bài gốc
            </Button>
          </a>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
          <Badge tone="neutral">{PLATFORM_LABEL[doc.platform_type] ?? doc.platform_type}</Badge>
          <span>{doc.target_name ?? '—'}</span>
          <span>·</span>
          <span className="tabular">{formatDate(doc.published_at)}</span>
        </div>

        <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed text-ink">{doc.content}</p>

        {doc.images.length > 0 && (
          <div className="mt-4 grid grid-cols-3 gap-2">
            {doc.images.map((src) => (
              <a key={src} href={src} target="_blank" rel="noopener noreferrer">
                <img src={src} alt="" className="aspect-square w-full rounded-md border border-line object-cover" />
              </a>
            ))}
          </div>
        )}

        <div className="mt-4 flex gap-4 border-t border-line pt-3 text-xs text-muted">
          <span className="tabular inline-flex items-center gap-1">
            <ThumbsUp className="h-3.5 w-3.5" /> {doc.like_count.toLocaleString('vi-VN')} thích
          </span>
          <span className="tabular inline-flex items-center gap-1">
            <MessageCircle className="h-3.5 w-3.5" /> {doc.comment_count.toLocaleString('vi-VN')} bình luận
          </span>
          <span className="tabular inline-flex items-center gap-1">
            <Heart className="h-3.5 w-3.5" /> {doc.reaction_count.toLocaleString('vi-VN')} tổng reaction
          </span>
          <span className="tabular inline-flex items-center gap-1">
            <Share2 className="h-3.5 w-3.5" /> {doc.share_count.toLocaleString('vi-VN')} chia sẻ
          </span>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {doc.classification_sentiment && (
            <Badge tone={sentimentTone(doc.classification_sentiment)}>
              {SENTIMENT_LABEL[doc.classification_sentiment] ?? doc.classification_sentiment}
            </Badge>
          )}
          {doc.classification_category && (
            <Badge tone="accent">{CATEGORY_LABEL[doc.classification_category] ?? doc.classification_category}</Badge>
          )}
          {doc.classification_sentiment_source && (
            <Badge tone="neutral">
              {doc.classification_sentiment_source === 'ai' ? 'Đánh giá bởi AI' : 'Đánh giá không dùng LLM'}
            </Badge>
          )}
        </div>
        {doc.entities.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {doc.entities.map((name) => (
              <Badge key={name} tone="accent">
                {name}
              </Badge>
            ))}
          </div>
        )}
      </div>

      {entityNetwork && entityNetwork.nodes.length >= 2 && (
        <div className="rounded-xl border border-line bg-surface p-5">
          <Suspense fallback={<p className="text-sm text-muted">Đang tải sơ đồ…</p>}>
            <EntityNetworkGraph network={entityNetwork} />
          </Suspense>
          <p className="mt-2 text-xs text-muted">
            {entityNetwork.focus_canonical_name
              ? `Chỉ hiện quan hệ trực tiếp với "${entityNetwork.focus_canonical_name}" (đang lọc theo entity này ở trên) — số trên mỗi nhánh là số bài viết khác (trong tổ chức bạn) có cả 2 thực thể cùng xuất hiện.`
              : 'Cạnh nối 2 thực thể = số bài viết khác (trong tổ chức bạn) có cả 2 thực thể đó cùng xuất hiện.'}
          </p>
        </div>
      )}

      <div className="rounded-xl border border-line bg-surface p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">
          Bình luận {comments ? `(${comments.length})` : ''}
        </p>
        {comments && comments.length > 0 ? (
          <ul className="mt-3 space-y-3">
            {comments.map((c, i) => (
              <li key={i} className="border-b border-line pb-3 last:border-0" style={{ marginLeft: c.depth * 16 }}>
                <div className="flex items-center gap-2 text-xs text-muted">
                  <span className="font-medium text-ink">{c.author ?? 'Ẩn danh'}</span>
                  <span className="tabular">{formatDate(c.created_at)}</span>
                </div>
                <p className="mt-1 text-sm text-ink">{c.text}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted">Chưa có bình luận nào.</p>
        )}
      </div>

      <div className="rounded-xl border border-line bg-surface p-5">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Bài viết liên quan (cùng thực thể)</p>
        <div className="mb-3 flex gap-1.5">
          {RELATED_SENTIMENT_OPTIONS.map((o) => (
            <button
              key={o.key}
              type="button"
              onClick={() => setRelatedFilter(o.key)}
              className={`cursor-pointer rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                relatedFilter === o.key ? 'bg-accent-ink text-white' : 'bg-paper text-muted hover:text-ink'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
        {related && related.length > 0 ? (
          <ul className="space-y-2">
            {related.map((r) => (
              <li key={r.id} className="rounded-lg border border-line p-3 hover:bg-paper/60">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-ink">{r.topic || r.content_snippet.slice(0, 100)}</p>
                    <p className="mt-0.5 text-xs text-muted">
                      {r.target_name ?? '—'} · {formatDate(r.published_at)} · {r.shared_entities} thực thể chung
                    </p>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => onSelect(r.id)}>
                    Xem →
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Không có bài viết liên quan nào khớp bộ lọc này.</p>
        )}
      </div>
    </div>
  )
}
