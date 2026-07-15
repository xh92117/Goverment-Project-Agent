import json
import logging
from types import SimpleNamespace

from deerflow.community.hybrid_search import tools
from deerflow.community.hybrid_search.tools import web_fetch_tool, web_search_tool


def _config(extra: dict | None = None):
    return SimpleNamespace(get_tool_config=lambda _: SimpleNamespace(model_extra=extra or {}))


def test_hybrid_search_ranks_official_results_across_providers(monkeypatch) -> None:
    tools._SEARCH_CACHE.clear()
    monkeypatch.setattr(tools, "get_app_config", lambda: _config({"providers": ["ddgs", "simple_web"]}))

    def fake_run_provider(provider, query, *, max_results, official_domains, extra):
        if provider == "ddgs":
            return [
                {
                    "title": "Repost",
                    "url": "https://mirror.example.com/notice",
                    "content": "guide",
                    "provider": "ddgs",
                    "domain": "mirror.example.com",
                    "source_type": "unknown",
                    "is_official": False,
                    "score": 1,
                }
            ], {"provider": "ddgs", "result_count": 1}
        return [
            {
                "title": "Official",
                "url": "https://www.gov.cn/notice",
                "content": "guide",
                "provider": "simple_web",
                "domain": "gov.cn",
                "source_type": "official",
                "is_official": True,
                "score": 100,
            }
        ], {"provider": "simple_web", "result_count": 1}

    monkeypatch.setattr(tools, "_run_provider", fake_run_provider)

    data = json.loads(web_search_tool.invoke({"query": "project guide", "max_results": 2}))

    assert data["providers"] == ["ddgs", "simple_web"]
    assert data["results"][0]["url"] == "https://www.gov.cn/notice"
    assert data["results"][0]["is_official"] is True
    assert data["total_results"] == 2


def test_hybrid_search_does_not_promote_unrelated_official_results(monkeypatch) -> None:
    tools._SEARCH_CACHE.clear()
    monkeypatch.setattr(tools, "get_app_config", lambda: _config({"providers": ["ddgs"]}))

    def fake_run_provider(provider, query, *, max_results, official_domains, extra):
        return [
            {
                "title": "增值电信业务经营许可证",
                "url": "https://beian.miit.gov.cn",
                "content": "ICP备案 查询",
                "provider": provider,
                "domain": "miit.gov.cn",
                "source_type": "official",
                "is_official": True,
                "score": 100,
            },
            {
                "title": "隧道衬砌冷缝无损检测技术研究",
                "url": "https://journal.example.com/tunnel-cold-joint",
                "content": "隧道 衬砌 冷缝 无损检测 地质雷达 超声",
                "provider": provider,
                "domain": "journal.example.com",
                "source_type": "unknown",
                "is_official": False,
                "score": 20,
            },
        ], {"provider": provider, "result_count": 2}

    monkeypatch.setattr(tools, "_run_provider", fake_run_provider)

    data = json.loads(web_search_tool.invoke({"query": "隧道 衬砌 冷缝 无损检测", "max_results": 2}))

    assert data["results"][0]["title"] == "隧道衬砌冷缝无损检测技术研究"


def test_hybrid_search_skips_serper_without_key(monkeypatch) -> None:
    tools._SEARCH_CACHE.clear()
    monkeypatch.setattr(tools, "get_app_config", lambda: _config({"providers": ["serper"]}))
    monkeypatch.delenv("SERPER_API_KEY", raising=False)

    data = json.loads(web_search_tool.invoke({"query": "policy"}))

    assert data["error"] == "No results found"
    assert data["diagnostics"][0]["provider"] == "serper"
    assert data["diagnostics"][0]["skipped"] is True


def test_hybrid_search_caches_successful_results(monkeypatch) -> None:
    tools._SEARCH_CACHE.clear()
    monkeypatch.setattr(tools, "get_app_config", lambda: _config({"providers": ["ddgs"], "cache_ttl_seconds": 60}))
    calls = 0

    def fake_run_provider(provider, query, *, max_results, official_domains, extra):
        nonlocal calls
        calls += 1
        return [
            {
                "title": "Official",
                "url": "https://www.gov.cn/notice",
                "content": "guide",
                "provider": provider,
                "domain": "gov.cn",
                "source_type": "official",
                "is_official": True,
                "score": 100,
            }
        ], {"provider": provider, "result_count": 1}

    monkeypatch.setattr(tools, "_run_provider", fake_run_provider)

    first = json.loads(web_search_tool.invoke({"query": "policy"}))
    second = json.loads(web_search_tool.invoke({"query": "policy"}))

    assert calls == 1
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True


def test_hybrid_search_writes_audit_log(monkeypatch, caplog) -> None:
    tools._SEARCH_CACHE.clear()
    monkeypatch.setattr(tools, "get_app_config", lambda: _config({"providers": ["ddgs"], "cache_enabled": False}))
    monkeypatch.setattr(
        tools,
        "_run_provider",
        lambda provider, query, *, max_results, official_domains, extra: (
            [
                {
                    "title": "Official",
                    "url": "https://www.gov.cn/notice",
                    "content": "guide",
                    "provider": provider,
                    "domain": "gov.cn",
                    "source_type": "official",
                    "is_official": True,
                    "score": 100,
                }
            ],
            {"provider": provider, "result_count": 1},
        ),
    )

    with caplog.at_level(logging.INFO, logger="deerflow.community.hybrid_search.tools"):
        web_search_tool.invoke({"query": "policy"})

    audit_records = [record for record in caplog.records if "hybrid_search audit" in record.message]
    assert len(audit_records) == 1
    audit = json.loads(audit_records[0].message.split("hybrid_search audit ", 1)[1])
    assert audit["query"] == "policy"
    assert audit["total_results"] == 1
    assert audit["official_results"] == 1
    assert audit["cache_hit"] is False
    assert audit["provider_status"][0]["provider"] == "ddgs"


def test_hybrid_search_decorates_ddgs_results(monkeypatch) -> None:
    monkeypatch.setattr(
        "deerflow.community.ddg_search.tools._search_text",
        lambda **kwargs: [{"title": "Guide", "href": "https://www.gov.cn/a.pdf", "body": "notice"}],
    )

    results, diagnostic = tools._search_ddgs(
        "guide",
        max_results=5,
        official_domains=["gov.cn"],
        extra={"backend": "duckduckgo"},
    )

    assert diagnostic["provider"] == "ddgs"
    assert results[0]["provider"] == "ddgs"
    assert results[0]["source_type"] == "official_document"
    assert results[0]["is_official"] is True


def test_hybrid_web_fetch_falls_back_to_direct(monkeypatch) -> None:
    monkeypatch.setattr(tools, "get_app_config", lambda: _config({"providers": ["jina_reader", "direct"]}))
    monkeypatch.setattr(tools, "_fetch_jina_reader", lambda url, max_chars: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(tools, "_fetch_direct", lambda url, max_chars, extra: "direct content")

    assert web_fetch_tool.invoke({"url": "https://example.com"}) == "direct content"
