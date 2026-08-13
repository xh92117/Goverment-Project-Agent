"""Dependency-light web search and fetch tools.

These tools intentionally use only httpx from the base runtime so deployments
can enable basic web access without installing search-provider extras.
"""

from __future__ import annotations

import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import httpx
from langchain.tools import tool

from deerflow.config import get_app_config

_JINA_READER_PREFIX = "https://r.jina.ai/http://"
_DEFAULT_TIMEOUT = 20.0
_DEFAULT_MAX_RESULTS = 5
_DEFAULT_EXTRACT_SNIPPETS = 5
_DEFAULT_SEARCH_ENGINE = "bing_cn"
_DEFAULT_CACHE_TTL_SECONDS = 900
_MAX_SEARCH_CACHE_ENTRIES = 256
_DEFAULT_MULTI_ENGINES = [_DEFAULT_SEARCH_ENGINE]
_SEARCH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_DEFAULT_OFFICIAL_DOMAINS = [
    "gov.cn",
    "most.gov.cn",
    "nsfc.gov.cn",
    "miit.gov.cn",
    "ndrc.gov.cn",
    "mof.gov.cn",
    "moe.gov.cn",
    "samr.gov.cn",
]
_LOW_QUALITY_DOMAIN_KEYWORDS = (
    "peixun",
    "doc88",
    "docin",
    "book118",
    "wenku",
    "zhidao",
    "csdn",
)
_DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
_TIME_RANGE_TERMS = {
    "day": "past day",
    "week": "past week",
    "month": "past month",
    "year": "past year",
    "latest": "latest",
    "recent": "recent",
    "today": "today",
}
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_SEARCH_ENGINES: dict[str, dict[str, str]] = {
    "baidu": {"label": "Baidu", "url": "https://www.baidu.com/s?wd={keyword}"},
    "bing_cn": {"label": "Bing CN", "url": "https://cn.bing.com/search?q={keyword}&ensearch=0"},
    "bing_int": {"label": "Bing INT", "url": "https://cn.bing.com/search?q={keyword}&ensearch=1"},
    "360": {"label": "360", "url": "https://www.so.com/s?q={keyword}"},
    "sogou": {"label": "Sogou", "url": "https://sogou.com/web?query={keyword}"},
    "wechat": {"label": "WeChat", "url": "https://wx.sogou.com/weixin?type=2&query={keyword}"},
    "toutiao": {"label": "Toutiao", "url": "https://so.toutiao.com/search?keyword={keyword}"},
    "jisilu": {"label": "Jisilu", "url": "https://www.jisilu.cn/explore/?keyword={keyword}"},
    "google": {"label": "Google", "url": "https://www.google.com/search?q={keyword}"},
    "google_hk": {"label": "Google HK", "url": "https://www.google.com.hk/search?q={keyword}"},
    "duckduckgo": {"label": "DuckDuckGo", "url": "https://duckduckgo.com/html/?q={keyword}"},
    "yahoo": {"label": "Yahoo", "url": "https://search.yahoo.com/search?p={keyword}"},
    "startpage": {"label": "Startpage", "url": "https://www.startpage.com/sp/search?query={keyword}"},
    "brave": {"label": "Brave", "url": "https://search.brave.com/search?q={keyword}"},
    "ecosia": {"label": "Ecosia", "url": "https://www.ecosia.org/search?q={keyword}"},
    "qwant": {"label": "Qwant", "url": "https://www.qwant.com/?q={keyword}"},
    "wolframalpha": {"label": "WolframAlpha", "url": "https://www.wolframalpha.com/input?i={keyword}"},
}
_SEARCH_ENGINE_ALIASES = {
    "bing": "bing_cn",
    "bingcn": "bing_cn",
    "bing_intl": "bing_int",
    "googlehk": "google_hk",
    "google_hk": "google_hk",
    "google_cn": "google_hk",
    "ddg": "duckduckgo",
    "duck": "duckduckgo",
    "so": "360",
    "so360": "360",
    "weixin": "wechat",
    "wx": "wechat",
    "sp": "startpage",
    "wolfram": "wolframalpha",
}
_RESULT_RE = re.compile(
    r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?(?:<p[^>]*>(?P<snippet>.*?)</p>)?',
    re.I | re.S,
)
_ANCHOR_RE = re.compile(r'<a[^>]+href=["\'](?P<url>[^"\']+)["\'][^>]*>(?P<title>.*?)</a>', re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://[^\s<>()\"']+")
_FIELD_SPLIT_RE = re.compile(r"[,，、;；\n]+")
_DATE_RE = re.compile(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?|\d{1,2}[月/-]\d{1,2}日?")
_PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s?%")
_AMOUNT_RE = re.compile(r"\d+(?:\.\d+)?\s?(?:亿元|万元|元|万|亿|k|K|m|M|b|B)")
_TEMPERATURE_RE = re.compile(r"-?\d+(?:\.\d+)?\s?(?:℃|°C|度)")
_WEATHER_WORD_RE = re.compile(r"晴|阴|多云|小雨|中雨|大雨|暴雨|阵雨|雷阵雨|雪|雾|霾|沙尘")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")


def _strip_html(value: str) -> str:
    text = _TAG_RE.sub("", value)
    return " ".join(html.unescape(text).split())


def _clean_text(value: str) -> str:
    text = _TAG_RE.sub("\n", value)
    text = html.unescape(text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _valid_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _extract_redirect_target(url: str) -> str | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("url", "q", "u", "uddg"):
        for value in query.get(key, []):
            candidate = unquote(value).strip()
            if _valid_http_url(candidate):
                return candidate
    return None


def _normalize_result_url(url: str) -> str | None:
    url = html.unescape(url).strip()
    if not url:
        return None
    if url.startswith("//"):
        url = f"https:{url}"

    redirected = _extract_redirect_target(url)
    if redirected:
        return redirected

    parsed = urlparse(url)
    if not parsed.scheme and parsed.query:
        redirected = _extract_redirect_target(url)
        if redirected:
            return redirected

    if _valid_http_url(url):
        return url
    return None


def _normalize_engine(engine: str | None) -> str:
    raw = (engine or _DEFAULT_SEARCH_ENGINE).strip().lower().replace("-", "_")
    raw = _SEARCH_ENGINE_ALIASES.get(raw, raw)
    if raw not in _SEARCH_ENGINES:
        return _DEFAULT_SEARCH_ENGINE
    return raw


def _search_url(engine: str, query: str) -> str:
    return _SEARCH_ENGINES[engine]["url"].format(keyword=quote(query, safe=""))


def _cache_key(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _get_cached_search(key: str, ttl_seconds: int) -> dict[str, Any] | None:
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


def _put_cached_search(key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    if ttl_seconds <= 0:
        return
    if len(_SEARCH_CACHE) >= _MAX_SEARCH_CACHE_ENTRIES:
        oldest_key = min(_SEARCH_CACHE, key=lambda item: _SEARCH_CACHE[item][0])
        _SEARCH_CACHE.pop(oldest_key, None)
    _SEARCH_CACHE[key] = (time.time(), json.loads(json.dumps(payload, ensure_ascii=False)))


def _coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_str_list(value: object, default: list[str] | None = None) -> list[str]:
    if value is None:
        return list(default or [])
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\s]+", value) if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return list(default or [])


def _normalize_engines(engines: object, fallback_engine: str = _DEFAULT_SEARCH_ENGINE) -> list[str]:
    normalized: list[str] = []
    for item in _coerce_str_list(engines, [fallback_engine]):
        engine = _normalize_engine(item)
        if engine not in normalized:
            normalized.append(engine)
    return normalized or [_normalize_engine(fallback_engine)]


def _domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _is_document_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _DOCUMENT_EXTENSIONS)


def _is_official_domain(domain: str, official_domains: list[str]) -> bool:
    for official in official_domains:
        official = official.lower().strip().removeprefix("www.")
        if not official:
            continue
        if domain == official or domain.endswith(f".{official}"):
            return True
    return False


def _source_type(url: str, official_domains: list[str]) -> str:
    domain = _domain(url)
    if _is_official_domain(domain, official_domains):
        return "official_document" if _is_document_url(url) else "official"
    if _is_document_url(url):
        return "document"
    if any(token in domain for token in ("weixin", "toutiao", "sohu", "163", "sina", "qq.com")):
        return "media_or_social"
    if any(token in domain for token in _LOW_QUALITY_DOMAIN_KEYWORDS):
        return "low_quality"
    return "unknown"


def _result_score(result: dict[str, str], official_domains: list[str], query: str) -> int:
    url = result.get("url", "")
    domain = _domain(url)
    title = result.get("title", "")
    content = result.get("content", "")
    combined = f"{title} {content}".lower()
    score = 0
    official_domain = _is_official_domain(domain, official_domains)
    if official_domain:
        score += 100
    if _is_document_url(url):
        score += 20
    if any(word in combined for word in ("通知", "指南", "申报", "公示", "deadline", "guide", "notice")):
        score += 15
    query_terms = _query_terms(query)
    matched_terms = [term for term in query_terms if term and term in combined]
    score += len(matched_terms) * 4
    if query_terms and not matched_terms:
        score -= 30
    if any(token in domain for token in _LOW_QUALITY_DOMAIN_KEYWORDS):
        score -= 40
    return score


def _augment_query(query: str, *, site: str = "", filetype: str = "", time_range: str = "") -> str:
    parts = [query.strip()]
    if "\u52a8\u6001\u56de\u5f39\u6a21\u578b" in query and "\u52a8\u6001\u56de\u5f39\u6a21\u91cf" not in query:
        parts.append("\u52a8\u6001\u56de\u5f39\u6a21\u91cf")
    site = site.strip()
    filetype = filetype.strip().lower().lstrip(".")
    time_range = time_range.strip().lower()
    if site and "site:" not in query:
        parts.append(f"site:{site}")
    if filetype and "filetype:" not in query:
        parts.append(f"filetype:{filetype}")
    if time_range and time_range not in {"any", "all", "none"}:
        parts.append(_TIME_RANGE_TERMS.get(time_range, time_range))
    return " ".join(part for part in parts if part)


def _decorate_results(results: list[dict[str, str]], *, engine: str, search_url: str, official_domains: list[str], query: str) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for result in results:
        url = result.get("url", "")
        domain = _domain(url)
        source_type = _source_type(url, official_domains)
        score = _result_score(result, official_domains, query)
        decorated.append(
            {
                "title": result.get("title", ""),
                "url": url,
                "content": result.get("content", ""),
                "engine": engine,
                "engine_label": _SEARCH_ENGINES[engine]["label"],
                "search_url": search_url,
                "domain": domain,
                "source_type": source_type,
                "is_official": source_type.startswith("official"),
                "score": score,
            }
        )
    return decorated


def _dedupe_and_rank_results(results: list[dict[str, Any]], max_results: int, official_first: bool, *, query: str = "") -> list[dict[str, Any]]:
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


def _has_query_match(result: dict[str, Any], query: str) -> bool:
    terms = _query_terms(query)
    if not terms:
        return True
    combined = f"{result.get('title', '')} {result.get('content', '')}".lower()
    return any(term and term in combined for term in terms)


def _search_engine_once(client: httpx.Client, *, query: str, engine: str, max_results: int, official_domains: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    search_url = _search_url(engine, query)
    try:
        response = client.get(search_url)
        response.raise_for_status()
    except Exception as exc:
        return [], {"engine": engine, "search_url": search_url, "error": f"{type(exc).__name__}: {exc}"}

    results = _extract_bing_results(response.text, max_results)
    if not results:
        results = _extract_anchor_results(response.text, max_results)
    return _decorate_results(results, engine=engine, search_url=search_url, official_domains=official_domains, query=query), {
        "engine": engine,
        "search_url": search_url,
        "result_count": len(results),
    }


def _extract_bing_results(html_text: str, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _RESULT_RE.finditer(html_text):
        url = _normalize_result_url(match.group("url"))
        if not url or url in seen:
            continue
        seen.add(url)
        results.append(
            {
                "title": _strip_html(match.group("title") or ""),
                "url": url,
                "content": _strip_html(match.group("snippet") or ""),
            }
        )
        if len(results) >= max_results:
            break
    return results


def _extract_anchor_results(html_text: str, max_results: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _ANCHOR_RE.finditer(html_text):
        url = _normalize_result_url(match.group("url"))
        if not url or url in seen:
            continue
        title = _strip_html(match.group("title") or "")
        if not title or len(title) < 2:
            continue
        seen.add(url)
        results.append({"title": title, "url": url, "content": ""})
        if len(results) >= max_results:
            break
    return results


def _timeout(tool_name: str, default: float = _DEFAULT_TIMEOUT) -> float:
    config = get_app_config().get_tool_config(tool_name)
    if config is None:
        return default
    raw = config.model_extra.get("timeout", default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _trust_env(tool_name: str) -> bool:
    config = get_app_config().get_tool_config(tool_name)
    if config is None:
        return False
    return bool(config.model_extra.get("trust_env", False))


def _fetch_readable_text(url: str, *, max_chars: int, tool_name: str) -> str:
    reader_url = _JINA_READER_PREFIX + url
    with httpx.Client(
        timeout=_timeout(tool_name),
        follow_redirects=True,
        trust_env=_trust_env(tool_name),
        http2=False,
    ) as client:
        response = client.get(reader_url)
        response.raise_for_status()
    text = response.text.strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n\n[truncated]"
    return text


def _flatten_json(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(_flatten_json(item, next_prefix))
        return lines
    if isinstance(value, list):
        lines = []
        for index, item in enumerate(value):
            next_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            lines.extend(_flatten_json(item, next_prefix))
        return lines
    if value is None:
        return []
    return [f"{prefix}: {value}" if prefix else str(value)]


def _source_to_text(source: str, max_chars: int) -> tuple[str, str, str | None]:
    source = source.strip()
    if _valid_http_url(source):
        try:
            return _fetch_readable_text(source, max_chars=max_chars, tool_name="web_extract"), "url", source
        except Exception as exc:
            return f"Fetch request failed: {exc}", "url", source

    try:
        parsed = json.loads(source)
    except json.JSONDecodeError:
        return _clean_text(source[:max_chars]), "text", None

    lines: list[str] = []
    if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
        for item in parsed["results"]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            url = item.get("url") or ""
            content = item.get("content") or item.get("snippet") or ""
            lines.append(" | ".join(part for part in [str(title), str(url), str(content)] if part))
    else:
        lines = _flatten_json(parsed)
    return _clean_text("\n".join(lines)[:max_chars]), "json", None


def _split_fields(fields: str) -> list[str]:
    parsed = [item.strip() for item in _FIELD_SPLIT_RE.split(fields) if item.strip()]
    return parsed[:20]


def _field_patterns(field: str) -> list[re.Pattern[str]]:
    lowered = field.lower()
    patterns: list[re.Pattern[str]] = []
    if any(token in lowered for token in ["date", "time", "deadline", "日期", "时间", "截止", "发布"]):
        patterns.append(_DATE_RE)
    if any(token in lowered for token in ["percent", "rate", "比例", "百分比", "湿度", "强度"]):
        patterns.append(_PERCENT_RE)
    if any(token in lowered for token in ["amount", "budget", "fund", "price", "金额", "预算", "经费", "费用", "资助"]):
        patterns.append(_AMOUNT_RE)
    if any(token in lowered for token in ["temperature", "temp", "温度", "气温"]):
        patterns.append(_TEMPERATURE_RE)
    if any(token in lowered for token in ["weather", "天气", "状况"]):
        patterns.append(_WEATHER_WORD_RE)
    if any(token in lowered for token in ["url", "link", "source", "链接", "网址", "来源"]):
        patterns.append(_URL_RE)
    return patterns


def _split_snippets(text: str) -> list[str]:
    chunks = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    snippets: list[str] = []
    for chunk in chunks:
        chunk = _clean_text(chunk)
        if not chunk:
            continue
        if len(chunk) <= 320:
            snippets.append(chunk)
            continue
        snippets.extend(chunk[index : index + 320].strip() for index in range(0, len(chunk), 320))
    return [snippet for snippet in snippets if snippet]


def _query_terms(query: str) -> list[str]:
    terms: list[str] = []
    for item in re.split(r"[,，、;\s]+", query):
        item = item.strip().lower()
        if item:
            terms.append(item)
    for chunk in _CJK_RE.findall(query):
        for keyword in ("检测", "技术", "现状", "模型", "模量", "回弹", "动态"):
            if keyword in chunk:
                terms.append(keyword)
        if len(chunk) <= 4:
            terms.append(chunk.lower())
            continue
        for size in (4, 3, 2):
            for index in range(0, len(chunk) - size + 1):
                terms.append(chunk[index : index + size].lower())
    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped[:24]


def _candidate_value(snippet: str, patterns: list[re.Pattern[str]]) -> str | None:
    for pattern in patterns:
        match = pattern.search(snippet)
        if match:
            return match.group(0)
    urls = _URL_RE.findall(snippet)
    if urls:
        return urls[0]
    return None


def _extract_candidates(text: str, field: str, query: str, max_snippets: int) -> list[dict[str, Any]]:
    snippets = _split_snippets(text)
    field_lower = field.lower()
    terms = _query_terms(query)
    patterns = _field_patterns(field)
    candidates: list[dict[str, Any]] = []

    for snippet in snippets:
        snippet_lower = snippet.lower()
        value = _candidate_value(snippet, patterns)
        score = 0
        if field_lower and field_lower in snippet_lower:
            score += 4
        score += sum(1 for term in terms if term and term in snippet_lower)
        if value:
            score += 3
        if any(pattern.search(snippet) for pattern in patterns):
            score += 2
        if score <= 0:
            continue
        candidates.append(
            {
                "value": value or "",
                "snippet": snippet[:500],
                "score": score,
            }
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate["snippet"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
        if len(deduped) >= max_snippets:
            break
    return deduped


@tool("web_search", parse_docstring=True)
def web_search_tool(
    query: str,
    max_results: int = _DEFAULT_MAX_RESULTS,
    engine: str = _DEFAULT_SEARCH_ENGINE,
    engines: str = "",
    site: str = "",
    filetype: str = "",
    time_range: str = "",
    official_first: bool = True,
) -> str:
    """Search the public web through one or more search engines with source ranking.

    Prefer this tool for latest policy notices, annual project guides,
    deadlines, official announcements, and facts that may have changed.

    Args:
        query: Search keywords. Use site: filters for official sources when possible.
        max_results: Maximum number of results to return.
        engine: Single search engine id, used when engines is empty.
        engines: Optional comma-separated engine ids for multi-engine search.
        site: Optional domain for site-specific search, such as most.gov.cn.
        filetype: Optional file extension filter, such as pdf, doc, or xls.
        time_range: Optional recency hint, such as latest, day, week, month, or year.
        official_first: Whether to rank official government/project sources first.
    """
    config = get_app_config().get_tool_config("web_search")
    configured_engines: object = None
    official_domains = list(_DEFAULT_OFFICIAL_DOMAINS)
    cache_ttl_seconds = _DEFAULT_CACHE_TTL_SECONDS
    if config is not None:
        max_results = int(config.model_extra.get("max_results", max_results))
        if engine == _DEFAULT_SEARCH_ENGINE:
            engine = str(config.model_extra.get("engine", engine))
        configured_engines = config.model_extra.get("engines")
        official_domains = _coerce_str_list(config.model_extra.get("official_domains"), official_domains)
        official_first = _coerce_bool(config.model_extra.get("official_first"), official_first)
        cache_ttl_seconds = int(config.model_extra.get("cache_ttl_seconds", cache_ttl_seconds))
        if not _coerce_bool(config.model_extra.get("cache_enabled", True), True):
            cache_ttl_seconds = 0
    max_results = max(1, min(max_results, 10))
    if engines:
        requested_engines: object = engines
    elif engine != _DEFAULT_SEARCH_ENGINE or configured_engines is None:
        requested_engines = [engine]
    else:
        requested_engines = configured_engines
    engine_list = _normalize_engines(requested_engines, engine)
    effective_query = _augment_query(query, site=site, filetype=filetype, time_range=time_range)
    cache_key = _cache_key(
        {
            "query": effective_query,
            "max_results": max_results,
            "engines": engine_list,
            "official_domains": official_domains,
            "official_first": official_first,
        }
    )
    cached_payload = _get_cached_search(cache_key, cache_ttl_seconds)
    if cached_payload is not None:
        cached_payload["cache_hit"] = True
        return json.dumps(cached_payload, ensure_ascii=False, indent=2)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        )
    }
    all_results: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    with httpx.Client(
        timeout=_timeout("web_search"),
        follow_redirects=True,
        headers=headers,
        trust_env=_trust_env("web_search"),
        http2=False,
    ) as client:
        if len(engine_list) == 1:
            results, diagnostic = _search_engine_once(
                client,
                query=effective_query,
                engine=engine_list[0],
                max_results=max_results,
                official_domains=official_domains,
            )
            all_results.extend(results)
            diagnostics.append(diagnostic)
        else:
            with ThreadPoolExecutor(max_workers=min(len(engine_list), 4)) as executor:
                futures = [
                    executor.submit(
                        _search_engine_once,
                        client,
                        query=effective_query,
                        engine=item,
                        max_results=max_results,
                        official_domains=official_domains,
                    )
                    for item in engine_list
                ]
                for future in as_completed(futures):
                    results, diagnostic = future.result()
                    all_results.extend(results)
                    diagnostics.append(diagnostic)

    ranked_results = _dedupe_and_rank_results(all_results, max_results, official_first, query=effective_query)

    payload = (
        {
            "query": query,
            "effective_query": effective_query,
            "engine": engine_list[0],
            "engines": engine_list,
            "engine_label": _SEARCH_ENGINES[engine_list[0]]["label"],
            "search_url": diagnostics[0].get("search_url") if diagnostics else "",
            "available_engines": list(_SEARCH_ENGINES),
            "total_results": len(ranked_results),
            "results": ranked_results,
            "diagnostics": diagnostics,
            "cache_hit": False,
        }
        if ranked_results
        else {
            "error": "No results found",
            "query": query,
            "effective_query": effective_query,
            "engine": engine_list[0],
            "engines": engine_list,
            "available_engines": list(_SEARCH_ENGINES),
            "diagnostics": diagnostics,
            "cache_hit": False,
        }
    )
    if ranked_results:
        _put_cached_search(cache_key, payload, cache_ttl_seconds)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool("web_fetch", parse_docstring=True)
def web_fetch_tool(url: str, max_chars: int = 12000) -> str:
    """Fetch and extract readable Markdown from an exact URL.

    Only fetch URLs provided by the user or returned by web_search.

    Args:
        url: Exact HTTP or HTTPS URL to fetch.
        max_chars: Maximum characters to return.
    """
    if not _valid_http_url(url):
        return "Invalid URL: web_fetch only accepts http(s) URLs."
    max_chars = max(500, min(max_chars, 60000))
    try:
        return _fetch_readable_text(url, max_chars=max_chars, tool_name="web_fetch")
    except Exception as exc:
        return f"Fetch request failed: {exc}"


@tool("web_extract", parse_docstring=True)
def web_extract_tool(
    source: str,
    fields: str,
    query: str = "",
    max_snippets: int = _DEFAULT_EXTRACT_SNIPPETS,
    max_chars: int = 60000,
) -> str:
    """Extract requested fields from a URL, web_search JSON, web_fetch text, HTML, or raw JSON.

    Use this after web_search or web_fetch when the user asks for specific
    facts, numbers, dates, titles, links, statuses, or other fields from web
    content. The tool returns ranked evidence snippets; cite the original URL
    when answering.

    Args:
        source: URL, web_search JSON, web_fetch text, HTML, or raw JSON to inspect.
        fields: Comma-separated field names to extract, such as deadline, amount, title.
        query: Optional user question or keywords used to rank snippets.
        max_snippets: Maximum candidate snippets per field.
        max_chars: Maximum source characters to inspect.
    """
    max_snippets = max(1, min(max_snippets, 10))
    max_chars = max(1000, min(max_chars, 120000))
    field_names = _split_fields(fields)
    if not field_names:
        return json.dumps({"error": "No fields provided", "fields": fields}, ensure_ascii=False)

    text, source_type, source_url = _source_to_text(source, max_chars)
    if text.startswith("Fetch request failed:"):
        return json.dumps({"error": text, "source_type": source_type, "source_url": source_url}, ensure_ascii=False)

    extracted = [
        {
            "name": field,
            "candidates": _extract_candidates(text, field, query, max_snippets),
        }
        for field in field_names
    ]
    return json.dumps(
        {
            "source_type": source_type,
            "source_url": source_url,
            "query": query,
            "fields": extracted,
        },
        ensure_ascii=False,
        indent=2,
    )
