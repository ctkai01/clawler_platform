export const PLATFORM_LABEL: Record<string, string> = {
  facebook_group: 'FB Group',
  facebook_page: 'FB Page',
  forum: 'Forum',
  news: 'News',
}

// Mirrors platform_app/targets/repository.py's mark_running/mark_success/
// mark_failed and facebook_runner.py's status="session_expired" override.
export type BadgeTone = 'neutral' | 'accent' | 'good' | 'bad'

export const SOURCE_STATUS_LABEL: Record<string, string> = {
  running: 'đang crawl',
  ok: 'ok',
  error: 'lỗi',
  session_expired: 'hết phiên đăng nhập',
  chua_crawl: 'chưa crawl',
}

export function sourceStatusTone(status: string | null): BadgeTone {
  if (status === 'ok') return 'good'
  if (status === 'error' || status === 'session_expired') return 'bad'
  if (status === 'running') return 'accent'
  return 'neutral'
}

// Mirrors platform_app/pipeline/classify.py's SENTIMENTS list.
export const SENTIMENT_LABEL: Record<string, string> = {
  positive: 'Tích cực',
  negative: 'Tiêu cực',
  neutral: 'Trung tính',
}

export function sentimentTone(sentiment: string | null): BadgeTone {
  if (sentiment === 'positive') return 'good'
  if (sentiment === 'negative') return 'bad'
  return 'neutral'
}

// Mirrors platform_app/pipeline/classify.py's normal-mode category values.
export const CATEGORY_LABEL: Record<string, string> = {
  khieu_nai: 'Khiếu nại',
  hoi_dap: 'Hỏi đáp',
  khen_ngoi: 'Khen ngợi',
  spam: 'Spam',
  khac: 'Khác',
}
