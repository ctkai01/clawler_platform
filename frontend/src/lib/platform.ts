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
  running: 'Đang crawl',
  ok: 'Thành công',
  error: 'Lỗi',
  session_expired: 'Hết phiên đăng nhập',
  not_a_member: 'Chưa là thành viên',
  checkpoint: 'Tài khoản bị checkpoint',
  chua_crawl: 'Chưa crawl',
}

export const SOURCE_STATUS_DESCRIPTION: Record<string, string> = {
  running: 'Đang trong quá trình crawl — chờ task hiện tại hoàn tất.',
  ok: 'Lần crawl gần nhất thành công.',
  error: 'Lần crawl gần nhất thất bại (không phải do hết phiên đăng nhập) — xem chi tiết ở trang Giám sát.',
  session_expired: 'Crawl thất bại vì phiên đăng nhập Facebook đã hết hạn — cần đăng nhập lại tài khoản.',
  not_a_member:
    'Group này ẩn bài viết với người chưa tham gia (kể cả group Public) — cần một tài khoản đã join group rồi gán thủ công qua fb_session_key.',
  checkpoint:
    'Facebook yêu cầu xác minh danh tính tài khoản này (checkpoint) — ảnh hưởng TẤT CẢ nguồn dùng chung tài khoản, không chỉ nguồn này. Cần xác minh thủ công trong trình duyệt thật rồi export lại session, re-export cookie từ session cũ không giải quyết được.',
  chua_crawl: 'Nguồn mới thêm, chưa từng được crawl lần nào — sẽ tự động crawl ở chu kỳ tiếp theo.',
}

export function sourceStatusTone(status: string | null): BadgeTone {
  if (status === 'ok') return 'good'
  if (status === 'error' || status === 'session_expired' || status === 'not_a_member' || status === 'checkpoint')
    return 'bad'
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
