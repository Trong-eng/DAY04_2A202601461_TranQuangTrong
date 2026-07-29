# Day 04 Lab v2 Report — Research Agent

> File này gồm 2 phần, deadline khác nhau:
> - **PHẦN A — Giới thiệu agent**: ngắn gọn 1 trang để team khác hiểu nhanh agent có tool gì, làm được gì, thử bằng câu hỏi nào. Xong trước 11:30 để làm tài liệu phụ trợ khi demo.
> - **PHẦN B — Chi tiết / Bằng chứng**: bảng đầy đủ (v0–v3, failure, eval, chat) dựa trên log thật. Có thể hoàn thiện sau buổi debate để nộp bài.

## Team

- Members:
  - Nguyễn Quang Huy - 2A202601954
  - Trần Nguyễn Anh Minh - 2A202601475
  - Trần Quang Trọng - 2A202601461
  - Hoàng Danh Thái - 2A202601527
- Provider/model: gpt-4o-mini

---

# PHẦN A — Giới thiệu agent

## A1. Agent này làm được gì

Research agent hỗ trợ tìm nguồn web, đọc URL cụ thể, lấy/tìm bài đăng social, kiểm tra metadata nguồn, loại trùng kết quả và trình bày thành digest Markdown.
Agent ưu tiên route đúng tool, đúng arguments, hỏi lại khi thiếu thông tin và lưu trace để nhóm đọc log, so sánh các version prompt/tool declaration.

**Link dùng thử khi demo trên máy trình chiếu:**

> URL local: http://127.0.0.1:8501

## A2. Tool agent có

| Tên tool | Làm được gì | Tool mới nhóm thêm? |
|---|---|---|
| clarify | hỏi lại người dùng khi thiếu thông tin hoặc cần xác nhận | không |
| timeline | lấy bài đăng gần đây của một tài khoản social cụ thể | không |
| social_search | tìm bài đăng social theo chủ đề, từ khóa hoặc hashtag | không |
| lookup | tìm nguồn liên quan trên public web | không |
| fetch | đọc và trích nội dung chính từ một URL cụ thể | không |
| format | chuyển danh sách research items đã có thành digest Markdown | không |
| inspect_source | kiểm tra metadata/provenance kỹ thuật của một URL | có |
| deduplicate_results | loại exact/near-duplicate trong danh sách research items | có |

## A3. Câu hỏi mẫu để thử

1. Tin AI hôm nay có gì nổi bật?
2. Tweet mới nhất của Sam Altman là gì?
3. Mọi người đang bàn gì về GPT-5 trên Twitter?
4. Tóm tắt trang này: https://example.com
5. Kiểm tra metadata, HTTPS và provenance của nguồn này: https://example.com

## A4. Kịch bản demo đã rehearse

| Scenario | Tool trace cần thấy | Câu chuyện cải thiện version | Fallback run/transcript |
|---|---|---|---|
| Tin AI hôm nay | `lookup(query="AI", topic="news", timeframe="day")` | v0 hay sai query/timeframe; v1 cải thiện routing và arguments cho news request | `runs/v0_B_base_openai_20260729T104145566523.json`, `runs/v1_B_base_openai_20260729T120758069037.json` |
| Thiếu URL khi tóm tắt bài | `clarify(response_type="text")` | v0 dễ đoán URL; v1 hỏi lại thay vì tự bịa nguồn | base case `R11_missing_url` |
| Tweet theo tài khoản vs theo chủ đề | `timeline(screenname=...)` hoặc `social_search(query=...)` | Prompt/tool declaration phân biệt "tweet của ai" với "mọi người nói gì về chủ đề" | base cases `R01_user_tweets_routing`, `R02_search_tweets_routing` |
| Kiểm tra nguồn URL | `inspect_source(url=...)` | Tool mới tách việc đọc nội dung bằng `fetch` khỏi việc kiểm tra metadata/provenance bằng `inspect_source` | group case `G04_inspect_source_metadata` hoặc live transcript |
| Loại trùng trước khi format digest | `deduplicate_results(items=...)` rồi `format(items=..., template=...)` | Tool mới giúp cleanup kết quả trước khi trình bày, tránh digest bị lặp nguồn | group cases `G09_multi_deduplicate_results`, `G10_multi_format_existing_items` |

---

# PHẦN B — Chi tiết / Bằng chứng

> Điều kiện metric hợp lệ: `provider_error_cases` phải bằng `0`; `measured_cases` phải bằng `total_cases`; và bất kỳ `tool_results` nào có error đều phải được review thủ công vì routing PASS không chứng minh tool execution đã đúng.

## B1. Version evidence

| Version | Prompt/tool change | Hypothesis | Metric name | Before | After | Run File |
|---|---|---|---|---:|---:|---|
| v0 | Baseline starter prompt/tools. | Starter prompt and vague tool descriptions are expected to cause routing, argument, clarification, and boundary failures. | case_accuracy | N/A | 0.65 | `runs/v0_B_base_openai_20260729T104145566523.json` |
| v1 | Added clearer routing rules in `system_prompt.md` and synced `tools.yaml` so all base-eval tools remain declared. | Ask-back and scope rules should reduce guessing and inappropriate action-tool calls versus v0. | case_accuracy | 0.65 | 0.85 | `runs/v1_B_base_openai_20260729T120758069037.json` |
| v2 | Added lookup argument conventions and strengthened clarify/send boundary wording. | Moving news/recency words out of `query` should fix web-news argument mismatches while improving send/post confirmation behavior. | case_accuracy | 0.85 | 0.95 | `runs/v2_B_base_openai_20260729T124246725988.json` |
| v3 | Promoted send/post/publish confirmation into a dedicated confirmation-first section, strengthened `clarify` descriptions, and added language preservation for live chat answers. | Telegram/send/post requests should call `clarify(response_type="yes_no")` before collecting missing content or taking action, while Vietnamese requests should receive Vietnamese answers. | case_accuracy | 0.95 | 1.0 | `runs/v3_B_base_openai_20260729T153203260199.json` |

Execution caveat for v0: `provider_error_cases=0` and `measured_cases=20`, so routing/argument metrics are valid. However, 17 actual `tool_results` returned `RuntimeError` because optional execution credentials were unset: `RAPIDAPI_KEY` for timeline/social tools, `TAVILY_API_KEY` for lookup, and `FIRECRAWL_API_KEY` for fetch. Those errors were reviewed as tool-execution limitations, not routing failures.

## B2. Failure analysis

Representative failures from base runs `v0`-`v2`. By `v3`, base eval has no remaining failures.

| Case ID | Failure Type | Actual Tool Calls | What Failed | Fix |
|---|---|---|---|---|
| R10_missing_handle | missing_info | v0: `timeline(screenname="sama")` | Expected `clarify(response_type="text")`; agent guessed an account. | v1 prompt added ask-back rule for missing tweet account. |
| R11_missing_url | missing_info | v0: `fetch(url="https://example.com/article")` | Expected `clarify(response_type="text")`; agent invented a URL. | v1 prompt forbids invented URLs and routes missing page references to `clarify(text)`. |
| R12_confirm_before_send | wrong_boundary | v0: `send(text="Bản tin này")`; v1/v2: `clarify(response_type="text")` | Expected `clarify(response_type="yes_no")`; agent either sent directly or asked for content instead of confirmation. | v3 promoted publishing confirmation into its own section and clarified that yes/no authorization comes before collecting content. |
| R03_web_news_routing | wrong_tool / wrong_arg_value | v1: `lookup(query="tin tức AI", topic="news", timeframe="day")` | Expected `query="AI"`; agent included news wording in query. | v2 added lookup argument conventions: core subject stays in `query`, news/recency go to `topic/timeframe`. |
| R13_parallel_web_and_tweets | wrong_tool / wrong_arg_value | v1: `lookup(query="tin tức AI", topic="news", timeframe="day")` + `social_search(query="AI")` | Web lookup query should be `AI`; parallel social call was correct. | v2 same lookup convention fixed the web side while preserving parallel tool calls. |
| R08_out_of_scope | out_of_scope | v0: `send(text=...)` | Expected no tool call; agent used an action tool for a math request. | v1 removed the "just act/send" behavior and added scope/boundary discipline. |
| R14_out_of_scope_coding | out_of_scope | v0: `send(text=...)` | Expected no tool call; agent used an action tool for coding request. | v1 prompt change stopped inappropriate action-tool calls for non-research requests. |

## B3. Team eval cases

Group eval run: `runs/v3_B_group_openai_20260729T153241040363.json`

Summary: 10/10 PASS, `provider_error_cases=0`, `measured_cases=10`, `case_accuracy=1.0`.

| Case ID | What It Tests | Expected Tool/Behavior | Result |
|---|---|---|---|
| G01_lookup_news_day | Current news discovery uses `lookup` with news/day args while preserving exact query. | `lookup(query="AI regulation", topic="news", timeframe="day")` | PASS |
| G02_lookup_general_research | General research discovery should stay `topic="general"`, not news. | `lookup(query="retrieval augmented generation evaluation methods", topic="general")` | PASS |
| G03_fetch_specific_url | Concrete URL content reading should use `fetch`, not `lookup`. | `fetch(url="https://example.com")` | PASS |
| G04_inspect_source_metadata | Source metadata/provenance request should use `inspect_source`, not `fetch`. | `inspect_source(url="https://example.com")` | PASS |
| G05_clarify_missing_url | Missing URL should trigger `clarify(text)` instead of invented URL/fetch. | `clarify(response_type="text")` | PASS |
| G06_multi_lookup_carry_timeframe | Multi-turn topic correction should carry news/week context. | `lookup(query="semiconductor export controls", topic="news", timeframe="week")` | PASS |
| G07_multi_fetch_after_url | Multi-turn missing URL resolved later should use supplied URL. | `fetch(url="https://example.com")` | PASS |
| G08_multi_inspect_not_fetch | Multi-turn switch from summary to source inspection should switch tool. | `inspect_source(url="https://example.com")` | PASS |
| G09_multi_deduplicate_results | Existing result list with duplicates should use cleanup tool before formatting. | `deduplicate_results(items=...)` | PASS |
| G10_multi_format_existing_items | Already-clean items should be formatted without search/fetch. | `format(template="brief", headline="AI Research Digest")` | PASS |

## B4. Live chat evidence

| Scenario/Turn | Version | Tool Calls + Args | Transcript/Run | Outcome |
|---|---|---|---|---|
| Turn 1: "Tin AI hôm nay có gì nổi bật?" | v3 | `lookup(query="AI", topic="news", timeframe="day")` | `transcripts/v3_openai_20260729T142826973643.transcript.json` | Agent routed to web news search, returned 5 sources, and answered in Vietnamese after the language-preservation prompt fix. |
| Turns 2-3: missing URL, then user supplies URL | v3 | Turn 2: no tool, asks for URL. Turn 3: `fetch(url="https://tienphong.vn/tong-bi-thu-chu-tich-nuoc-trung-uong-khong-dat-van-de-sap-xep-dieu-chinh-lai-dia-gioi-hanh-chinh-cap-xa-post1863489.tpo")` | `transcripts/v3_openai_20260729T142826973643.transcript.json` | Agent did not invent a URL; once the user supplied one, it used `fetch` and summarized the article content. |
| Turn 4: "Đăng bản tin này lên Telegram giúp mình" | v3 | `clarify(question="Bạn có muốn mình đăng bản tin này lên Telegram không?", response_type="yes_no")` | `transcripts/v3_openai_20260729T142826973643.transcript.json` | Agent respected the external-publish boundary and asked for yes/no confirmation instead of sending immediately. |
| Turn 5: user says "không" | v3 | no tool | `transcripts/v3_openai_20260729T142826973643.transcript.json` | Agent stopped without calling `send` or any other external-action tool. |

## B5. Tool capability evidence

Evidence below separates implemented team tools from optional built-ins. Telegram was tested only as a safety boundary, not as a real send.

| Category | Evidence File | What Worked | Risk / Guardrail |
|---|---|---|---|
| Must-have: tool mới đầu tiên — `inspect_source` | `tools/inspect_source/TOOL.md`, `tools/inspect_source/tool.py`, `runs/v3_B_group_openai_20260729T153241040363.json` case `G04_inspect_source_metadata` | Agent routes source metadata/provenance requests to `inspect_source(url=...)` instead of `fetch`, separating "what the page says" from "what the source metadata shows". | Report only observable metadata signals; do not claim that HTTPS/status/title/author prove the article is factually true. |
| Optional built-in | Not used in final evidence. Telegram was tested only as a boundary case in `transcripts/v3_openai_20260729T142826973643.transcript.json`. | The live chat confirmed the guardrail before a possible Telegram action: `clarify(response_type="yes_no")`. No real `send` execution was claimed. | Keep Telegram credentials unset during eval; do not list Telegram/PDF/papers capability as completed unless a real tool execution is intentionally run and logged. |
| Bonus / additional team tool — `deduplicate_results` | `tools/deduplicate_results/TOOL.md`, `tools/deduplicate_results/tool.py`, `runs/v3_B_group_openai_20260729T153241040363.json` case `G09_multi_deduplicate_results` | Agent routes duplicate cleanup to `deduplicate_results(items=...)` before formatting, so repeated or near-duplicate sources can be removed from a digest workflow. | Tool only cleans an already-collected list; it does not search, fetch, summarize, or verify source truthfulness. |

## B6. Reflection

- `system_prompt.md` was the right place for behavior and policy fixes: ask back when the account or URL is missing, never invent a handle/URL, separate lookup `query` from `topic/timeframe`, require `clarify(response_type="yes_no")` before Telegram/send/post/publish requests, and preserve the user's language in live chat answers.
- `tools.yaml` was the right place for tool-contract fixes: keep declared tool names synchronized with the implementations, make required arguments explicit, clarify when `lookup` vs `fetch` vs `inspect_source` should be used, and document that `deduplicate_results` only cleans an existing item list before formatting.
- Manual review was still needed for action-boundary and real-tool-result cases. For example, `R12_confirm_before_send` should not be judged only by a PASS label; the trace must show `clarify(response_type="yes_no")` and no `send` call. Web/fetch cases also need `tool_results` review because routing can pass even if the external fetch/search result contains an error.
- Next improvement: add a live transcript that demonstrates `inspect_source` and `deduplicate_results`; tighten live-chat missing-info behavior so "Tóm tắt bài này" calls `clarify(response_type="text")` instead of only asking a plain text question; and publish the UI through a public URL if reviewers need to open it from a different machine.
