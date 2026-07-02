from __future__ import annotations

import json

import httpx
import pytest

from platform_app.parsers.generic_css import GenericCssParser
from platform_app.parsers.sites.discourse_json import DiscourseJsonParser


_RealAsyncClient = httpx.AsyncClient


def _mock_client_factory(responses: dict[str, httpx.Response]):
    def handler(request: httpx.Request) -> httpx.Response:
        return responses[str(request.url)]

    def factory(*args, **kwargs):
        kwargs.pop("follow_redirects", None)
        kwargs.pop("timeout", None)
        return _RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)

    return factory


@pytest.mark.asyncio
async def test_generic_css_discover_and_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    listing_html = """
    <html><body>
        <a class="thread-link" href="/t/hello-world">Hello</a>
        <a class="thread-link" href="/t/second-post">Second</a>
    </body></html>
    """
    thread_html = """
    <html><body>
        <h1 class="thread-title">Hello World</h1>
        <span class="post-author">alice</span>
        <time class="post-date" datetime="2026-01-15T10:00:00Z"></time>
        <div class="post-content">Nội dung bài viết đầu tiên</div>
        <div class="comment"><span class="comment-author">bob</span><p class="comment-text">Bình luận 1</p></div>
        <div class="comment"><span class="comment-author">carol</span><p class="comment-text">Bình luận 2</p></div>
    </body></html>
    """
    responses = {
        "https://forum.example.com/board": httpx.Response(200, text=listing_html),
        "https://forum.example.com/t/hello-world": httpx.Response(200, text=thread_html),
    }
    monkeypatch.setattr(httpx, "AsyncClient", _mock_client_factory(responses))

    parser = GenericCssParser()
    config = {
        "list_selector": "a.thread-link",
        "title_selector": "h1.thread-title",
        "author_selector": ".post-author",
        "content_selector": ".post-content",
        "date_selector": "time.post-date",
        "date_attr": "datetime",
        "comment_selector": ".comment",
        "comment_author_selector": ".comment-author",
        "comment_text_selector": ".comment-text",
    }

    urls = await parser.discover_urls("https://forum.example.com/board", config)
    assert urls == [
        "https://forum.example.com/t/hello-world",
        "https://forum.example.com/t/second-post",
    ]

    doc = await parser.fetch_and_parse(urls[0], config)
    assert doc is not None
    assert doc.external_doc_id == "forum.example.com:/t/hello-world"
    assert doc.topic == "Hello World"
    assert doc.author == "alice"
    assert doc.content == "Nội dung bài viết đầu tiên"
    assert doc.published_at is not None and doc.published_at.year == 2026
    assert [c.text for c in doc.comments] == ["Bình luận 1", "Bình luận 2"]
    assert [c.author for c in doc.comments] == ["bob", "carol"]


@pytest.mark.asyncio
async def test_discourse_json_discover_and_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    listing = {
        "topic_list": {
            "topics": [
                {"id": 42, "slug": "welcome-to-the-forum"},
                {"id": 43, "slug": "second-topic"},
            ]
        }
    }
    topic_detail = {
        "id": 42,
        "title": "Welcome to the forum",
        "post_stream": {
            "posts": [
                {
                    "id": 100,
                    "post_number": 1,
                    "username": "alice",
                    "cooked": "<p>Bài viết gốc</p>",
                    "created_at": "2026-02-01T08:00:00.000Z",
                },
                {
                    "id": 101,
                    "post_number": 2,
                    "username": "bob",
                    "cooked": "<p>Trả lời bài gốc</p>",
                    "created_at": "2026-02-01T09:00:00.000Z",
                    "reply_to_post_number": 1,
                },
            ]
        },
    }
    responses = {
        "https://discuss.example.com/latest.json": httpx.Response(200, json=listing),
        "https://discuss.example.com/t/welcome-to-the-forum/42.json": httpx.Response(200, json=topic_detail),
    }
    monkeypatch.setattr(httpx, "AsyncClient", _mock_client_factory(responses))

    parser = DiscourseJsonParser()
    urls = await parser.discover_urls("https://discuss.example.com", {})
    assert urls == [
        "https://discuss.example.com/t/welcome-to-the-forum/42.json",
        "https://discuss.example.com/t/second-topic/43.json",
    ]

    doc = await parser.fetch_and_parse(urls[0], {})
    assert doc is not None
    assert doc.external_doc_id == "discuss.example.com:topic:42"
    assert doc.url == "https://discuss.example.com/t/welcome-to-the-forum/42"
    assert doc.topic == "Welcome to the forum"
    assert doc.author == "alice"
    assert doc.content == "Bài viết gốc"
    assert len(doc.comments) == 1
    assert doc.comments[0].external_comment_id == "discuss.example.com:post:101"
    assert doc.comments[0].parent_comment_id == "discuss.example.com:post:100"
    assert json.loads(json.dumps(doc.extra)) == {}
