from __future__ import annotations

import re
from datetime import datetime, timezone

from fb_crawl.parser import (
    _stable_id,
    engagement_from_dict,
    extract_group_id,
    extract_page_id,
    extract_post_id,
    extract_user_id,
    parse_comments_structured,
    parse_engagement,
    parse_relative_time,
    resolve_crawled_post_engagement,
)
from fb_crawl.types import Comment, Post, PostEngagement

EXTRACT_POST_PAGE_JS = """
(targetPostId) => {
  const skip = new Set([
    'thích', 'like', 'trả lời', 'reply', 'chia sẻ', 'share', 'bình luận', 'comment',
    'theo dõi', 'follow', 'phản hồi',
  ]);
  const timeRe = /^(\\d+\\s*(phút|giờ|giây|ngày|tuần|tháng|năm|min|hr|h|m|d|w|y|days?|weeks?|months?|years?)(\\s*trước|\\s+ago)?|vừa xong|just now)$/i;

  function cleanLines(text) {
    return (text || '')
      .split('\\n')
      .map((l) => l.trim())
      .filter((l) => l && l !== '·' && !skip.has(l.toLowerCase()) && !timeRe.test(l));
  }

  function parseCommentLabel(label) {
    let m = label.match(/Bình luận dưới tên (.+?) vào (.+)/i);
    if (m) return { author: m[1].trim(), time: m[2].trim(), isReply: false };
    // Current FB wording: "Phản hồi bình luận của <parent author> dưới tên
    // <reply author> vào <time>" — parent author is discarded here (depth/
    // parent linkage comes from DOM order in parse_comments_structured, not
    // from this label); only the actual replier's name matters.
    m = label.match(/Phản hồi bình luận của .+? dưới tên (.+?) vào (.+)/i);
    if (m) return { author: m[1].trim(), time: m[2].trim(), isReply: true };
    m = label.match(/Phản hồi bình luận của .+? dưới tên (.+)/i);
    if (m) return { author: m[1].trim(), time: '', isReply: true };
    m = label.match(/Phản hồi của (.+?) cho bình luận(?:.+?) vào (.+)/i);
    if (m) return { author: m[1].trim(), time: m[2].trim(), isReply: true };
    m = label.match(/Phản hồi của (.+?) cho bình luận/i);
    if (m) return { author: m[1].trim(), time: '', isReply: true };
    m = label.match(/Reply by (.+?) (?:to|on) (.+)/i);
    if (m) return { author: m[1].trim(), time: m[2].trim(), isReply: true };
    m = label.match(/Reply by (.+)/i);
    if (m) return { author: m[1].trim(), time: '', isReply: true };
    m = label.match(/Comment by (.+?) (?:on|at) (.+)/i);
    if (m) return { author: m[1].trim(), time: m[2].trim(), isReply: false };
    m = label.match(/Comment by (.+)/i);
    if (m) return { author: m[1].trim(), time: '', isReply: false };
    return null;
  }

  function extractTimeFromLines(lines, fallback) {
    if (fallback) return fallback;
    for (const l of lines) {
      if (timeRe.test(l)) return l;
    }
    return '';
  }

  function extractUserId(href) {
    if (!href) return '';
    const h = String(href);
    let m = h.match(/\\/user\\/(\\d+)/i);
    if (m) return m[1];
    m = h.match(/\\/groups\\/\\d+\\/user\\/(\\d+)/i);
    if (m) return m[1];
    m = h.match(/[?&]id=(\\d+)/i);
    if (m) return m[1];
    m = h.match(/\\/people\\/[^/?#]+\\/(\\d+)/i);
    if (m) return m[1];
    return '';
  }

  function namesMatch(a, b) {
    const x = (a || '').trim().toLowerCase();
    const y = (b || '').trim().toLowerCase();
    if (!x || !y) return false;
    return x === y || x.includes(y) || y.includes(x);
  }

  function scanAuthorLinks(node, authorName) {
    if (!node || !node.querySelectorAll) return '';
    const target = (authorName || '').trim();
    const links = node.querySelectorAll('a[href]');
    for (const link of links) {
      const href = link.getAttribute('href') || '';
      if (!/(\\/user\\/|\\/people\\/|profile\\.php|\\/groups\\/\\d+\\/user\\/)/i.test(href)) {
        continue;
      }
      const uid = extractUserId(href);
      if (!uid) continue;
      const name = (link.innerText || link.getAttribute('aria-label') || '').trim();
      if (!name || name.length > 80) continue;
      if (namesMatch(name, target)) return uid;
    }
    return '';
  }

  function findAuthorId(root, authorName) {
    const target = (authorName || '').trim();
    if (!target || /^(ẩn danh|anonymous)$/i.test(target)) return '';
    let found = scanAuthorLinks(root, target);
    if (found) return found;
    let node = root ? root.parentElement : null;
    for (let i = 0; i < 14 && node; i++) {
      found = scanAuthorLinks(node, target);
      if (found) return found;
      node = node.parentElement;
    }
    return '';
  }

  function buildAuthorIdLookup() {
    const byName = new Map();
    document.querySelectorAll('script').forEach((script) => {
      const text = script.textContent || '';
      const re =
        /"author":\\{"__typename":"User","id":"(\\d+)","name":"((?:[^"\\\\]|\\\\.)*)"/g;
      let match;
      while ((match = re.exec(text))) {
        const name = decodeFbString(match[2]).trim();
        if (!name) continue;
        byName.set(name.toLowerCase(), match[1]);
      }
    });
    return byName;
  }

  function lookupAuthorIdNearName(authorName) {
    const target = (authorName || '').trim();
    if (!target) return '';
    for (const script of document.querySelectorAll('script')) {
      const text = script.textContent || '';
      let from = 0;
      while (from < text.length) {
        const idx = text.indexOf(target, from);
        if (idx < 0) break;
        from = idx + target.length;
        const slice = text.slice(Math.max(0, idx - 350), idx + 350);
        if (!/comment|feedback|CometUFI|story/i.test(slice)) continue;
        const idBefore = slice.match(/"id":"(\\d{6,})"[^}]{0,160}?"name":"/);
        const idAfter = slice.match(/"name":"[^"]*"[^}]{0,160}?"id":"(\\d{6,})"/);
        const idNear = (idAfter && idAfter[1]) || (idBefore && idBefore[1]);
        if (idNear) return idNear;
      }
    }
    return '';
  }

  function lookupAuthorId(root, authorName, authorIdLookup) {
    const fromDom = findAuthorId(root, authorName);
    if (fromDom) return fromDom;
    const target = (authorName || '').trim().toLowerCase();
    if (authorIdLookup && target && authorIdLookup.has(target)) {
      return authorIdLookup.get(target);
    }
    return lookupAuthorIdNearName(authorName);
  }

  function parseIntCount(s) {
    const raw = String(s || '').trim();
    if (!raw) return 0;

    let m = raw.match(/^([\\d.,]+)\\s*([KkMm])$/);
    if (!m) m = raw.match(/([\\d.,]+)\\s*([KkMm])\\b/);
    if (m) {
      const num = parseDecimalCount(m[1]);
      if (!num) return 0;
      const mult = m[2].toLowerCase() === 'm' ? 1000000 : 1000;
      return Math.round(num * mult);
    }

    m = raw.match(/(\\d[\\d.,]*)/);
    if (!m) return 0;
    const part = m[1];
    if (/^\\d{1,3}(\\.\\d{3})+$/.test(part)) {
      return parseInt(part.replace(/\\./g, ''), 10) || 0;
    }
    if (/^\\d+,\\d{3}$/.test(part)) {
      return parseInt(part.replace(/,/g, ''), 10) || 0;
    }
    if (part.includes(',') && !part.includes('.')) {
      const n = parseFloat(part.replace(/,/g, '.'));
      return Number.isFinite(n) ? Math.round(n) : 0;
    }
    return parseInt(part.replace(/\\./g, '').replace(/,/g, ''), 10) || 0;
  }

  function parseDecimalCount(part) {
    const s = String(part || '').trim();
    if (!s) return 0;
    if (s.includes(',') && s.includes('.')) {
      return parseFloat(s.replace(/,/g, '')) || 0;
    }
    if (s.includes(',')) {
      const bits = s.split(',');
      if (bits[1] && bits[1].length === 3 && bits.length === 2) {
        return parseInt(bits.join(''), 10) || 0;
      }
      return parseFloat(bits.join('.')) || 0;
    }
    return parseFloat(s.replace(/\\./g, '')) || parseFloat(s) || 0;
  }

  const TYPED_REACTION_PATTERNS = [
    [/(?:yêu thích|loves?)\\s*:\\s*([\\d.,]+\\s*[KkMm]?)\\s*người/i, 'love'],
    [/(?:thương thương|care)\\s*:\\s*([\\d.,]+\\s*[KkMm]?)\\s*người/i, 'care'],
    [/(?:thích|likes?)\\s*:\\s*([\\d.,]+\\s*[KkMm]?)\\s*người/i, 'like'],
    [/(?:phẫn nộ|angrys?)\\s*:\\s*([\\d.,]+\\s*[KkMm]?)\\s*người/i, 'angry'],
    [/(?:buồn|sads?)\\s*:\\s*([\\d.,]+\\s*[KkMm]?)\\s*người/i, 'sad'],
    [/(?:haha|ha ha)\\s*:\\s*([\\d.,]+\\s*[KkMm]?)\\s*người/i, 'haha'],
    [/(?:wow|ngạc nhiên)\\s*:\\s*([\\d.,]+\\s*[KkMm]?)\\s*người/i, 'wow'],
    [/(?:thương thương|care)\\s*:\\s*([\\d.,]+\\s*[KkMm]?)\\s*người/i, 'care'],
    [/([\\d.,]+\\s*[KkMm]?)\\s+người\\s+(?:đã\\s+)?yêu thích/i, 'love'],
    [/([\\d.,]+\\s*[KkMm]?)\\s+người\\s+(?:đã\\s+)?(?:bày tỏ\\s+)?thích/i, 'like'],
    [/([\\d.,]+\\s*[KkMm]?)\\s+người\\s+(?:đã\\s+)?phẫn nộ/i, 'angry'],
    [/([\\d.,]+\\s*[KkMm]?)\\s+người\\s+(?:đã\\s+)?buồn/i, 'sad'],
    [/([\\d.,]+\\s*[KkMm]?)\\s+người\\s+(?:đã\\s+)?haha/i, 'haha'],
  ];

  function emptyEngagement() {
    return { like_count: 0, share_count: 0, comment_count: 0, reaction_count: 0, reactions: {} };
  }

  function mergeEngagement(a, b) {
    const reactions = { ...(a.reactions || {}) };
    Object.entries(b.reactions || {}).forEach(([key, val]) => {
      reactions[key] = Math.max(reactions[key] || 0, val || 0);
    });
    return {
      like_count: Math.max(a.like_count || 0, b.like_count || 0),
      share_count: Math.max(a.share_count || 0, b.share_count || 0),
      comment_count: Math.max(a.comment_count || 0, b.comment_count || 0),
      reaction_count: Math.max(a.reaction_count || 0, b.reaction_count || 0),
      reactions,
    };
  }

  function applyTypedReaction(out, key, val) {
    if (!val) return;
    if (key === 'like') out.like_count = Math.max(out.like_count || 0, val);
    else out.reactions[key] = Math.max(out.reactions[key] || 0, val);
  }

  function parseTypedReactions(text) {
    const out = emptyEngagement();
    if (!text) return out;
    TYPED_REACTION_PATTERNS.forEach(([re, key]) => {
      const m = text.match(re);
      if (m) applyTypedReaction(out, key, parseIntCount(m[1]));
    });
    return out;
  }

  function parseTotalReactionCount(text) {
    if (!text) return 0;
    const patterns = [
      /tất cả cảm xúc\\s*:?\\s*([\\d.,]+\\s*[KkMm]?)/i,
      /all reactions\\s*:?\\s*([\\d.,]+\\s*[KkMm]?)/i,
      /([\\d.,]+\\s*[KkMm]?)\\s+người đã bày tỏ cảm xúc/i,
    ];
    for (const re of patterns) {
      const m = text.match(re);
      if (m) return parseIntCount(m[1]);
    }
    return 0;
  }

  function isPostReactionToolbar(label) {
    return /xem ai đã bày tỏ cảm xúc về tin này|who reacted to this/i.test(label || '');
  }

  function isCommentReactionLabel(label) {
    return /bình luận này|this comment|comment by|phản hồi của|reply by|bài viết của|post by/i.test(label || '');
  }

  function extractPostReactionToolbar(scope) {
    let eng = emptyEngagement();
    const root = scope || document.body;
    root.querySelectorAll('[role="toolbar"][aria-label]').forEach((toolbar) => {
      const label = toolbar.getAttribute('aria-label') || '';
      if (!isPostReactionToolbar(label)) return;
      toolbar.querySelectorAll('[role="button"][aria-label]').forEach((btn) => {
        const btnLabel = btn.getAttribute('aria-label') || '';
        if (!btnLabel || isCommentReactionLabel(btnLabel)) return;
        const parsed = parseTypedReactions(btnLabel);
        if ((parsed.like_count || 0) > 0 || Object.values(parsed.reactions).some((v) => v > 0)) {
          eng = mergeEngagement(eng, parsed);
        }
      });
    });
    return eng;
  }

  function reactionBreakdownSum(eng) {
    let sum = eng.like_count || 0;
    Object.values(eng.reactions || {}).forEach((v) => {
      sum += v || 0;
    });
    return sum;
  }

  function otherReactionSum(eng) {
    return Object.entries(eng.reactions || {}).reduce(
      (s, [k, v]) => s + (k === 'like' ? 0 : (v || 0)),
      0,
    );
  }

  function normalizeEngagement(eng) {
    if (!eng) return emptyEngagement();
    eng.reactions = eng.reactions || {};
    if (!eng.like_count && eng.reactions.like) {
      eng.like_count = eng.reactions.like;
    }
    const other = otherReactionSum(eng);
    if (eng.like_count && eng.reaction_count && eng.like_count === eng.reaction_count && other > 0) {
      eng.like_count = eng.reactions.like || 0;
    }
    delete eng.reactions.other;
    const breakdown = reactionBreakdownSum(eng);
    if (!eng.reaction_count) {
      eng.reaction_count = breakdown;
    } else if (breakdown > eng.reaction_count) {
      eng.reaction_count = breakdown;
    } else if (breakdown > 0 && eng.reaction_count > breakdown) {
      eng.reactions.other = eng.reaction_count - breakdown;
    }
    return eng;
  }

  function parseEngagementFromText(text) {
    const out = parseTypedReactions(text);
    if (!text) return out;
    const total = parseTotalReactionCount(text);
    if (total) out.reaction_count = Math.max(out.reaction_count || 0, total);
    const patterns = [
      [/([\\d.,]+\\s*[KkMm]?)\\s*(bình luận|comments?)/i, 'comment_count'],
      [/([\\d.,]+\\s*[KkMm]?)\\s*(lượt chia sẻ|chia sẻ|shares?)/i, 'share_count'],
    ];
    patterns.forEach(([re, key]) => {
      const m = text.match(re);
      if (!m) return;
      const val = parseIntCount(m[1]);
      out[key] = Math.max(out[key] || 0, val);
    });
    return out;
  }

  const REACTION_NODE_IDS = {
    '1635855486666999': 'like',
    '1678524932434102': 'love',
    '115940658764963': 'haha',
    '478547315650144': 'wow',
    '908563459236466': 'sad',
    '444813342392137': 'angry',
    '615977619379348': 'care',
  };

  const REACTION_NAME_PATTERNS = [
    [/yêu thích|love/i, 'love'],
    [/thương thương|care/i, 'care'],
    [/phẫn nộ|angry/i, 'angry'],
    [/buồn|sad/i, 'sad'],
    [/haha|ha ha/i, 'haha'],
    [/wow|ngạc nhiên/i, 'wow'],
    [/thích|like/i, 'like'],
  ];

  function decodeFbString(raw) {
    if (!raw) return '';
    return raw.replace(/\\\\u([0-9a-fA-F]{4})/g, (_, hex) =>
      String.fromCharCode(parseInt(hex, 16)),
    );
  }

  function mapReactionKey(name, nodeId) {
    const decoded = decodeFbString(name || '');
    for (const [re, key] of REACTION_NAME_PATTERNS) {
      if (re.test(decoded)) return key;
    }
    return REACTION_NODE_IDS[nodeId || ''] || null;
  }

  function extractTopReactionsFromScripts(expectedTotal) {
    const blocks = [];
    const edgeRe =
      /"node":\\{"id":"(\\d+)"(?:,"localized_name":"((?:[^"\\\\]|\\\\.)*)")?\\}[^}]*?"reaction_count":(\\d+)/g;

    document.querySelectorAll('script').forEach((script) => {
      const text = script.textContent || '';
      if (!text.includes('top_reactions') || !text.includes('localized_name')) return;

      let searchFrom = 0;
      while (searchFrom < text.length) {
        const idx = text.indexOf('top_reactions":', searchFrom);
        if (idx < 0) break;
        const slice = text.slice(idx, idx + 5000);
        searchFrom = idx + 14;

        if (!slice.includes('localized_name')) continue;

        const edges = [];
        let match;
        edgeRe.lastIndex = 0;
        while ((match = edgeRe.exec(slice))) {
          const nodeId = match[1];
          const name = match[2] || '';
          const count = parseInt(match[3], 10);
          if (!count || !name) continue;
          const key = mapReactionKey(name, nodeId);
          if (!key) continue;
          edges.push({ key, count });
        }

        if (edges.length < 1) continue;

        const total = edges.reduce((sum, edge) => sum + edge.count, 0);
        const countMatch = slice.match(/top_reactions":\\{"count":(\\d+)/);
        const declaredCount = countMatch ? parseInt(countMatch[1], 10) : total;
        blocks.push({ edges, total, declaredCount });
      }
    });

    if (!blocks.length) return emptyEngagement();

    const seen = new Set();
    const unique = [];
    blocks.forEach((block) => {
      const sig = block.edges
        .map((edge) => `${edge.key}:${edge.count}`)
        .sort()
        .join('|');
      if (seen.has(sig)) return;
      seen.add(sig);
      unique.push(block);
    });

    if (expectedTotal <= 0) {
      // No DOM-read total to anchor against — every past incident here
      // involved script-tag data for an unrelated (usually far more
      // viral) post/comment on the same page overwriting a legitimate,
      // much smaller per-post total, e.g. a post with 48 real reactions
      // getting stamped with 43,560 from something else entirely. With no
      // signal to tell blocks apart, guessing (old code picked whichever
      // block had the highest total) is worse than reporting nothing —
      // callers already treat "no engagement data found" as a normal,
      // expected state.
      return emptyEngagement();
    }

    let best = unique[0];
    for (const block of unique) {
      if (block.total === expectedTotal) {
        best = block;
        break;
      }
      // Prefer the block whose total is CLOSEST to the DOM-read expected
      // total. The old "pick highest total" strategy caused script-tag
      // data from the group page or related posts (which can be millions)
      // to overwrite a per-post total of a few thousand.
      if (Math.abs(block.total - expectedTotal) < Math.abs(best.total - expectedTotal)) {
        best = block;
      } else if (
        Math.abs(block.total - expectedTotal) === Math.abs(best.total - expectedTotal) &&
        block.edges.length > best.edges.length
      ) {
        best = block;
      }
    }

    let eng = emptyEngagement();
    best.edges.forEach((edge) => applyTypedReaction(eng, edge.key, edge.count));
    eng.reaction_count = Math.max(best.declaredCount, best.total);
    return eng;
  }

  function findPostEngagementRoot(scope) {
    const root = scope || document.body;
    const btn = [...root.querySelectorAll('[aria-label]')].find((el) =>
      /xem ai đã bày tỏ cảm xúc về tin này/i.test(el.getAttribute('aria-label') || ''),
    );
    if (btn) {
      let best = null;
      let node = btn;
      for (let i = 0; i < 12 && node; i++) {
        const text = node.innerText || '';
        if (text.length > 900) {
          node = node.parentElement;
          continue;
        }
        if (/tất cả cảm xúc/i.test(text) && /bình luận|comments?/i.test(text)) {
          return node;
        }
        if (/tất cả cảm xúc/i.test(text)) {
          best = node;
        }
        node = node.parentElement;
      }
      if (best) return best;
      return btn.parentElement || btn;
    }
    const marker = [...root.querySelectorAll('span, div')].find((el) =>
      /tất cả cảm xúc/i.test((el.innerText || '').trim()),
    );
    if (marker) {
      let best = marker.parentElement;
      let node = marker.parentElement;
      for (let i = 0; i < 10 && node; i++) {
        const text = node.innerText || '';
        if (text.length > 900) break;
        if (/tất cả cảm xúc/i.test(text) && /bình luận|comments?/i.test(text)) {
          return node;
        }
        if (/tất cả cảm xúc/i.test(text)) best = node;
        node = node.parentElement;
      }
      return best;
    }
    return null;
  }

  function extractPostEngagement(root) {
    let eng = emptyEngagement();
    const scope = root || document.body;

    eng = mergeEngagement(eng, extractPostReactionToolbar(scope));

    const bar = findPostEngagementRoot(scope);
    const barText = bar ? bar.innerText || '' : '';
    if (barText) {
      eng = mergeEngagement(eng, parseEngagementFromText(barText));
    }

    const expectedTotal =
      eng.reaction_count || parseTotalReactionCount(barText || scope.innerText || '');
    eng = mergeEngagement(eng, extractTopReactionsFromScripts(expectedTotal));

    return normalizeEngagement(eng);
  }

  function parseEngagementLabel(label) {
    const l = (label || '').trim();
    if (!l) return null;
    let out = parseTypedReactions(l);
    let m = l.match(/([\\d.,]+\\s*[KkMm]?)\\s*(comments?|bình luận)/i);
    if (m) out.comment_count = Math.max(out.comment_count || 0, parseIntCount(m[1]));
    m = l.match(/([\\d.,]+\\s*[KkMm]?)\\s*(shares?|chia sẻ|lượt chia sẻ)/i);
    if (m) out.share_count = Math.max(out.share_count || 0, parseIntCount(m[1]));

    const hasTyped = (out.like_count || 0) > 0 || Object.values(out.reactions).some((v) => v > 0);
    if (!hasTyped) {
      m = l.match(/([\\d.,]+\\s*[KkMm]?)\\s*(người đã bày tỏ cảm xúc|reactions?|cảm xúc)/i);
      if (m) out.reaction_count = parseIntCount(m[1]);
    }

    if (!out.reaction_count && !out.like_count && !out.comment_count && !out.share_count && !hasTyped) {
      return null;
    }
    return out;
  }

  function findCommentRow(el) {
    let node = el;
    let best = el;
    for (let i = 0; i < 16 && node; i++) {
      const text = node.innerText || '';
      if (text.length > 5000) {
        node = node.parentElement;
        continue;
      }
      if (/thích|like/i.test(text) && /trả lời|reply/i.test(text)) {
        best = node;
      }
      node = node.parentElement;
    }
    return best;
  }

  function parseLinesEngagement(lines) {
    let eng = emptyEngagement();
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      let m = line.match(/^(\\d+)\\s*(thích|likes?)$/i);
      if (m) {
        eng.like_count = Math.max(eng.like_count, parseInt(m[1], 10));
        continue;
      }
      m = line.match(/^(\\d+)\\s*(yêu thích|loves?)$/i);
      if (m) {
        eng.reactions.love = Math.max(eng.reactions.love || 0, parseInt(m[1], 10));
        continue;
      }
      m = line.match(/^(\\d+)\\s*(phẫn nộ|angrys?)$/i);
      if (m) {
        eng.reactions.angry = Math.max(eng.reactions.angry || 0, parseInt(m[1], 10));
        continue;
      }
      m = line.match(/^(\\d+)\\s*(buồn|sads?)$/i);
      if (m) {
        eng.reactions.sad = Math.max(eng.reactions.sad || 0, parseInt(m[1], 10));
        continue;
      }
      m = line.match(/^(\\d+)\\s*(haha|ha ha)$/i);
      if (m) {
        eng.reactions.haha = Math.max(eng.reactions.haha || 0, parseInt(m[1], 10));
        continue;
      }
      if (/^(thích|like)$/i.test(line)) {
        for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
          const next = lines[j];
          if (/^\\d+$/.test(next)) {
            eng.like_count = Math.max(eng.like_count, parseInt(next, 10));
            break;
          }
          if (/^(trả lời|reply|bình luận|comment|yêu thích|phẫn nộ)$/i.test(next)) break;
        }
      }
    }
    return normalizeEngagement(eng);
  }

  function hasEngagementData(eng) {
    if (!eng) return false;
    if ((eng.like_count || 0) > 0 || (eng.reaction_count || 0) > 0) return true;
    return Object.values(eng.reactions || {}).some((v) => (v || 0) > 0);
  }

  function extractCommentEngagement(el, rawLines) {
    let eng = emptyEngagement();
    const row = findCommentRow(el);
    const rowText = (row.innerText || '').slice(0, 1500);
    eng = mergeEngagement(eng, parseEngagementFromText(rowText));

    const rowLines = rowText
      .split('\\n')
      .map((l) => l.trim())
      .filter((l) => l && l !== '·');
    eng = mergeEngagement(eng, parseLinesEngagement(rowLines));
    eng = mergeEngagement(eng, parseLinesEngagement(rawLines));

    if (row.querySelectorAll) {
      row.querySelectorAll('[aria-label]').forEach((child) => {
        const label = child.getAttribute('aria-label') || '';
        if (/bình luận dưới tên|phản hồi của|comment by|reply by|bài viết của/i.test(label)) {
          return;
        }
        if (!/(thích|like|yêu thích|love|phẫn nộ|angry|reaction|cảm xúc|người)/i.test(label)) {
          return;
        }
        const parsed = parseEngagementLabel(label);
        if (parsed) eng = mergeEngagement(eng, parsed);
      });
    }

    eng._found = hasEngagementData(eng);
    return normalizeEngagement(eng);
  }

  // A permalink URL (esp. opaque pfbid IDs) doesn't always render as an
  // isolated single-post view — Facebook sometimes serves the Page's
  // regular feed instead. Blindly taking the FIRST [role="article"] then
  // silently attaches a DIFFERENT post's content to this URL (wrong post
  // pinned/most-recent at the top). Prefer the article whose own links
  // reference the requested post's ID.
  function findMatchingArticle(id) {
    if (!id) return null;
    // A comment's own deep-link ALSO embeds the parent post's id (e.g.
    // ".../posts/{id}/?comment_id=..."), so a plain substring match on the
    // id matches every comment's article just as well as the post's own.
    // Real incident: the post's article was still a "Loading..." skeleton
    // (0 links) when checked, so this matched the first already-rendered
    // COMMENT instead and saved its text as the post's content. Excluding
    // comment_id links makes a comment's article structurally unmatchable,
    // regardless of load timing.
    const articles = document.querySelectorAll('[role="article"]');
    for (const el of articles) {
      const links = el.querySelectorAll('a[href]');
      for (const a of links) {
        const href = a.getAttribute('href') || '';
        if (href.includes(id) && !href.includes('comment_id=')) return el;
      }
    }
    return null;
  }

  const matchedRoot = findMatchingArticle(targetPostId);
  // Opening a permalink URL often renders the post as a [role="dialog"]
  // overlaying the group/page's regular feed, rather than as its own
  // standalone page. In that view the OP's own post text is NOT wrapped
  // in [role="article"] at all (confirmed live) — only comments/replies
  // are — so findMatchingArticle can never find it there by definition,
  // no matter how long we wait. Fall back to the whole dialog as the
  // search scope in that case; the comment-exclusion filter below (which
  // strips every known comment's text out of the candidate list) is what
  // keeps this from picking up a comment instead of the real post.
  // There can be more than one [role="dialog"] on the page at once (a
  // hovercard/tooltip/menu can also use that role) — the FIRST one isn't
  // reliably the content modal, so pick whichever dialog actually has
  // comments (confirmed live: this varies between loads of the exact
  // same URL).
  const dialog = [...document.querySelectorAll('[role="dialog"]')].find(
    (d) => d.querySelector('[role="article"]')
  );
  const dialogHasComments = !!dialog;
  if (targetPostId && !matchedRoot && !dialogHasComments) {
    // We know exactly which post we want but couldn't find its article OR
    // a dialog to fall back to (Facebook rendered something else — a
    // suggested/viral post, a login-wall, etc). Falling back to "first
    // article" here is what caused a real incident: a small page's post
    // got saved with a completely unrelated viral post's content and
    // 373k fake reactions. Returning nothing is strictly safer than
    // returning the wrong thing.
    return {
      url: location.href, groupId: '', pageId: '', author: '', authorId: '', topic: '',
      content: '', publishedTime: '', publishedUnix: null, isEdited: false,
      editedTime: '', images: [], videos: [], engagement: normalizeEngagement(null), comments: [],
    };
  }
  // Only matchedRoot / the confirmed comments-bearing dialog are actually
  // THIS post's own container — the remaining fallbacks (first [role=
  // "article"] on the page, first FeedUnit, document.body) exist so
  // content/comment extraction still has *something* to search, but they
  // can just as easily be a different post entirely, or the whole page.
  // Kept separate from postRoot so engagement extraction below can refuse
  // to trust a root it isn't confident about — same failure mode as the
  // 373k-fake-reactions incident above, just for likes/reactions instead
  // of content: a real incident had a post's like_count read as 12,153
  // (matching the Page's own like/follower count) off a same-sized
  // discrepancy when postRoot fell through to a too-broad scope.
  const safeRoot = matchedRoot || (targetPostId && dialogHasComments ? dialog : null);
  const postRoot =
    safeRoot ||
    document.querySelector('[role="article"]') ||
    document.querySelector('div[data-pagelet*="FeedUnit"]') ||
    document.body;

  const url = location.href;
  const groupMatch = url.match(/\\/groups\\/(\\d+)/);
  const groupId = groupMatch ? groupMatch[1] : '';
  let pageId = '';
  if (!groupId) {
    const pageMatch = url.match(/facebook\\.com\\/([^/?#]+)/i);
    const reserved = new Set([
      'groups', 'watch', 'photo', 'permalink.php', 'story.php', 'share',
      'login', 'recover', 'help', 'policies', 'privacy', 'marketplace',
      'gaming', 'reel', 'reels', 'events', 'friends', 'notifications',
      'messages', 'settings', 'pages', 'profile.php', 'people',
    ]);
    if (pageMatch && !reserved.has(pageMatch[1].toLowerCase())) {
      pageId = pageMatch[1];
    }
  }

  // --- Author: từ aria-label "bài viết của X" ---
  // Scoped to postRoot, not document — same class of bug as the content
  // extraction below: scanning the whole page can pick up an unrelated
  // "bài viết của X" aria-label from a sidebar/suggested-post module.
  const authorCounts = {};
  postRoot.querySelectorAll('[aria-label]').forEach((el) => {
    const label = el.getAttribute('aria-label') || '';
    // "X's post" (e.g. "Comment on Anonymous participant's post") is the
    // toolbar-button phrasing seen in a permalink-dialog view — different
    // wording from the "bài viết của X"/"post by X" phrasing used
    // elsewhere, but the same signal.
    const m =
      label.match(/bài viết của (.+)$/i) ||
      label.match(/post by (.+)$/i) ||
      label.match(/^.+ (?:to|on) (.+)'s post$/i);
    if (m) {
      const name = m[1].trim();
      authorCounts[name] = (authorCounts[name] || 0) + 1;
    }
  });

  // --- Comment texts để loại khỏi nội dung bài ---
  const commentTexts = new Set();
  const comments = [];
  const seenComments = new Set();
  const seenCommentNodes = new Set();
  const authorIdLookup = buildAuthorIdLookup();

  document.querySelectorAll('[aria-label]').forEach((el) => {
    const label = el.getAttribute('aria-label') || '';
    const parsed = parseCommentLabel(label);
    if (!parsed) return;

    // Facebook sometimes renders the same comment as two DOM nodes sharing
    // the exact aria-label — one with normal line breaks, one with all
    // whitespace collapsed (likely an a11y/measurement duplicate). Whitespace
    // differs, so dedupe on label + whitespace-stripped innerText instead of
    // parsed body text (which the collapsed variant can't parse correctly).
    const nodeKey = label + '||' + (el.innerText || '').replace(/\\s+/g, '');
    if (seenCommentNodes.has(nodeKey)) return;
    seenCommentNodes.add(nodeKey);

    const rawLines = (el.innerText || '')
      .split('\\n')
      .map((l) => l.trim())
      .filter((l) => l && l !== '·');
    const lines = rawLines.filter(
      (l) => !skip.has(l.toLowerCase()) && !timeRe.test(l)
    );
    let body = lines.filter((l) => l !== parsed.author).join('\\n').trim();
    body = body.replace(/^Theo dõi\\s*/i, '').trim();
    body = body.replace(/\\n\\d+$/, '').trim();
    if (!body) return;

    const key = parsed.author + '|' + body.replace(/\\s+/g, ' ').slice(0, 60);
    if (seenComments.has(key)) return;
    seenComments.add(key);
    commentTexts.add(body);

    comments.push({
      author: parsed.author,
      author_id: lookupAuthorId(el, parsed.author, authorIdLookup),
      body,
      text: parsed.author + '\\n' + body,
      depth: parsed.isReply ? 1 : 0,
      time: extractTimeFromLines(rawLines, parsed.time),
      engagement: (() => {
        const e = extractCommentEngagement(el, rawLines);
        return { ...e, found: !!e._found };
      })(),
    });
  });

  // --- Nội dung bài: div[dir=auto] dài nhất, không trùng comment ---
  // Scoped to postRoot (the article), NOT the whole document — real bug
  // found in production: scanning the whole page let a comment that
  // parseCommentLabel failed to recognize (so it never landed in
  // commentTexts) get picked up as a "candidate" alongside the post's own
  // text, and since selection is "longest div wins", a long-ish spam
  // comment (a common bot-posted ad, byte-for-byte identical across 100+
  // unrelated posts/pages) beat a short real caption that Facebook split
  // across several shorter divs. Every other extraction in this file
  // (images, engagement) is already scoped to postRoot — this one wasn't.
  const candidates = [];
  postRoot.querySelectorAll('div[dir="auto"]').forEach((el) => {
    const t = (el.innerText || '').trim();
    if (t.length < 40) return;
    if (/xem thêm$/i.test(t) && t.length < 120) return;
    if (commentTexts.has(t)) return;
    // Bidirectional substring check, not just startsWith/equality — the
    // candidate div's text and the parsed comment body frequently DON'T
    // match either exactly or as a clean prefix: a comment's own div can
    // render as "{Author}{body}" with no separator (candidate is LONGER
    // than c.body), while the parsed comment body itself often has
    // "{Author}\\n{body}\\nSee translation\\nEdited" wrapped around the
    // same core text (c.body is LONGER than the candidate div, which only
    // holds the bare paragraph). Either direction has to count as a
    // match, or real comment text keeps slipping through as if it were
    // the post's own content.
    if (comments.some((c) => c.body && (t.includes(c.body) || c.body.includes(t)))) return;
    if (/^(Thích|Trả lời|Chia sẻ|Like|Reply|Share)$/i.test(t)) return;
    candidates.push({ text: t, len: t.length, el });
  });

  candidates.sort((a, b) => b.len - a.len);

  let topic = '';
  let content = '';
  let author = '';
  let authorId = '';

  if (candidates.length) {
    const main = candidates[0].text;
    const mainEl = candidates[0].el;
    const prefix = main.slice(0, 40);
    const related = candidates.filter((c) => {
      if (c.text === main) return true;
      // div[dir="auto"] matches at every nesting level, so a container
      // holding the full post text and each of its own paragraph's wrapper
      // divs all land in `candidates`. Skip anything in the same subtree as
      // `main` (ancestor or descendant) — that's the same content, not a
      // genuinely separate block — to avoid duplicating it below.
      if (mainEl.contains(c.el) || c.el.contains(mainEl)) return false;
      return c.text.includes(prefix.slice(0, 20)) || main.includes(c.text.slice(0, 20));
    });

    const mainLines = main.split('\\n').map((l) => l.trim()).filter(Boolean);
    topic = mainLines[0] || '';

    const contentParts = related
      .map((c) => c.text)
      .filter((t) => t !== topic);
    content = contentParts.join('\\n\\n').trim();

    if (topic.length > 200) {
      content = (content ? topic + '\\n\\n' + content : topic).trim();
      topic = topic.slice(0, 150).trim() + '…';
    }

    // Prefer the aria-label-derived author (authorCounts, computed above)
    // when it's unambiguous — it's Facebook's own "this is the post's
    // author" signal, tied directly to the post rather than inferred from
    // DOM proximity. Real incident: an anonymous-post author ("Anonymous
    // participant") has no profile link at all, so the DOM-walk below
    // found nothing near the post and kept climbing until it picked up
    // the first COMMENTER's real profile link instead.
    if (Object.keys(authorCounts).length === 1) {
      author = Object.keys(authorCounts)[0];
    }

    // Walk up from the content div looking for a profile link, but never past
    // postRoot — real bug found in production: Page posts link to the page
    // via /PageName/ (doesn't match /user/ or profile.php), so this walk
    // found nothing nearby and kept climbing past the post's own boundary
    // into page-wide chrome (top nav / account switcher), where it picked up
    // a link to the CRAWLER'S OWN LOGGED-IN SESSION ACCOUNT and misattributed
    // dozens of unrelated posts across many different pages to that one
    // account. Stop the walk at postRoot itself.
    if (!author) {
      const anchor = candidates[0];
      let node = anchor.el;
      for (let i = 0; i < 15 && node; i++) {
        const links = node.querySelectorAll
          ? node.querySelectorAll('a[href*="/user/"], a[href*="profile.php"]')
          : [];
        for (const link of links) {
          const name = (link.innerText || '').trim();
          const href = link.getAttribute('href') || '';
          if (name && name.length < 60 && !/^(Theo dõi|Follow|THE LIEMS|Nhóm)$/i.test(name)) {
            author = name;
            authorId = extractUserId(href);
            break;
          }
        }
        if (author || node === postRoot) break;
        node = node.parentElement;
      }
    }
  }

  if (!author) {
    const sortedAuthors = Object.entries(authorCounts).sort((a, b) => b[1] - a[1]);
    if (sortedAuthors.length === 1) {
      author = sortedAuthors[0][0];
    } else if (sortedAuthors.length > 1) {
      author = sortedAuthors[sortedAuthors.length - 1][0];
    }
  }

  if (!authorId && author) {
    authorId = findAuthorId(postRoot, author);
  }

  // Engagement (likes/reactions/shares) read from an unconfirmed root is
  // not trustworthy — see safeRoot's comment above. comment_count is fine
  // either way: it's overridden right below by comments.length, which
  // went through its own matching-post filtering separately.
  const postEngagement = safeRoot ? extractPostEngagement(postRoot) : normalizeEngagement(null);
  postEngagement.comment_count = Math.max(postEngagement.comment_count, comments.length);

  function looksLikeFbTime(t) {
    if (!t || t.length > 50) return false;
    if (timeRe.test(t)) return true;
    if (/^\\d+\\s*(phút|giờ|ngày|giây|min|hr|h|m|d|day|days?\\s+ago)/i.test(t)) return true;
    if (/^(?:yesterday|today|hôm qua|hôm nay)\\b/i.test(t)) return true;
    if (/^\\d{1,2}\\s*(?:tháng|thg)\\s*\\d{1,2}/i.test(t)) return true;
    if (/^(?:january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\\s+\\d{1,2}/i.test(t)) return true;
    if (/\\b\\d{1,2}:\\d{2}\\s*(?:am|pm)?\\b/i.test(t) && t.length < 35) return true;
    return false;
  }

  let publishedTime = '';
  let publishedUnix = null;
  const timeScopes = postRoot ? [postRoot, document] : [document];
  for (const scope of timeScopes) {
    scope.querySelectorAll('abbr[data-utime], span[data-utime], a[data-utime]').forEach((el) => {
      const raw = el.getAttribute('data-utime');
      if (raw && !publishedUnix) {
        const n = parseInt(raw, 10);
        if (Number.isFinite(n) && n > 0) publishedUnix = n;
      }
    });
    if (publishedUnix) break;
  }
  document.querySelectorAll('[aria-label]').forEach((el) => {
    const label = el.getAttribute('aria-label') || '';
    const timeM = label.match(/bài viết của .+ vào (.+)$/i)
      || label.match(/post by .+ (?:on|at) (.+)$/i);
    if (timeM && !publishedTime) publishedTime = timeM[1].trim();
  });
  if (!publishedTime) {
    for (const scope of timeScopes) {
      for (const el of scope.querySelectorAll('a[href], span, abbr')) {
        const title = (el.getAttribute('title') || '').trim();
        const inner = (el.innerText || '').trim();
        for (const t of [title, inner]) {
          if (looksLikeFbTime(t)) {
            publishedTime = t;
            break;
          }
        }
        if (publishedTime) break;
      }
      if (publishedTime) break;
    }
  }

  let isEdited = false;
  let editedTime = '';
  const postText = (postRoot.innerText || '').slice(0, 4000);
  if (/đã chỉnh sửa|edited/i.test(postText)) {
    isEdited = true;
    const lines = postText.split('\\n').map((l) => l.trim()).filter(Boolean);
    for (const line of lines) {
      if (/đã chỉnh sửa|edited/i.test(line) && line.length < 80) {
        editedTime = line;
        break;
      }
    }
  }

  const images = [];
  const videos = [];

  return {
    url,
    groupId,
    pageId,
    author,
    authorId,
    topic,
    content,
    publishedTime,
    publishedUnix,
    isEdited,
    editedTime,
    images,
    videos,
    engagement: postEngagement,
    comments,
  };
}
"""

EXPAND_COMMENTS_JS = """
async (opts) => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const maxRounds = opts?.maxRounds ?? 50;
  const targetCount = opts?.targetCount ?? 0;

  function parseIntCount(raw) {
    if (!raw) return 0;
    let s = String(raw).trim().replace(/\\s/g, '').replace(',', '.');
    const km = s.match(/^([\\d.]+)([KkMm])$/);
    if (km) {
      const n = parseFloat(km[1]);
      if (!Number.isFinite(n)) return 0;
      return Math.round(n * (km[2].toLowerCase() === 'm' ? 1e6 : 1e3));
    }
    const n = parseFloat(s);
    return Number.isFinite(n) ? Math.round(n) : 0;
  }

  function countVisibleComments() {
    let n = 0;
    document.querySelectorAll('[aria-label]').forEach((el) => {
      const label = el.getAttribute('aria-label') || '';
      if (/Bình luận dưới tên|Phản hồi của|Comment by|Reply by/i.test(label)) {
        n++;
      }
    });
    return n;
  }

  function readTargetFromPage() {
    if (targetCount > 0) return targetCount;
    for (const el of document.querySelectorAll('[aria-label], span, div')) {
      const text = (el.getAttribute('aria-label') || el.innerText || '').trim();
      const m = text.match(/([\\d.,]+\\s*[KkMm]?)\\s*bình luận/i)
        || text.match(/([\\d.,]+\\s*[KkMm]?)\\s*comments?/i);
      if (m) return parseIntCount(m[1]);
    }
    return 0;
  }

  function clickButtons(patterns, excludePatterns) {
    let clicks = 0;
    const seen = new Set();
    for (const el of document.querySelectorAll(
      '[role="button"], span, a, div[tabindex="0"]'
    )) {
      const text = (el.innerText || '').trim();
      if (!text || text.length > 80) continue;
      if (excludePatterns.some((p) => p.test(text))) continue;
      if (!patterns.some((p) => p.test(text))) continue;
      const key = text + '|' + (el.getBoundingClientRect?.().top ?? 0);
      if (seen.has(key)) continue;
      seen.add(key);
      try {
        el.scrollIntoView({ block: 'center' });
        el.click();
        clicks++;
      } catch (e) {}
    }
    return clicks;
  }

  const mainPatterns = [
    /xem thêm bình luận/i,
    /view more comments/i,
    /view previous comments/i,
  ];
  const mainExclude = [/phản hồi|repl/i];
  const replyPatterns = [
    /xem thêm phản hồi/i,
    /view more replies/i,
    /xem tất cả \\d+ phản hồi/i,
    /view all \\d+ repl/i,
    // Facebook also renders bare reply-count toggles with no "thêm"/"tất cả"
    // qualifier (e.g. "Xem 2 phản hồi", "2 phản hồi", "2 replies") — without
    // these, threads whose replies are hidden behind that shorter label
    // never get expanded at all.
    /^xem\\s*\\d*\\s*phản hồi/i,
    /^\\d+\\s*phản hồi$/i,
    /^view\\s*\\d*\\s*repl/i,
    /^\\d+\\s*repl(y|ies)$/i,
  ];

  const target = readTargetFromPage();
  let staleRounds = 0;
  let prevCount = countVisibleComments();

  for (let round = 0; round < maxRounds; round++) {
    // Click both every round (not reply-only-as-fallback) — otherwise a
    // thread with many top-level comments can exhaust the whole round
    // budget on pagination and never get to expand nested replies at all.
    const mainClicks = clickButtons(mainPatterns, mainExclude);
    const replyClicks = clickButtons(replyPatterns, []);
    const clicks = mainClicks + replyClicks;
    window.scrollBy(0, Math.round(window.innerHeight * 0.75));
    await sleep(clicks > 0 ? 600 : 350);

    const current = countVisibleComments();
    if (target > 0 && current >= Math.max(target - 5, Math.floor(target * 0.9))) {
      break;
    }
    if (current === prevCount && clicks === 0) {
      staleRounds++;
      if (staleRounds >= 3) break;
    } else {
      staleRounds = 0;
      prevCount = current;
    }
  }

  return { count: countVisibleComments(), target };
}
"""

EXTRACT_MEDIA_JS = """
(targetPostId) => {
  // See EXTRACT_POST_PAGE_JS's findMatchingArticle comment — same fix,
  // needed here too so images/videos don't get attached to the wrong post.
  function findMatchingArticle(id) {
    if (!id) return null;
    // A comment's own deep-link ALSO embeds the parent post's id (e.g.
    // ".../posts/{id}/?comment_id=..."), so a plain substring match on the
    // id matches every comment's article just as well as the post's own.
    // Real incident: the post's article was still a "Loading..." skeleton
    // (0 links) when checked, so this matched the first already-rendered
    // COMMENT instead and saved its text as the post's content. Excluding
    // comment_id links makes a comment's article structurally unmatchable,
    // regardless of load timing.
    const articles = document.querySelectorAll('[role="article"]');
    for (const el of articles) {
      const links = el.querySelectorAll('a[href]');
      for (const a of links) {
        const href = a.getAttribute('href') || '';
        if (href.includes(id) && !href.includes('comment_id=')) return el;
      }
    }
    return null;
  }

  const matchedRoot = findMatchingArticle(targetPostId);
  // See EXTRACT_POST_PAGE_JS's dialog-fallback comment — the OP's post
  // isn't wrapped in [role="article"] in a permalink-modal view, so widen
  // to the dialog rather than failing closed when one is present.
  // There can be more than one [role="dialog"] on the page at once (a
  // hovercard/tooltip/menu can also use that role) — the FIRST one isn't
  // reliably the content modal, so pick whichever dialog actually has
  // comments (confirmed live: this varies between loads of the exact
  // same URL).
  const dialog = [...document.querySelectorAll('[role="dialog"]')].find(
    (d) => d.querySelector('[role="article"]')
  );
  const dialogHasComments = !!dialog;
  if (targetPostId && !matchedRoot && !dialogHasComments) {
    // Same fail-closed rule as EXTRACT_POST_PAGE_JS: don't attach media
    // from an unrelated article to this post.
    return { images: [], videos: [] };
  }
  const postRoot =
    matchedRoot ||
    (targetPostId && dialogHasComments ? dialog : null) ||
    document.querySelector('[role="article"]') ||
    document.querySelector('div[data-pagelet*="FeedUnit"]') ||
    document.body;
  const pageUrl = location.href;
  const groupId = (pageUrl.match(/\\/groups\\/(\\d+)/) || [])[1] || '';

  function extractPostNeedles(url) {
    const needles = [];
    const u = url || '';
    let m = u.match(/\\/(?:posts|permalink)\\/(pfbid[^/?#]+)/i);
    if (m) needles.push(m[1]);
    m = u.match(/\\/(?:posts|permalink)\\/(\\d+)/);
    if (m) needles.push(m[1]);
    m = u.match(/\\/groups\\/\\d+\\/(?:posts|permalink)\\/(\\d+)/);
    if (m) needles.push(m[1]);
    m = u.match(/[?&](?:story_fbid|fbid)=(\\d+)/i);
    if (m) needles.push(m[1]);
    return [...new Set(needles)];
  }

  const postNeedles = extractPostNeedles(pageUrl);

  function scriptMatchesPost(text) {
    if (!postNeedles.length) return false;
    return postNeedles.some((needle) => text.includes(needle));
  }

  const images = [];
  const videos = [];
  const seenImg = new Set();
  const seenVid = new Set();

  function unescapeFb(raw) {
    if (!raw) return '';
    let s = String(raw);
    s = s.replace(/\\\\u([0-9a-fA-F]{4})/g, (_, hex) => String.fromCharCode(parseInt(hex, 16)));
    s = s.split('\\\\/').join('/');
    s = s.split('\\/').join('/');
    s = s.split('\\u0025').join('%');
    s = s.split('\\u0026').join('&');
    return s.replace(/&amp;/g, '&').trim();
  }

  function parseImageScore(url) {
    const cstp = (url || '').match(/cstp=mx(\\d+)x(\\d+)/i);
    if (cstp) return parseInt(cstp[1], 10) * parseInt(cstp[2], 10);
    const ctp = (url || '').match(/ctp=s(\\d+)x(\\d+)/i);
    if (ctp) return parseInt(ctp[1], 10) * parseInt(ctp[2], 10);
    return 500;
  }

  function isThumbnailUrl(url) {
    const ctp = (url || '').match(/ctp=s(\\d+)x(\\d+)/i);
    if (ctp) {
      const w = parseInt(ctp[1], 10);
      const h = parseInt(ctp[2], 10);
      if (w < 200 || h < 200) return true;
    }
    if (/t39\\.30808-1\\//.test(url) && /ctp=s(?:48|64|80|100|110)/i.test(url)) return true;
    return false;
  }

  function isPostImageUrl(url) {
    const u = unescapeFb(url);
    if (!u || u.startsWith('data:')) return false;
    if (/emoji|static_map|safe_image|profile|avatar|reaction|sticker|rsrc\\.php|\\.wasm|static\\.xx\\.fbcdn/i.test(u)) {
      return false;
    }
    // t39.1997-6 is Facebook's dedicated sticker-pack CDN bucket (as opposed
    // to t39.30808-6 for regular uploaded photos) — these URLs don't always
    // contain the literal word "sticker", and reaction/comment stickers are
    // also picked up via the script-JSON scan below, which isn't scoped to
    // postRoot so the DOM-based comment exclusion can't catch them.
    if (/\\/t39\\.1997-/i.test(u)) {
      return false;
    }
    if (!/scontent.*fbcdn|external.*fbcdn/i.test(u)) return false;
    if (isThumbnailUrl(u)) return false;
    return /\\.(jpe?g|png|webp|gif)(\\?|$)/i.test(u) || /\\/v\\/t39\\./i.test(u);
  }

  function photoKey(url) {
    const m = (url || '').match(/\\/\\d+_\\d+_\\d+_n\\./);
    return m ? m[0] : url.split('?')[0];
  }

  function addImage(url) {
    const u = unescapeFb(url);
    if (!isPostImageUrl(u)) return;
    const key = photoKey(u);
    if (seenImg.has(key)) return;
    seenImg.add(key);
    images.push(u);
  }

  function addVideo(url) {
    const u = unescapeFb(url);
    if (!u || u.startsWith('blob:') || u.startsWith('data:')) return;
    const key = u.split('#')[0];
    if (seenVid.has(key)) return;
    seenVid.add(key);
    videos.push(u);
  }

  function isVideoLink(url) {
    if (!url || !/facebook\\.com/i.test(url)) return false;
    if (/\\/groups\\/[^/]+\\/posts\\//i.test(url)) return false;
    return /\\/videos\\/|\\/watch\\/?\\?|\\/reels?\\/|\\/share\\/r\\//i.test(url);
  }

  function isDirectMp4(url) {
    return /\\.mp4(\\?|$)|mime=video|video\\/mp4/i.test(url || '');
  }

  // postRoot ([role="article"]) usually wraps the whole post AND its
  // comments thread on a permalink page, so scanning it for <img> also picks
  // up commenters' avatars/reply stickers — walk up to the nearest
  // comment/reply container (same aria-label wording parseCommentLabel
  // matches) and skip anything found inside one.
  function isInsideComment(el) {
    let node = el;
    for (let i = 0; i < 20 && node; i++) {
      const label = node.getAttribute ? node.getAttribute('aria-label') || '' : '';
      if (/bình luận dưới tên|phản hồi (bình luận|của)|comment by|reply by/i.test(label)) {
        return true;
      }
      node = node.parentElement;
    }
    return false;
  }

  const scope = postRoot;
  scope.querySelectorAll('img[src], img[srcset]').forEach((img) => {
    if (isInsideComment(img)) return;
    const src = img.src || img.getAttribute('src') || '';
    const w = img.naturalWidth || img.width || 0;
    const h = img.naturalHeight || img.height || 0;
    if (src && !(w > 0 && w < 48 && h > 0 && h < 48)) addImage(src);
    (img.getAttribute('srcset') || '').split(',').forEach((part) => {
      addImage((part.trim().split(/\\s+/)[0] || '').trim());
    });
  });

  scope.querySelectorAll('a[href]').forEach((a) => {
    if (isInsideComment(a)) return;
    const href = (a.href || '').split('#')[0];
    if (/photo\\.php|fbid=|\\/photos\\/|\\/photo\\//i.test(href)) addImage(href);
    if (isVideoLink(href)) addVideo(href);
  });

  scope.querySelectorAll('[style*="background-image"]').forEach((el) => {
    if (isInsideComment(el)) return;
    const style = el.getAttribute('style') || '';
    const m = style.match(/background-image:\\s*url\\(["']?([^"')]+)/i);
    if (m) addImage(m[1]);
  });

  const imageCandidates = [];

  scope.querySelectorAll('video, video source[src]').forEach((el) => {
    if (isInsideComment(el)) return;
    const src = el.src || el.getAttribute('src') || '';
    if (isDirectMp4(src) || /scontent|fbcdn/i.test(src)) addVideo(src);
  });

  const videoIds = new Set();
  document.querySelectorAll('script').forEach((script) => {
    const text = script.textContent || '';
    if (text.length > 800000) return;
    if (!scriptMatchesPost(text)) return;

    if (/scontent|fbcdn|photo|image|uri/i.test(text)) {
      const imageKeys = [
        'image_uri',
        'viewer_image',
        'full_image',
        'photo_image',
        'thumbnailImage',
        'uri',
      ];
      for (const key of imageKeys) {
        const mk = '"' + key + '":"';
        let p = 0;
        for (let g = 0; g < 40; g++) {
          const idx = text.indexOf(mk, p);
          if (idx < 0) break;
          let i = idx + mk.length;
          let raw = '';
          while (i < text.length && raw.length < 3000) {
            const ch = text[i];
            if (ch === '"' && text.charCodeAt(i - 1) !== 92) break;
            raw += ch;
            i++;
          }
          const u = unescapeFb(raw);
          if (isPostImageUrl(u)) {
            imageCandidates.push({ url: u, score: parseImageScore(u) });
          }
          p = i + 1;
        }
      }
    }

    if (!/video|permalink_url|playable|browser_native/i.test(text)) return;

    const marker = '"permalink_url":"';
    let pos = 0;
    for (let g = 0; g < 30; g++) {
      const idx = text.indexOf(marker, pos);
      if (idx < 0) break;
      let i = idx + marker.length;
      let raw = '';
      while (i < text.length && raw.length < 2000) {
        const ch = text[i];
        if (ch === '"' && text.charCodeAt(i - 1) !== 92) break;
        raw += ch;
        i++;
      }
      const u = unescapeFb(raw);
      if (isVideoLink(u)) addVideo(u);
      pos = i + 1;
    }

    for (const key of ['browser_native_hd_url', 'browser_native_sd_url', 'playable_url', 'progressive_url']) {
      const mk = '"' + key + '":"';
      let p = 0;
      for (let g = 0; g < 10; g++) {
        const idx = text.indexOf(mk, p);
        if (idx < 0) break;
        let i = idx + mk.length;
        let raw = '';
        while (i < text.length && raw.length < 2000) {
          const ch = text[i];
          if (ch === '"' && text.charCodeAt(i - 1) !== 92) break;
          raw += ch;
          i++;
        }
        const u = unescapeFb(raw);
        if (isDirectMp4(u) || /scontent|fbcdn/i.test(u)) addVideo(u);
        p = i + 1;
      }
    }

    const vidRe = /"video_id":"(\\d{8,})"/g;
    let m;
    while ((m = vidRe.exec(text))) videoIds.add(m[1]);
  });

  videoIds.forEach((vid) => addVideo('https://www.facebook.com/watch/?v=' + vid));

  imageCandidates.sort((a, b) => b.score - a.score);
  const pickedPhotos = new Set();
  for (const candidate of imageCandidates) {
    const pk = photoKey(candidate.url);
    if (pickedPhotos.has(pk)) continue;
    pickedPhotos.add(pk);
    addImage(candidate.url);
  }

  return { images, videos };
}
"""

MAX_HOVER_COMMENT_TIMES = 30  # bound per-post hover overhead


async def hydrate_precise_comment_times(page, comments: list[dict]) -> None:
    """Best-effort: replace each comment dict's relative time text (e.g.
    "17 tuần") with Facebook's precise hover-tooltip timestamp text, when
    available. Mutates `comments` (the raw JS-returned list, pre-parsing) in
    place; a comment is left with its original relative text — parsed as an
    approximation by parse_relative_time same as before — if its DOM element
    or tooltip can't be located, so this never raises or drops a comment."""
    for item in comments[:MAX_HOVER_COMMENT_TIMES]:
        author = (item.get("author") or "").strip()
        time_text = (item.get("time") or "").strip()
        if not author or not time_text:
            continue
        try:
            handle = await page.evaluate_handle(
                """([author, timeText]) => {
                    const el = Array.from(document.querySelectorAll('[aria-label]')).find((e) => {
                        const label = e.getAttribute('aria-label') || '';
                        return label.includes(author) && label.includes(timeText);
                    });
                    if (!el) return null;
                    return Array.from(el.querySelectorAll('a')).find((a) => {
                        const t = (a.innerText || '').trim();
                        return t.length > 0 && t.length < 15 && /\\d/.test(t);
                    }) || null;
                }""",
                [author, time_text],
            )
            el = handle.as_element()
            if el is None:
                continue
            await el.hover(timeout=2000)
            await page.wait_for_timeout(700)
            tooltip_text = await page.evaluate(
                """() => {
                    const tip = document.querySelector('[role="tooltip"]');
                    return tip ? (tip.innerText || '').trim() : null;
                }"""
            )
            if tooltip_text:
                item["time"] = tooltip_text
        except Exception:
            continue


def build_post_from_page_data(
    data: dict,
    *,
    fallback_url: str,
    crawled_at: datetime | None = None,
) -> Post | None:
    crawl_time = crawled_at or datetime.now(timezone.utc)
    url = data.get("url") or fallback_url
    group_id = data.get("groupId") or extract_group_id(url) or ""
    page_id = data.get("pageId") or extract_page_id(url) or extract_page_id(fallback_url) or None
    source_type = "page" if page_id and not group_id else "group"
    owner_id = group_id or page_id or "unknown"
    post_id = extract_post_id(url) or extract_post_id(fallback_url)
    if not post_id:
        post_id = _stable_id(owner_id, data.get("topic", ""), data.get("author", ""))

    topic = (data.get("topic") or "").strip()
    content = (data.get("content") or "").strip()
    author = (data.get("author") or "").strip()
    raw_author_id = data.get("authorId") or data.get("author_id")
    author_id = str(raw_author_id).strip() if raw_author_id else None
    if not author_id:
        author_id = extract_user_id(data.get("authorProfileUrl") or "")

    if not topic and not content:
        return None

    if not topic:
        lines = content.split("\n", 1)
        topic = lines[0]
        content = lines[1] if len(lines) > 1 else ""

    engagement = engagement_from_dict(data.get("engagement"))
    if not engagement.reaction_count and not engagement.like_count:
        engagement = parse_engagement((data.get("pageTextSnippet") or "")[:3000])
    comments = parse_comments_structured(data.get("comments") or [], now=crawl_time)
    engagement = resolve_crawled_post_engagement(
        engagement,
        parsed_comment_count=len(comments),
    )

    published_at = None
    published_unix = data.get("publishedUnix")
    if published_unix:
        try:
            published_at = datetime.fromtimestamp(int(published_unix), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            published_at = None
    published_time = (data.get("publishedTime") or "").strip()
    if not published_at and published_time:
        published_at = parse_relative_time(published_time, now=crawl_time)

    is_edited = bool(data.get("isEdited"))
    edited_at = None
    edited_time = (data.get("editedTime") or "").strip()
    if edited_time:
        edited_at = parse_relative_time(edited_time, now=crawl_time)

    images = [str(u).strip() for u in (data.get("images") or []) if u]
    videos = [str(u).strip() for u in (data.get("videos") or []) if u]

    return Post(
        post_id=post_id,
        group_id=group_id or (page_id or "unknown"),
        page_id=page_id,
        source_type=source_type,
        url=url.split("?")[0],
        author=author,
        author_id=author_id or None,
        topic=topic,
        content=content,
        published_at=published_at,
        edited_at=edited_at,
        is_edited=is_edited,
        images=images,
        videos=videos,
        engagement=engagement,
        comments=comments,
    )
