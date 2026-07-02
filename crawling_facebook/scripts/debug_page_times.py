"""Debug thời gian hiển thị trên feed Page."""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

FEED_TIMES_JS = """
() => {
  const out = [];
  document.querySelectorAll('abbr, a[role="link"], span[dir="auto"]').forEach((el) => {
    const t = (el.getAttribute('title') || el.getAttribute('aria-label') || el.innerText || '').trim();
    if (!t || t.length > 100) return;
    if (/yesterday|today|am|pm|hôm qua|hôm nay|phút|giờ|ngày|minute|hour|day|\\d{1,2}:\\d{2}/i.test(t)) {
      out.push(t);
    }
  });
  return [...new Set(out)].slice(0, 40);
}
"""


async def main() -> None:
    session = Path.home() / ".fb_crawl" / "fb_session.json"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(storage_state=str(session), locale="en-US")
        page = await ctx.new_page()
        await page.goto("https://www.facebook.com/beatvn.network", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        for t in await page.evaluate(FEED_TIMES_JS):
            print(t)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
