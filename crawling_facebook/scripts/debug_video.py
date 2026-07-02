#!/usr/bin/env python3
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else ""
SESSION = Path.home() / ".fb_crawl" / "fb_session.json"

DEBUG_JS = """
() => {
  const root = document.querySelector('[role="article"]') || document.body;
  const videos = [];
  const links = [];
  const scripts = [];

  root.querySelectorAll('video').forEach((v, i) => {
    videos.push({
      i,
      src: v.src || '',
      currentSrc: v.currentSrc || '',
      poster: v.poster || '',
      aria: v.getAttribute('aria-label') || '',
    });
  });

  root.querySelectorAll('a[href]').forEach((a) => {
    const href = a.href || '';
    if (/video|watch|reel|fbid|photo/i.test(href)) {
      links.push(href.split('#')[0].slice(0, 200));
    }
  });

  document.querySelectorAll('[aria-label]').forEach((el) => {
    const label = el.getAttribute('aria-label') || '';
    if (/video|phát|play|xem/i.test(label) && label.length < 120) {
      links.push('aria:' + label);
    }
  });

  document.querySelectorAll('script').forEach((script) => {
    const text = script.textContent || '';
    if (!/video|playable|browser_native|dash_/i.test(text)) return;
    const keys = ['browser_native_hd_url', 'browser_native_sd_url', 'playable_url', 'permalink_url', 'video_id', 'story_fbid'];
    for (const key of keys) {
      const re = new RegExp('"' + key + '":"([^"]{10,500})"', 'g');
      let m;
      while ((m = re.exec(text))) {
        scripts.push({ key, val: m[1].slice(0, 200) });
        if (scripts.length > 30) break;
      }
    }
  });

  return {
    url: location.href,
    videoCount: videos.length,
    videos: videos.slice(0, 10),
    links: [...new Set(links)].slice(0, 30),
    scripts: scripts.slice(0, 30),
    hasArticle: !!document.querySelector('[role="article"]'),
  };
}
"""


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        kwargs = {"viewport": {"width": 1280, "height": 900}, "locale": "vi-VN"}
        if SESSION.exists():
            kwargs["storage_state"] = str(SESSION)
        ctx = await browser.new_context(**kwargs)
        page = await ctx.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)
        # click play if needed
        try:
            await page.locator('[aria-label*="Phát"], [aria-label*="Play"]').first.click(timeout=3000)
            await page.wait_for_timeout(3000)
        except Exception:
            pass
        data = await page.evaluate(DEBUG_JS)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
