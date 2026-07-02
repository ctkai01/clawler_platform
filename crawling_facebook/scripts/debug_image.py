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
  const postId = (location.href.match(/\\/(?:posts|permalink)\\/(pfbid[^/?#]+)/i) || [])[1]
    || (location.href.match(/\\/(?:posts|permalink)\\/(\\d+)/) || [])[1]
    || (location.href.match(/\\/groups\\/\\d+\\/(?:posts|permalink)\\/(\\d+)/) || [])[1]
    || '';
  const imgs = [];
  root.querySelectorAll('img').forEach((img, i) => {
    imgs.push({
      i,
      src: (img.src || '').slice(0, 220),
      w: img.naturalWidth || img.width || 0,
      h: img.naturalWidth || img.height || 0,
      role: img.getAttribute('role') || '',
      aria: (img.getAttribute('aria-label') || '').slice(0, 80),
    });
  });
  const links = [];
  root.querySelectorAll('a[href]').forEach((a) => {
    const h = a.href || '';
    if (/photo|fbid|media|set=|picture/i.test(h)) links.push(h.split('#')[0]);
  });
  const scriptUrls = [];
  document.querySelectorAll('script').forEach((s) => {
    const t = s.textContent || '';
    if (postId && !t.includes(postId)) return;
    if (!/scontent|fbcdn|image|photo|uri/i.test(t)) return;
    const keys = ['uri', 'image_uri', 'viewer_image', 'full_image', 'thumbnailImage', 'photo_image'];
    for (const key of keys) {
      const marker = '"' + key + '":"';
      let pos = 0;
      for (let g = 0; g < 20; g++) {
        const idx = t.indexOf(marker, pos);
        if (idx < 0) break;
        let i = idx + marker.length;
        let raw = '';
        while (i < t.length && raw.length < 500) {
          const ch = t[i];
          if (ch === '"' && t.charCodeAt(i - 1) !== 92) break;
          raw += ch;
          i++;
        }
        scriptUrls.push({ key, val: raw.slice(0, 220) });
        pos = i + 1;
      }
    }
  });
  return {
    postId,
    imgCount: imgs.length,
    imgs: imgs.slice(0, 25),
    links: [...new Set(links)].slice(0, 20),
    scriptUrls: scriptUrls.slice(0, 25),
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
        from fb_crawl.facebook_extract import EXTRACT_MEDIA_JS

        print("MEDIA:", json.dumps(await page.evaluate(EXTRACT_MEDIA_JS), ensure_ascii=False, indent=2))
        print("DEBUG:", json.dumps(await page.evaluate(DEBUG_JS), ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
