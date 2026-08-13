"""Hybrid web search and fetch tools.

This module keeps the public tool names stable (`web_search`, `web_fetch`) but
routes calls through provider adapters, normalizes evidence fields, ranks
official sources, and falls back to dependency-light providers when paid APIs
or external services are unavailable.
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
from langchain.tools import tool

from deerflow.community.simple_web import tools as simple_web
from deerflow.config import get_app_config

logger = logging.getLogger(__name__)

_SERPER_ENDPOINT = "https://google.serper.dev/search"
_DEFAULT_PROVIDERS = ["serper", "ddgs", "simple_web"]
_DEFAULT_FETCH_PROVIDERS = ["jina_reader", "direct"]
_DEFAULT_CACHE_TTL_SECONDS = 900
_MAX_CACHE_ENTRIES = 256
_SEARCH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _config_extra(tool_name: str) -> dict[str, Any]:
    config = get_app_config().get_tool_config(tool_name)
    if config is None:
        return {}
    return dict(getattr(config, "model_extra", {}) or {})


def _coerce_bool(value: object, default: bool = False) -> bool:
    return simple_web._coerce_bool(value, default)


def _coerce_str_list(value: object, default: list[str] | None = None) -> list[str]:
    return simple_web._coerce_str_list(value, default)


def _cache_key(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _get_cached(key: str, ttl_seconds: int) -> dict[str, Any] | None:
    if ttl_seconds <= 0:
        return None
    cached = _SEARCH_CACHE.get(key)
    if cached is None:
        return None
    created_at, payload = cached
    if time.time() - created_at > ttl_seconds:
        _SEARCH_CACHE.pop(key, None)
        return None
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _put_cached(key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    if len(_SEARCH_CACHE) >= _MAX_CACHE_ENTRIES:
        oldest_key = min(_SEARCH_CACHE, key=lambda item: _SEARCH_CACHE[item][0])
        _SEARCH_CACHE.pop(oldest_key, None)
    _SEARCH_CACHE[key] = (time.time(), json.loads(json.dumps(payload, ensure_ascii=False)))


def _audit_search(payload: dict[str, Any], *, latency_ms: int, cache_hit: bool) -> None:
    results = payload.get("results")
    if not isinstance(results, list):
        results = []
    diagnostics = payload.get("diagnostics")
    if not isinstance(diagnostics, list):
        diagnostics = []
    provider_status = []
    for item in diagnostics:
        if isinstance(item, dict):
            provider_status.append(
                {
                    "provider": item.get("provider"),
                    "result_count": item.get("result_count", 0),
                    "skipped": bool(item.get("skipped", False)),
                    "error": item.get("error"),
                }
            )
    logger.info(
        "hybrid_search audit %s",
        json.dumps(
            {
                "query": payload.get("query"),
                "effective_query": payload.get("effective_query"),
                "providers": payload.get("providers"),
                "total_results": payload.get("total_results", 0),
                "official_results": sum(1 for result in results if isinstance(result, dict) and result.get("is_official")),
                "cache_hit": cache_hit,
                "latency_ms": latency_ms,
                "provider_status": provider_status,
            },
            ensure_ascii=False,
        ),
    )


def _serper_api_key(extra: dict[str, Any]) -> str | None:
    for key in ("serper_api_key", "api_key"):
        value = extra.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return os.getenv("SERPER_API_KEY")


def _decorate_result(
    *,
    title: str,
    url: str,
    content: str,
    provider: str,
    official_domains: list[str],
    query: str,
    engine: str = "",
    search_url: str = "",
) -> dict[str, Any] | None:
    normalized_url = simple_web._normalize_result_url(url)
    if not normalized_url:
        return None
    domain = simple_web._domain(normalized_url)
    source_type = simple_web._source_type(normalized_url, official_domains)
    base = {
        "title": title or "",
        "url": normalized_url,
        "content": content or "",
        "provider": provider,
        "engine": engine,
        "search_url": search_url,
        "domain": domain,
        "source_type": source_type,
        "is_official": source_type.startswith("official"),
    }
    base["score"] = simple_web._result_score(base, official_domains, query)
    return base


def _has_query_match(result: dict[str, Any], query: str) -> bool:
    terms = simple_web._query_terms(query)
    if not terms:
        return True
    combined = f"{result.get('title', '')} {result.get('content', '')}".lower()
    return any(term and term in combined for term in terms)


def _dedupe_and_rank(results: list[dict[str, Any]], max_results: int, official_first: bool, *, query: str = "") -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for result in results:
        url = str(result.get("url", "")).rstrip("/")
        if not url:
            continue
        existing = deduped.get(url)
        if existing is None or int(result.get("score", 0)) > int(existing.get("score", 0)):
            deduped[url] = result
    ranked = list(deduped.values())
    if official_first:
        ranked.sort(
            key=lambda item: (
                _has_query_match(item, query),
                bool(item.get("is_official")) and _has_query_match(item, query),
                int(item.get("score", 0)),
            ),
            reverse=True,
        )
    return ranked[:max_results]


def _search_serper(query: str, *, max_results: int, official_domains: list[str], extra: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = _serper_api_key(extra)
    if not api_key:
        return [], {"provider": "serper", "skipped": True, "reason": "SERPER_API_KEY is not configured"}

    payload = {"q": query, "num": max_results}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=float(extra.get("timeout", 30)), trust_env=_coerce_bool(extra.get("trust_env"), False)) as client:
            response = client.post(_SERPER_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("Serper search failed: %s", exc)
        return [], {"provider": "serper", "error": f"{type(exc).__name__}: {exc}"}

    results = []
    for item in data.get("organic", [])[:max_results]:
        decorated = _decorate_result(
            title=str(item.get("title", "")),
            url=str(item.get("link", "")),
            content=str(item.get("snippet", "")),
            provider="serper",
            official_domains=official_domains,
            query=query,
            search_url=_SERPER_ENDPOINT,
        )
        if decorated:
            results.append(decorated)
    return results, {"provider": "serper", "result_count": len(results)}


def _search_ddgs(query: str, *, max_results: int, official_domains: list[str], extra: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        from deerflow.community.ddg_search.tools import _search_text
    except Exception as exc:
        return [], {"provider": "ddgs", "error": f"import failed: {exc}"}

    backend = extra.get("ddgs_backend", extra.get("backend", "auto"))
    region = extra.get("ddgs_region", extra.get("region", "wt-wt"))
    safesearch = extra.get("ddgs_safesearch", extra.get("safesearch", "moderate"))
    raw_results = _search_text(
        query=query,
        max_results=max_results,
        region=region,
        safesearch=safesearch,
        backend=backend,
    )
    results = []
    for item in raw_results:
        decorated = _decorate_result(
            title=str(item.get("title", "")),
            url=str(item.get("href", item.get("link", ""))),
            content=str(item.get("body", item.get("snippet", ""))),
            provider="ddgs",
            official_domains=official_domains,
            query=query,
        )
        if decorated:
            results.append(decorated)
    return results, {"provider": "ddgs", "result_count": len(results), "backend": backend, "region": region}


def _search_simple_web(query: str, *, max_results: int, official_domains: list[str], extra: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    engines = simple_web._normalize_engines(extra.get("simple_web_engines", extra.get("engines", ["bing_cn"])), str(extra.get("engine", "bing_cn")))
    diagnostics: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        )
    }
    with httpx.Client(
        timeout=float(extra.get("timeout", 20)),
        follow_redirects=True,
        headers=headers,
        trust_env=_coerce_bool(extra.get("trust_env"), False),
        http2=False,
    ) as client:
        for engine in engines:
            engine_results, diagnostic = simple_web._search_engine_once(
                client,
                query=query,
                engine=engine,
                max_results=max_results,
                official_domains=official_domains,
            )
            for result in engine_results:
                result["provider"] = "simple_web"
            results.extend(engine_results)
            diagnostics.append(diagnostic)
    return results, {"provider": "simple_web", "result_count": len(results), "engines": engines, "diagnostics": diagnostics}


def _run_provider(provider: str, query: str, *, max_results: int, official_domains: list[str], extra: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if provider == "serper":
        return _search_serper(query, max_results=max_results, official_domains=official_domains, extra=extra)
    if provider == "ddgs":
        return _search_ddgs(query, max_results=max_results, official_domains=official_domains, extra=extra)
    if provider == "simple_web":
        return _search_simple_web(query, max_results=max_results, official_domains=official_domains, extra=extra)
    return [], {"provider": provider, "skipped": True, "reason": "unknown provider"}


@tool("web_search", parse_docstring=True)
def web_search_tool(
    query: str,
    max_results: int = 5,
    providers: str = "",
    site: str = "",
    filetype: str = "",
    time_range: str = "",
    official_first: bool = True,
) -> str:
    """Search the public web through multiple providers with normalized source ranking.

    Args:
        query: Search keywords. Use precise project, authority, year, and field terms.
        max_results: Maximum number of normalized results to return.
        providers: Optional comma-separated provider ids: serper, ddgs, simple_web.
        site: Optional domain for site-specific search, such as most.gov.cn.
        filetype: Optional file extension filter, such as pdf, doc, or xls.
        time_range: Optional recency hint, such as latest, day, week, month, or year.
        official_first: Whether to rank official government/project sources first.
    """
    extra = _config_extra("web_search")
    max_results = max(1, min(int(extra.get("max_results", max_results)), 10))
    provider_list = _coerce_str_list(providers or extra.get("providers"), _DEFAULT_PROVIDERS)
    official_domains = _coerce_str_list(extra.get("official_domains"), list(simple_web._DEFAULT_OFFICIAL_DOMAINS))
    official_first = _coerce_bool(extra.get("official_first"), official_first)
    cache_enabled = _coerce_bool(extra.get("cache_enabled"), True)
    cache_ttl_seconds = int(extra.get("cache_ttl_seconds", _DEFAULT_CACHE_TTL_SECONDS)) if cache_enabled else 0
    effective_query = simple_web._augment_query(query, site=site, filetype=filetype, time_range=time_range)
    started_at = time.perf_counter()

    key = _cache_key(
        {
            "query": effective_query,
            "max_results": max_results,
            "providers": provider_list,
            "official_domains": official_domains,
            "official_first": official_first,
        }
    )
    cached = _get_cached(key, cache_ttl_seconds)
    if cached is not None:
        cached["cache_hit"] = True
        _audit_search(cached, latency_ms=int((time.perf_counter() - started_at) * 1000), cache_hit=True)
        return json.dumps(cached, ensure_ascii=False, indent=2)

    results: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(len(provider_list), 4) or 1) as executor:
        futures = [
            executor.submit(
                _run_provider,
                provider,
                effective_query,
                max_results=max_results,
                official_domains=official_domains,
                extra=extra,
            )
            for provider in provider_list
        ]
        for future in as_completed(futures):
            provider_results, diagnostic = future.result()
            results.extend(provider_results)
            diagnostics.append(diagnostic)

    ranked_results = _dedupe_and_rank(results, max_results, official_first, query=effective_query)
    payload = {
        "query": query,
        "effective_query": effective_query,
        "providers": provider_list,
        "available_providers": ["serper", "ddgs", "simple_web"],
        "total_results": len(ranked_results),
        "results": ranked_results,
        "diagnostics": diagnostics,
        "cache_hit": False,
    }
    if not ranked_results:
        payload["error"] = "No results found"
    else:
        _put_cached(key, payload, cache_ttl_seconds)
    _audit_search(payload, latency_ms=int((time.perf_counter() - started_at) * 1000), cache_hit=False)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _fetch_jina_reader(url: str, max_chars: int) -> str:
    return simple_web._fetch_readable_text(url, max_chars=max_chars, tool_name="web_fetch")


def _fetch_direct(url: str, max_chars: int, extra: dict[str, Any]) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        )
    }
    with httpx.Client(
        timeout=float(extra.get("timeout", 20)),
        follow_redirects=True,
        headers=headers,
        trust_env=_coerce_bool(extra.get("trust_env"), True),
        http2=False,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
    text = simple_web._clean_text(response.text)
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n[truncated]"
    return text


@tool("web_fetch", parse_docstring=True)
def web_fetch_tool(url: str, max_chars: int = 12000, providers: str = "") -> str:
    """Fetch readable text from an exact URL with provider fallback.

    Args:
        url: Exact HTTP or HTTPS URL to fetch.
        max_chars: Maximum characters to return.
        providers: Optional comma-separated fetch provider ids: jina_reader, direct.
    """
    if not simple_web._valid_http_url(url):
        return "Invalid URL: web_fetch only accepts http(s) URLs."

    extra = _config_extra("web_fetch")
    max_chars = max(500, min(int(max_chars), 60000))
    provider_list = _coerce_str_list(providers or extra.get("providers"), _DEFAULT_FETCH_PROVIDERS)
    failures: list[str] = []
    for provider in provider_list:
        try:
            if provider == "jina_reader":
                return _fetch_jina_reader(url, max_chars)
            if provider == "direct":
                return _fetch_direct(url, max_chars, extra)
            failures.append(f"{provider}: unknown provider")
        except Exception as exc:
            failures.append(f"{provider}: {type(exc).__name__}: {exc}")
    return "Fetch request failed: " + " | ".join(failures)
