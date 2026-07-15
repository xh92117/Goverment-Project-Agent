import json
from types import SimpleNamespace

from deerflow.community.simple_web import tools
from deerflow.community.simple_web.tools import web_extract_tool, web_search_tool


def _field(data: dict, name: str) -> dict:
    return next(item for item in data["fields"] if item["name"] == name)


def test_simple_web_search_embeds_multi_search_engine_templates() -> None:
    assert set(tools._SEARCH_ENGINES) == {
        "baidu",
        "bing_cn",
        "bing_int",
        "360",
        "sogou",
        "wechat",
        "toutiao",
        "jisilu",
        "google",
        "google_hk",
        "duckduckgo",
        "yahoo",
        "startpage",
        "brave",
        "ecosia",
        "qwant",
        "wolframalpha",
    }
    assert tools._search_url("baidu", "国家自然科学基金") == (
        "https://www.baidu.com/s?wd=%E5%9B%BD%E5%AE%B6%E8%87%AA%E7%84%B6%E7%A7%91%E5%AD%A6%E5%9F%BA%E9%87%91"
    )
    assert tools._normalize_engine("bing") == "bing_cn"
    assert tools._normalize_engine("google-hk") == "google_hk"
    assert tools._normalize_engine("ddg") == "duckduckgo"
    assert tools._search_url("duckduckgo", "privacy tools") == "https://duckduckgo.com/html/?q=privacy%20tools"


def test_simple_web_search_unwraps_search_redirect_urls() -> None:
    assert tools._normalize_result_url("/url?q=https%3A%2F%2Fexample.gov.cn%2Fnotice.html&sa=U") == "https://example.gov.cn/notice.html"
    assert tools._normalize_result_url("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fguide.pdf") == "https://example.com/guide.pdf"


def test_simple_web_query_terms_and_rewrite_improve_chinese_relevance() -> None:
    query = "\u52a8\u6001\u56de\u5f39\u6a21\u578b\u68c0\u6d4b\u6280\u672f\u73b0\u72b6"
    terms = tools._query_terms(query)

    assert "\u52a8\u6001\u56de\u5f39" in terms
    assert "\u68c0\u6d4b" in terms
    assert tools._augment_query(query).endswith("\u52a8\u6001\u56de\u5f39\u6a21\u91cf")


def test_simple_web_scoring_penalizes_unrelated_documents() -> None:
    query = "\u52a8\u6001\u56de\u5f39\u6a21\u578b\u68c0\u6d4b\u6280\u672f\u73b0\u72b6"
    relevant = {
        "title": "\u8def\u57fa\u52a8\u6001\u56de\u5f39\u6a21\u91cf\u65e0\u635f\u68c0\u6d4b\u6280\u672f",
        "url": "https://zgglxb.chd.edu.cn/article",
        "content": "\u52a8\u6001\u56de\u5f39\u6a21\u91cf \u68c0\u6d4b \u6280\u672f",
    }
    unrelated_pdf = {
        "title": "\u4eba\u5de5\u667a\u80fd\u9a71\u52a8\u4e0b\u5f39\u8f7d\u63a2\u6d4b\u6280\u672f",
        "url": "https://spacejournal.cn/article.pdf",
        "content": "\u590d\u6742\u7535\u78c1\u73af\u5883 \u63a2\u6d4b",
    }

    assert tools._result_score(relevant, ["gov.cn"], query) > tools._result_score(unrelated_pdf, ["gov.cn"], query)


def test_simple_web_ranking_does_not_promote_unrelated_official_results() -> None:
    results = [
        {
            "title": "增值电信业务经营许可证",
            "url": "https://beian.miit.gov.cn",
            "content": "ICP备案 查询",
            "domain": "miit.gov.cn",
            "source_type": "official",
            "is_official": True,
            "score": 100,
        },
        {
            "title": "隧道衬砌冷缝无损检测技术研究",
            "url": "https://journal.example.com/tunnel-cold-joint",
            "content": "隧道 衬砌 冷缝 无损检测 地质雷达 超声",
            "domain": "journal.example.com",
            "source_type": "unknown",
            "is_official": False,
            "score": 20,
        },
    ]

    ranked = tools._dedupe_and_rank_results(
        results,
        max_results=2,
        official_first=True,
        query="隧道 衬砌 冷缝 无损检测",
    )

    assert ranked[0]["title"] == "隧道衬砌冷缝无损检测技术研究"


def test_web_search_gateway_runs_multiple_engines_and_ranks_official_sources(monkeypatch) -> None:
    tools._SEARCH_CACHE.clear()
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(get_tool_config=lambda _: SimpleNamespace(model_extra={})),
    )

    def fake_search_engine_once(client, *, query, engine, max_results, official_domains):
        if engine == "baidu":
            return [
                {
                    "title": "Official guide",
                    "url": "https://www.most.gov.cn/example.html",
                    "content": "notice",
                    "engine": engine,
                    "engine_label": "Baidu",
                    "search_url": "https://example.test/baidu",
                    "domain": "most.gov.cn",
                    "source_type": "official",
                    "is_official": True,
                    "score": 100,
                }
            ], {"engine": engine, "search_url": "https://example.test/baidu", "result_count": 1}
        return [
            {
                "title": "Repost guide",
                "url": "https://mirror.example.com/example.html",
                "content": "notice",
                "engine": engine,
                "engine_label": "DuckDuckGo",
                "search_url": "https://example.test/ddg",
                "domain": "mirror.example.com",
                "source_type": "unknown",
                "is_official": False,
                "score": 1,
            }
        ], {"engine": engine, "search_url": "https://example.test/ddg", "result_count": 1}

    monkeypatch.setattr(tools, "_search_engine_once", fake_search_engine_once)

    result = web_search_tool.invoke(
        {
            "query": "key project guide",
            "engines": "duckduckgo,baidu",
            "site": "most.gov.cn",
            "filetype": "pdf",
            "time_range": "year",
            "max_results": 2,
        }
    )
    data = json.loads(result)

    assert data["engines"] == ["duckduckgo", "baidu"]
    assert data["effective_query"] == "key project guide site:most.gov.cn filetype:pdf past year"
    assert data["results"][0]["url"] == "https://www.most.gov.cn/example.html"
    assert data["results"][0]["is_official"] is True
    assert data["total_results"] == 2


def test_web_search_gateway_respects_explicit_single_engine_over_configured_defaults(monkeypatch) -> None:
    tools._SEARCH_CACHE.clear()
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(
            get_tool_config=lambda _: SimpleNamespace(
                model_extra={"engines": ["bing_cn", "baidu"], "official_first": True}
            )
        ),
    )

    called_engines = []

    def fake_search_engine_once(client, *, query, engine, max_results, official_domains):
        called_engines.append(engine)
        return [], {"engine": engine, "search_url": "https://example.test", "result_count": 0}

    monkeypatch.setattr(tools, "_search_engine_once", fake_search_engine_once)

    data = json.loads(web_search_tool.invoke({"query": "privacy", "engine": "duckduckgo"}))

    assert called_engines == ["duckduckgo"]
    assert data["engines"] == ["duckduckgo"]


def test_web_search_gateway_caches_successful_searches(monkeypatch) -> None:
    tools._SEARCH_CACHE.clear()
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(
            get_tool_config=lambda _: SimpleNamespace(
                model_extra={"cache_enabled": True, "cache_ttl_seconds": 60}
            )
        ),
    )

    call_count = 0

    def fake_search_engine_once(client, *, query, engine, max_results, official_domains):
        nonlocal call_count
        call_count += 1
        return [
            {
                "title": "Official guide",
                "url": "https://www.gov.cn/example.html",
                "content": "notice",
                "engine": engine,
                "engine_label": "Bing CN",
                "search_url": "https://example.test",
                "domain": "gov.cn",
                "source_type": "official",
                "is_official": True,
                "score": 100,
            }
        ], {"engine": engine, "search_url": "https://example.test", "result_count": 1}

    monkeypatch.setattr(tools, "_search_engine_once", fake_search_engine_once)

    first = json.loads(web_search_tool.invoke({"query": "policy guide"}))
    second = json.loads(web_search_tool.invoke({"query": "policy guide"}))

    assert call_count == 1
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert second["results"][0]["url"] == "https://www.gov.cn/example.html"


def test_web_extract_tool_extracts_fields_from_search_json() -> None:
    source = json.dumps(
        {
            "query": "2026 国家自然科学基金 面上项目 指南",
            "results": [
                {
                    "title": "2026年度国家自然科学基金项目指南",
                    "url": "https://www.nsfc.gov.cn/example.html",
                    "content": "面上项目资助强度为直接费用平均60万元/项，申请截止日期为2026年3月20日。",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = web_extract_tool.invoke(
        {
            "source": source,
            "fields": "资助强度,截止日期,链接",
            "query": "面上项目 资助强度 截止日期",
        }
    )
    data = json.loads(result)

    assert data["source_type"] == "json"
    assert "60万元" in _field(data, "资助强度")["candidates"][0]["value"]
    assert "2026年3月20日" in _field(data, "截止日期")["candidates"][0]["value"]
    assert _field(data, "链接")["candidates"][0]["value"] == "https://www.nsfc.gov.cn/example.html"


def test_web_extract_tool_extracts_fields_from_html_text() -> None:
    result = web_extract_tool.invoke(
        {
            "source": "<html><body><p>成都今日天气：多云，气温 24℃，湿度 68%。</p></body></html>",
            "fields": "天气,温度,湿度",
            "query": "成都 今日天气",
        }
    )
    data = json.loads(result)

    assert data["source_type"] == "text"
    assert _field(data, "天气")["candidates"][0]["value"] == "多云"
    assert _field(data, "温度")["candidates"][0]["value"] == "24℃"
    assert _field(data, "湿度")["candidates"][0]["value"] == "68%"
