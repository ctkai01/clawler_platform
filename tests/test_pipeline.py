from __future__ import annotations

import json

import httpx
import pytest

from platform_app.db.pool import get_pool
from platform_app.pipeline import classify as classify_module
from platform_app.pipeline.entity_match import run_entity_match
from platform_app.pipeline.keyword_filter import run_keyword_filter


@pytest.fixture
def target_id() -> int:
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "DELETE FROM documents WHERE target_id IN (SELECT id FROM crawl_targets WHERE url = %s)",
            ("https://forum.example.com/pipeline-test",),
        )
        conn.execute("DELETE FROM crawl_targets WHERE url = %s", ("https://forum.example.com/pipeline-test",))
        row = conn.execute(
            """
            INSERT INTO crawl_targets (platform_type, url, enabled) VALUES ('forum', 'https://forum.example.com/pipeline-test', false)
            RETURNING id
            """
        ).fetchone()
    return row["id"]


def _insert_document(target_id: int, external_doc_id: str, topic: str, content: str) -> int:
    pool = get_pool()
    with pool.connection() as conn:
        row = conn.execute(
            """
            INSERT INTO documents (target_id, platform_type, source_type, external_doc_id, url, topic, content, content_hash)
            VALUES (%s, 'forum', 'forum_thread', %s, %s, %s, %s, %s)
            ON CONFLICT (platform_type, external_doc_id) DO UPDATE SET topic = EXCLUDED.topic, content = EXCLUDED.content
            RETURNING id
            """,
            (target_id, external_doc_id, f"https://forum.example.com/{external_doc_id}", topic, content, external_doc_id),
        ).fetchone()
    return row["id"]


def test_keyword_filter_matches_and_skips(target_id: int) -> None:
    matched_id = _insert_document(target_id, "kw-match-1", "Đánh giá Mobifone", "Sóng Mobifone chỗ tôi rất yếu")
    skip_id = _insert_document(target_id, "kw-skip-1", "Chuyện phiếm", "Hôm nay trời đẹp quá")

    result = run_keyword_filter(document_ids=[matched_id, skip_id])
    assert result["matched"] == 1
    assert result["no_match"] == 1

    pool = get_pool()
    with pool.connection() as conn:
        matched_row = conn.execute(
            "SELECT keyword_status, matched_keywords FROM documents WHERE id = %s", (matched_id,)
        ).fetchone()
        skip_row = conn.execute("SELECT keyword_status FROM documents WHERE id = %s", (skip_id,)).fetchone()

    assert matched_row["keyword_status"] == "matched"
    assert "mobifone" in matched_row["matched_keywords"]
    assert skip_row["keyword_status"] == "no_match"


def test_entity_match_tags_and_sentinels_no_match(target_id: int) -> None:
    tagged_id = _insert_document(target_id, "em-match-1", "So sánh nhà mạng", "Viettel và Mobifone ai mạnh hơn")
    none_id = _insert_document(target_id, "em-none-1", "Ăn uống", "Món phở này ngon quá")
    doc_ids = [tagged_id, none_id]

    result = run_entity_match(document_ids=doc_ids)
    # >= 2 not == 2: the gazetteer has many surface-form variants per company
    # (imported from opencrawler), so a real match can hit more than one
    # concept_id for the same company.
    assert result["tagged"] >= 2

    pool = get_pool()
    with pool.connection() as conn:
        # canonical_name, not concept_id: the gazetteer's concept_id scheme
        # is whatever the imported source data uses (opencrawler CSVs use
        # e.g. "telco:ent:mobifone_*", one per surface-form variant) — the
        # stable, source-independent signal is the canonical display name.
        tagged_names = {
            r["canonical_name"]
            for r in conn.execute(
                "SELECT canonical_name FROM document_entities WHERE document_id = %s", (tagged_id,)
            ).fetchall()
        }
        none_concepts = {
            r["concept_id"]
            for r in conn.execute(
                "SELECT concept_id FROM document_entities WHERE document_id = %s", (none_id,)
            ).fetchall()
        }

    assert {"Viettel", "MobiFone"} <= tagged_names
    assert none_concepts == {"__none__"}

    # Second run must not re-scan already-checked documents (no duplicate rows).
    run_entity_match(document_ids=doc_ids)
    with pool.connection() as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM document_entities WHERE document_id = %s", (none_id,)
        ).fetchone()["n"]
    assert count == 1


def test_classify_skips_when_no_api_key(monkeypatch: pytest.MonkeyPatch, target_id: int) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = classify_module.run_classify(mode="llm_text")
    assert result.get("skipped_no_key") is True


def test_classify_calls_openai_and_stores_result(monkeypatch: pytest.MonkeyPatch, target_id: int) -> None:
    doc_id = _insert_document(target_id, "cls-1", "Khiếu nại Mobifone", "Tổng đài Mobifone không ai nghe máy")
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE documents SET keyword_status = 'matched', classification_status = 'pending' WHERE id = %s",
            (doc_id,),
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "category": "khieu_nai",
                                "sentiment": "negative",
                                "severity": 2,
                                "reasoning": "Khách hàng phàn nàn tổng đài",
                            }
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }
        return httpx.Response(200, json=payload, request=request)

    real_post = httpx.post

    def fake_post(url, **kwargs):
        if url == classify_module.OPENAI_API_URL:
            request = httpx.Request("POST", url)
            return handler(request)
        return real_post(url, **kwargs)

    monkeypatch.setattr(httpx, "post", fake_post)

    result = classify_module.run_classify(document_ids=[doc_id], mode="llm_text")
    assert result["completed"] == 1

    with pool.connection() as conn:
        row = conn.execute(
            "SELECT classification_status, classification_category, classification_sentiment, "
            "classification_severity, classification_cost_usd FROM documents WHERE id = %s",
            (doc_id,),
        ).fetchone()
    assert row["classification_status"] == "completed"
    assert row["classification_category"] == "khieu_nai"
    assert row["classification_sentiment"] == "negative"
    assert row["classification_severity"] == 2
    assert row["classification_cost_usd"] > 0


def test_classify_normal_mode_is_rule_based_and_free(target_id: int) -> None:
    doc_id = _insert_document(target_id, "cls-normal-1", "Khiếu nại Mobifone", "Tổng đài Mobifone lừa đảo trừ tiền")
    pool = get_pool()
    with pool.connection() as conn:
        conn.execute(
            "UPDATE documents SET keyword_status = 'matched', classification_status = 'pending' WHERE id = %s",
            (doc_id,),
        )

    result = classify_module.run_classify(document_ids=[doc_id], mode="normal")
    assert result["completed"] == 1

    with pool.connection() as conn:
        row = conn.execute(
            "SELECT classification_category, classification_sentiment, classification_severity, classification_cost_usd "
            "FROM documents WHERE id = %s",
            (doc_id,),
        ).fetchone()
    assert row["classification_category"] == "khieu_nai"
    assert row["classification_sentiment"] == "negative"
    assert row["classification_severity"] == 2
    assert row["classification_cost_usd"] == 0
