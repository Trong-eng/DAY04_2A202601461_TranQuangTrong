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

**Link dùng thử (truy cập được trong showdown):**

> Dán public URL nếu người khác cần mở từ máy riêng; localhost cũng được nếu demo trực tiếp trên máy trình chiếu. Streamlit được khuyến nghị, nhưng nhóm có thể dùng bất kỳ framework nào.
>
> URL:

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

Fill from `artifacts/version_log.csv` and `runs/*.json`.

| Version | Prompt/tool change | Hypothesis | Metric name | Before | After | Run File |
|---|---|---|---|---:|---:|---|
| v0 | baseline |  |  |  |  |  |
| v1 |  |  |  |  |  |  |
| v2 |  |  |  |  |  |  |
| v3 |  |  |  |  |  |  |

## B2. Failure analysis

Use actual failures from `results[*].result.failures`.

| Case ID | Failure Type | Actual Tool Calls | What Failed | Fix |
|---|---|---|---|---|
|  |  |  |  |  |

## B3. Team eval cases

List the 10 cases added to `data/eval_group.json`:

- 5 single-turn
- 5 multi-turn

This section is for the mandatory team-authored eval set. Optional built-ins do
not belong here.

File template để trống có chủ đích; nhóm phải tự thiết kế đủ 10 case.

| Case ID | What It Tests | Expected Tool/Behavior | Result |
|---|---|---|---|
|  |  |  |  |

## B4. Live chat evidence

Use `transcripts/*.transcript.json`.

| Scenario/Turn | Version | Tool Calls + Args | Transcript/Run | Outcome |
|---|---|---|---|---|
|  |  |  |  |  |

## B5. Tool capability evidence

Phân loại rõ tool mới bắt buộc, optional built-in và tool đủ điều kiện bonus. Chỉ ghi Telegram/PDF nếu nhóm thực sự dùng; base report không cần chúng.

UI is core deliverable, not bonus. Do not list it here.

| Category | Evidence File | What Worked | Risk / Guardrail |
|---|---|---|---|
| Must-have: tool mới đầu tiên |  |  |  |
| Optional built-in |  |  |  |
| Bonus: tool mới thứ 4 trở đi |  |  |  |

## B6. Reflection

- Which fixes belonged in `system_prompt.md`?
- Which fixes belonged in `tools.yaml`?
- Which failure needed manual review instead of automatic grading?
- What would you improve next?
