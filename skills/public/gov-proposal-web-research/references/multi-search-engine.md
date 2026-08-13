# Multi-Search Engine Reference

Use this reference when constructing concrete search queries for
`gov-proposal-web-research`.

## Provider Selection

The production `web_search` tool is a hybrid provider gateway:

| Provider | Best Use |
| --- | --- |
| `serper` | Google-quality recall when `SERPER_API_KEY` is configured |
| `ddgs` | No-key broad search and privacy-friendly fallback |
| `simple_web` | No-key direct search-page scraping fallback with selectable engines |

Use `providers` only when you need to override the configured default, for
example `providers="ddgs,simple_web"` when Serper is unavailable or
`providers="simple_web"` when testing a specific no-key engine path.

## Engine Selection

The `simple_web` fallback provider supports selectable engines through
configuration. Useful engine ids include:

| Engine | Best Use |
| --- | --- |
| `baidu` | Chinese official notices, local department pages, broad CN recall |
| `bing_cn` | Default Chinese search with stable snippets |
| `bing_int` | English/global sources from the Bing endpoint |
| `360` | Chinese fallback when Baidu/Bing miss local pages |
| `sogou` | Chinese web fallback |
| `wechat` | Public-account interpretations, use only as supplementary evidence |
| `toutiao` | News/social supplementary context, not authoritative |
| `jisilu` | Finance/investment-specific lookup |
| `google` | Global search when network access allows Google |
| `google_hk` | Google Hong Kong endpoint for global/CN-adjacent queries |
| `duckduckgo` | Privacy-friendly global fallback |
| `yahoo` | Global fallback with broad recall |
| `startpage` | Privacy-oriented Google-style results |
| `brave` | Independent-index global fallback |
| `ecosia` | Global privacy-friendly fallback |
| `qwant` | EU/privacy-friendly global fallback |
| `wolframalpha` | Calculations, conversions, weather, quantitative knowledge |

This list mirrors the no-key pattern from the referenced OpenClaw skill:
Baidu, Bing CN, Bing INT, 360, Sogou, WeChat, Toutiao, Jisilu, Google,
Google HK, DuckDuckGo, Yahoo, Startpage, Brave, Ecosia, Qwant, and
WolframAlpha.

## Advanced Operators

| Operator | Example | Use |
| --- | --- | --- |
| `site:` | `site:most.gov.cn 重点研发计划 2026 申报指南` | Search within an official site |
| `filetype:` | `科技计划 申报指南 filetype:pdf` | Locate guides, templates, attachments |
| `""` | `"国家重点研发计划" "申报指南"` | Exact phrase |
| `-` | `申报指南 -培训 -代写 -转载` | Exclude low-quality pages |
| `OR` | `科技厅 OR 工信厅 项目 申报 通知` | Search alternatives |

## Time Filters

Use time terms in the query when the tool provider does not expose direct time
parameters:

- `2026`, `2025`, or the target year.
- `最新`, `本年度`, `申报通知`, `申报指南`, `征集通知`, `公示`.
- For engines that support URL parameters, Google-style filters include
  `tbs=qdr:h` for past hour, `tbs=qdr:d` for past day, `tbs=qdr:w` for past
  week, `tbs=qdr:m` for past month, and `tbs=qdr:y` for past year.

## Government Query Patterns

Use these as starting points and adapt the authority, year, and domain:

```text
site:gov.cn 2026 科技计划 申报指南
site:most.gov.cn 重点研发计划 2026 申报指南 filetype:pdf
site:nsfc.gov.cn 2026 项目指南 申请 截止
省科技厅 2026 科技计划 项目 申报 通知
市科技局 2026 科技项目 申报 材料 附件
"项目申报指南" "资助额度" "截止时间"
"申报通知" "附件" "项目申报书" filetype:doc
```

## Source Quality Rules

- Treat public-account articles, training institutions, repost portals, and
  document mirrors as discovery aids only.
- Use snippets to decide what to fetch, not as final evidence.
- Always prefer the source page that hosts or links the attachment over a
  third-party copy of the same attachment.
- Deduplicate reposts by title, document number, attachment filename, and URL.
- If a source cannot be fetched, cite it only as an unfetched search result and
  lower confidence.
