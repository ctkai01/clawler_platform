"""Debug: liệt kê link trên feed group để kiểm tra pattern discovery."""
from __future__ import annotations

import asyncio
import json
from collections import Counter
from pathlib import Path

from playwright.async_api import async_playwright

GROUP_URL = "https://www.facebook.com/groups/380912805062832"
SESSION = Path.home() / ".fb_crawl" / "fb_session.json"
SCROLLS = 10

DUMP_LINKS_JS = """
(groupId) => {
  const hrefs = new Set();
  document.querySelectorAll('a[href]').forEach((a) => {
    const href = (a.href || '').split('#')[0];
    if (!href || !href.includes('facebook.com')) return;
    hrefs.add(href);
  });
  const articles = document.querySelectorAll('[role="article"]').length;
  const feedHeight = document.body ? document.body.scrollHeight : 0;
  return { links: [...hrefs], articles, feedHeight };
}
"""


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx_kwargs = {"viewport": {"width": 1280, "height": 900}, "locale": "vi-VN"}
        if SESSION.exists():
            ctx_kwargs["storage_state"] = str(SESSION)
        ctx = await browser.new_context(**ctx_kwargs)
        page = await ctx.new_page()
        await page.goto(GROUP_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)

        all_links: set[str] = set()
        for i in range(SCROLLS):
            data = await page.evaluate(DUMP_LINKS_JS, "380912805062832")
            found = data["links"]
            before = len(all_links)
            all_links.update(found)
            print(
                f"scroll {i+1}: links={len(all_links)} (+{len(all_links)-before}) "
                f"articles={data['articles']} height={data['feedHeight']}"
            )
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2500)

        group_links = [u for u in sorted(all_links) if "/groups/380912805062832" in u]
        print(f"\nTotal fb links: {len(all_links)}")
        print(f"Group-specific links: {len(group_links)}")

        buckets: Counter[str] = Counter()
        for u in group_links:
            if "/permalink/" in u:
                buckets["permalink"] += 1
            elif "/posts/" in u:
                buckets["posts"] += 1
            elif "multi_permalinks" in u:
                buckets["multi_permalinks"] += 1
            elif "/photo" in u or "fbid=" in u:
                buckets["photo"] += 1
            elif "/videos/" in u or "watch?v=" in u:
                buckets["video"] += 1
            else:
                buckets["other"] += 1

        print("Group link buckets:", dict(buckets))
        print("\nAll fb links sample:")
        for u in sorted(all_links):
            if any(x in u for x in ("/posts/", "/permalink/", "/videos/", "watch", "photo", "story_fbid", "multi_permalink")):
                print(" ", u[:160])

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
