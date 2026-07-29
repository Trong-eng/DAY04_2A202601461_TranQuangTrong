"""Streamlit UI for the Day 04 research agent.

Design assumptions and placeholder policy live in ui/design-notes.md. This UI
reuses chat.run_model_tool_loop so the terminal chat, evaluator, and UI share
one agent execution contract.
"""

from __future__ import annotations

import html
import inspect
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chat import (
    now_iso,
    run_model_tool_loop,
    safe_slug,
    trim_history,
    write_transcript,
)
from providers import make_provider
from tools import TOOL_FUNCTIONS, load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

ARTIFACTS_DIR = ROOT / "artifacts"
RUNS_DIR = ROOT / "runs"
TRANSCRIPTS_DIR = ROOT / "transcripts"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "transcripts" / "example_openrouter_20260101T030000000000.transcript.json"
VERSION_OPTIONS = ("v0", "v1", "v2", "v3")

PROVIDER_META = {
    "openrouter": {
        "label": "OpenRouter",
        "key": "OPENROUTER_API_KEY",
        "default_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
    },
    "openai": {
        "label": "OpenAI",
        "key": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        "label": "Anthropic",
        "key": "ANTHROPIC_API_KEY",
        "default_model": "claude-haiku-4-5-20251001",
    },
    "gemini": {
        "label": "Gemini",
        "key": "GEMINI_API_KEY",
        "default_model": "gemini-3.5-flash",
    },
}

TOOL_LABELS = {
    "clarify": "Hỏi lại để làm rõ yêu cầu",
    "timeline": "Đọc dòng thời gian của một tài khoản",
    "social_search": "Tìm kiếm bài đăng mạng xã hội",
    "lookup": "Tìm kiếm trên web",
    "fetch": "Đọc nội dung một trang web",
    "format": "Định dạng bản tin nghiên cứu",
    "send": "Gửi nội dung lên Telegram",
    "policy": "Tra cứu chính sách công ty",
    "papers": "Tìm kiếm trên arXiv",
    "paper_text": "Trích xuất nội dung bài báo",
    "inspect_source": "Kiểm tra nguồn gốc và metadata của một URL",
    "deduplicate_results": "Loại bỏ kết quả nghiên cứu trùng lặp",
}

METRICS = (
    ("case_accuracy", "Độ chính xác"),
    ("tool_routing_accuracy", "Định tuyến"),
    ("argument_accuracy", "Tham số"),
    ("multiturn_accuracy", "Đa lượt"),
)

STATUS_LABELS = {
    "answered": "Đã trả lời",
    "waiting_for_user": "Đang chờ phản hồi",
    "max_tool_rounds": "Đã đạt giới hạn vòng công cụ",
    "provider_error": "Lỗi nhà cung cấp",
    "started": "Đang xử lý",
    "unknown": "Không rõ",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def artifact_paths(version: str, use_snapshot: bool) -> tuple[Path, Path, str]:
    snapshot_dir = ARTIFACTS_DIR / "versions" / version
    snapshot_prompt = snapshot_dir / "system_prompt.md"
    snapshot_tools = snapshot_dir / "tools.yaml"
    if use_snapshot and snapshot_prompt.exists() and snapshot_tools.exists():
        return snapshot_prompt, snapshot_tools, f"Snapshot {version} đã lưu"
    return ARTIFACTS_DIR / "system_prompt.md", ARTIFACTS_DIR / "tools.yaml", "Artifact hiện tại"


def available_snapshot(version: str) -> bool:
    snapshot_dir = ARTIFACTS_DIR / "versions" / version
    return (snapshot_dir / "system_prompt.md").exists() and (snapshot_dir / "tools.yaml").exists()


def discover_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for path in sorted(RUNS_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        payload["_path"] = str(path)
        runs.append(payload)
    return runs


def discover_transcripts() -> list[dict[str, Any]]:
    transcripts: list[dict[str, Any]] = []
    for path in sorted(TRANSCRIPTS_DIR.glob("*.transcript.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        turns = payload.get("turns", [])
        if not isinstance(turns, list):
            continue
        first_question = ""
        if turns:
            first_question = " ".join(str(turns[0].get("user", "")).split())
        if len(first_question) > 42:
            first_question = f"{first_question[:41]}…"
        updated_at = str(payload.get("updated_at") or payload.get("created_at") or "")
        try:
            updated_label = datetime.fromisoformat(updated_at).strftime("%d/%m · %H:%M")
        except ValueError:
            updated_label = "Không rõ thời gian"
        transcripts.append(
            {
                "path": path,
                "payload": payload,
                "label": f"{updated_label} · {len(turns)} lượt · {first_question or 'Phiên chưa có nội dung'}",
            }
        )
    return transcripts


def latest_runs_by_version(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for run in runs:
        version = str(run.get("version", "unknown"))
        latest.setdefault(version, run)
    return latest


def percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "—"
    return f"{value * 100:.0f}%"


def compact_hash(value: Any, length: int = 8) -> str:
    text = str(value or "")
    return text[:length] if text else "—"


def tool_event_state(event: dict[str, Any]) -> tuple[str, str]:
    result = event.get("result")
    if not isinstance(result, dict):
        return "complete", "Hoàn tất"
    if result.get("awaiting_user"):
        return "waiting", "Đang chờ"
    if result.get("error"):
        return "error", "Có lỗi"
    return "complete", "Hoàn tất"


def result_preview(event: dict[str, Any]) -> str:
    result = event.get("result")
    if isinstance(result, dict):
        if result.get("message"):
            return str(result["message"])
        items = result.get("items")
        if isinstance(items, list):
            return f"Đã trả về {len(items)} mục."
        if result.get("awaiting_user"):
            return str(result.get("question", "Đang chờ người dùng phản hồi."))
    return "Kết quả đã được lưu trong transcript."


def declared_tool_names(tools_path: Path) -> list[str]:
    try:
        return [str(item.get("name")) for item in load_tool_declarations(tools_path)]
    except (OSError, KeyError, TypeError, ValueError):
        return []


def session_config_key(
    *,
    provider: str,
    model: str,
    version: str,
    use_snapshot: bool,
    prompt_path: Path,
    tools_path: Path,
    history_window: int,
    max_tool_rounds: int,
) -> str:
    return "|".join(
        [
            provider,
            model,
            version,
            str(use_snapshot),
            str(prompt_path),
            str(tools_path),
            str(history_window),
            str(max_tool_rounds),
        ]
    )


def history_from_turns(turns: list[dict[str, Any]]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for turn in turns:
        history.append({"role": "user", "content": str(turn.get("user", ""))})
        history.append({"role": "assistant", "content": str(turn.get("assistant_text", ""))})
    return history


def new_transcript(
    *,
    version: str,
    provider: str,
    model: str,
    prompt_path: Path,
    tools_path: Path,
    history_window: int,
    max_tool_rounds: int,
) -> tuple[dict[str, Any], Path]:
    artifact = build_artifact_version(version, prompt_path, tools_path)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([safe_slug(version), safe_slug(provider), timestamp])
    path = TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"
    transcript: dict[str, Any] = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact),
        "provider": provider,
        "model": model,
        "system_prompt": str(prompt_path),
        "tools": str(tools_path),
        "history_window": history_window,
        "max_tool_rounds": max_tool_rounds,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }
    write_transcript(path, transcript)
    return transcript, path


def reset_conversation() -> None:
    for key in (
        "conversation",
        "history",
        "transcript",
        "transcript_path",
        "transcript_config",
        "demo_mode",
    ):
        st.session_state.pop(key, None)


def ensure_session(config_key: str) -> None:
    if st.session_state.get("transcript_config") not in {None, config_key}:
        reset_conversation()
    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("demo_mode", False)
    st.session_state["transcript_config"] = config_key


def load_demo_transcript() -> None:
    reset_conversation()
    payload = read_json(SAMPLE_TRANSCRIPT)
    turns = list(payload.get("turns", []))
    st.session_state["conversation"] = turns
    st.session_state["history"] = history_from_turns(turns)
    st.session_state["transcript"] = payload
    st.session_state["transcript_path"] = SAMPLE_TRANSCRIPT
    st.session_state["transcript_config"] = "demo"
    st.session_state["demo_mode"] = True


def load_saved_transcript(path: Path) -> None:
    resolved_path = path.resolve()
    if resolved_path.parent != TRANSCRIPTS_DIR.resolve():
        raise ValueError("Đường dẫn transcript không hợp lệ.")

    payload = read_json(resolved_path)
    turns = payload.get("turns", [])
    if not isinstance(turns, list):
        raise ValueError("Transcript không chứa danh sách lượt hội thoại hợp lệ.")

    provider = str(payload.get("provider", "openrouter"))
    if provider not in PROVIDER_META:
        provider = "openrouter"
    version = str(payload.get("version", "v0"))
    if version not in VERSION_OPTIONS:
        version = "v0"

    saved_prompt = str(payload.get("system_prompt", "")).replace("\\", "/")
    saved_tools = str(payload.get("tools", "")).replace("\\", "/")
    snapshot_marker = f"/versions/{version}/"
    use_snapshot = (
        snapshot_marker in saved_prompt
        and snapshot_marker in saved_tools
        and available_snapshot(version)
    )
    prompt_path, tools_path, _ = artifact_paths(version, use_snapshot)
    model = str(payload.get("model") or PROVIDER_META[provider]["default_model"])
    history_window = max(1, min(12, int(payload.get("history_window", 5))))
    max_tool_rounds = max(1, min(8, int(payload.get("max_tool_rounds", 4))))

    reset_conversation()
    st.session_state["provider_choice"] = provider
    st.session_state["version_choice"] = version
    st.session_state["snapshot_choice"] = use_snapshot
    st.session_state["model_override"] = model
    st.session_state["history_window"] = history_window
    st.session_state["max_tool_rounds"] = max_tool_rounds
    st.session_state["conversation"] = list(turns)
    st.session_state["history"] = history_from_turns(turns)
    st.session_state["transcript"] = payload
    st.session_state["transcript_path"] = resolved_path
    st.session_state["transcript_config"] = session_config_key(
        provider=provider,
        model=model,
        version=version,
        use_snapshot=use_snapshot,
        prompt_path=prompt_path,
        tools_path=tools_path,
        history_window=history_window,
        max_tool_rounds=max_tool_rounds,
    )
    st.session_state["demo_mode"] = False


def inject_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --paper: #f7f5ef;
            --paper-deep: #eeeae1;
            --ink: #2f2c28;
            --muted: #777168;
            --line: rgba(47, 44, 40, 0.13);
            --accent: #c96f50;
            --accent-soft: #f0ddd3;
            --sage: #68776a;
            --danger: #9a4e40;
            --serif: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
            --sans: "Avenir Next", Avenir, "Segoe UI", sans-serif;
            --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        }

        html, body, [class*="css"] { font-family: var(--sans); }
        .stApp { background: var(--paper); color: var(--ink); }
        [data-testid="stHeader"] { background: rgba(247,245,239,.82); backdrop-filter: blur(12px); }
        [data-testid="stToolbar"] { right: 1rem; }
        #MainMenu, footer { visibility: hidden; }
        .block-container { max-width: 1480px; padding-top: 3.5rem; padding-bottom: 4rem; }

        [data-testid="stSidebar"] { background: #eae6dc; border-right: 1px solid var(--line); }
        [data-testid="stSidebar"] > div:first-child { padding-top: 1.2rem; }
        [data-testid="stSidebar"] .stButton button { width: 100%; }
        [data-testid="stSidebar"] hr { border-color: var(--line); }

        h1, h2, h3 { font-family: var(--serif) !important; letter-spacing: -.025em; color: var(--ink); }
        p { color: var(--ink); }
        code, pre { font-family: var(--mono) !important; }

        .brand-lockup { display:flex; align-items:center; gap:.75rem; margin:.1rem 0 1.45rem; }
        .brand-mark { width:34px; height:34px; display:grid; place-items:center; border:1px solid var(--ink); border-radius:50%; font-family:var(--serif); font-size:18px; }
        .brand-name { font-family:var(--serif); font-size:20px; letter-spacing:-.02em; line-height:1; }
        .brand-kicker { color:var(--muted); font-size:10px; letter-spacing:.14em; text-transform:uppercase; margin-top:4px; }

        .workspace-header { display:flex; justify-content:space-between; align-items:flex-end; gap:2rem; border-bottom:1px solid var(--line); padding:0 0 1rem; margin-bottom:1.25rem; }
        .workspace-eyebrow { color:var(--accent); font-size:10px; letter-spacing:.16em; text-transform:uppercase; font-weight:700; margin-bottom:.35rem; }
        .workspace-title { font-family:var(--serif); font-size:clamp(30px,3.2vw,48px); letter-spacing:-.045em; line-height:.98; }
        .workspace-meta { text-align:right; color:var(--muted); font-size:12px; line-height:1.55; }
        .artifact-pill { display:inline-block; max-width:360px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; border:1px solid var(--line); border-radius:999px; padding:.32rem .62rem; color:var(--ink); background:rgba(255,255,255,.28); font-family:var(--mono); font-size:10px; }

        .hero-empty { min-height:250px; display:flex; flex-direction:column; justify-content:center; padding:2rem clamp(.5rem,7vw,6.5rem) 1.4rem; }
        .hero-empty h1 { font-size:clamp(40px,4.6vw,62px); line-height:.98; margin:0; max-width:780px; text-wrap:balance; word-break:normal; overflow-wrap:normal; }
        .hero-empty p { color:var(--muted); font-size:15px; max-width:580px; margin:1.2rem 0 0; line-height:1.65; }
        .hairline-label { display:flex; gap:.7rem; align-items:center; color:var(--muted); text-transform:uppercase; letter-spacing:.14em; font-size:9px; margin:1.5rem 0 .65rem; }
        .hairline-label:after { content:""; flex:1; height:1px; background:var(--line); }

        .st-key-trace-panel { border-left:1px solid var(--line); padding-left:1.25rem; min-height:410px; position:sticky; top:1rem; max-height:calc(100vh - 2rem); overflow-y:auto; scrollbar-width:thin; }
        .panel-kicker { color:var(--muted); font-size:9px; letter-spacing:.15em; text-transform:uppercase; margin-bottom:.35rem; }
        .panel-title { font-family:var(--serif); font-size:23px; margin-bottom:.35rem; }
        .panel-copy { color:var(--muted); font-size:12px; line-height:1.55; margin-bottom:1.1rem; }
        .trace-current { border-top:1px solid var(--line); border-bottom:1px solid var(--line); padding:.85rem 0; margin:.2rem 0 1rem; }
        .trace-current-head { display:flex; justify-content:space-between; align-items:baseline; gap:.75rem; }
        .trace-current-label { color:var(--accent); font-size:9px; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
        .trace-current-turn { font-family:var(--serif); color:var(--ink); font-size:18px; }
        .trace-current-question { color:var(--ink); font-size:12px; line-height:1.5; margin-top:.45rem; text-wrap:pretty; }
        .trace-current-meta { color:var(--muted); font-size:10px; margin-top:.5rem; }
        .trace-history { margin-top:1rem; padding-top:.75rem; border-top:1px solid var(--line); }
        .trace-history-title { color:var(--muted); font-size:9px; letter-spacing:.12em; text-transform:uppercase; margin-bottom:.35rem; }
        .trace-history-row { display:flex; justify-content:space-between; gap:.75rem; padding:.45rem 0; color:var(--muted); font-size:10px; border-bottom:1px solid rgba(62,58,51,.08); }
        .trace-history-row strong { color:var(--ink); font-weight:600; }
        .trace-empty { border-top:1px solid var(--line); padding-top:.9rem; }
        .trace-placeholder { display:grid; grid-template-columns:22px 1fr; gap:.65rem; padding:.75rem 0; border-bottom:1px solid var(--line); color:var(--muted); font-size:12px; }
        .trace-index { font-family:var(--mono); font-size:10px; color:var(--accent); padding-top:2px; }

        .turn-meta { display:flex; flex-wrap:wrap; gap:.45rem; margin:.55rem 0 1.1rem; }
        .meta-chip { color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:.22rem .5rem; font-size:10px; }
        .meta-chip.accent { color:var(--accent); border-color:rgba(201,111,80,.34); background:rgba(201,111,80,.06); }
        .user-question-block { display:flex; flex-direction:column; align-items:flex-end; margin:1.6rem 0 1.8rem; }
        .message-role { color:var(--ink); font-size:11px; font-weight:700; letter-spacing:.07em; margin-bottom:.45rem; }
        .message-role span { color:var(--accent); font-family:var(--mono); font-size:9px; font-weight:400; margin-left:.45rem; }
        .user-question-card { max-width:78%; background:var(--paper-deep); border-radius:18px 18px 4px 18px; padding:.9rem 1.1rem; color:var(--ink); font-size:15px; line-height:1.58; white-space:pre-wrap; text-wrap:pretty; }
        .assistant-role { display:flex; align-items:center; gap:.7rem; color:var(--accent); font-size:11px; font-weight:700; letter-spacing:.07em; margin:.2rem 0 .15rem; }
        .assistant-role:after { content:""; flex:1; height:1px; background:var(--line); }
        .turn-divider { height:1px; background:var(--line); margin:1.5rem 0 2rem; }

        [data-testid="stChatMessage"] { background:transparent; padding:.85rem .25rem; border-radius:0; gap:0; }
        [data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] { display:none; }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { max-width:820px; }
        [data-testid="stChatMessage"] p { line-height:1.72; font-size:15px; }
        [data-testid="stTextArea"] textarea { background:rgba(255,255,255,.58); border:1px solid var(--line); border-radius:16px; color:var(--ink); box-shadow:0 12px 40px rgba(55,49,41,.07); min-height:76px; }
        [data-testid="stTextArea"] textarea:focus { border-color:rgba(201,111,80,.5); box-shadow:0 12px 40px rgba(55,49,41,.07); }

        .status-line { display:flex; justify-content:space-between; gap:.7rem; align-items:center; border-top:1px solid var(--line); padding:.7rem 0; font-size:11px; }
        .status-dot { width:7px; height:7px; display:inline-block; border-radius:50%; margin-right:.45rem; background:var(--sage); }
        .status-dot.offline { background:var(--accent); }
        .status-dot.error { background:var(--danger); }
        .status-copy { color:var(--muted); }

        .metric-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1px; background:var(--line); border:1px solid var(--line); margin:1rem 0 1.4rem; }
        .metric-cell { background:var(--paper); padding:1rem; min-height:96px; }
        .metric-label { color:var(--muted); text-transform:uppercase; letter-spacing:.11em; font-size:9px; }
        .metric-value { font-family:var(--serif); font-size:34px; margin-top:.3rem; }
        .metric-note { color:var(--muted); font-size:10px; margin-top:.25rem; }

        .version-strip { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.75rem; margin:.9rem 0 1.4rem; }
        .version-slot { border-top:2px solid var(--ink); padding:.7rem 0; min-height:92px; }
        .version-slot.pending { border-top-style:dotted; border-color:var(--muted); opacity:.62; }
        .version-name { font-family:var(--serif); font-size:24px; }
        .version-detail { color:var(--muted); font-size:11px; line-height:1.5; }

        .tool-shelf { display:flex; flex-wrap:wrap; gap:.35rem; margin:.45rem 0 1rem; }
        .tool-token { border:1px solid var(--line); border-radius:999px; padding:.23rem .48rem; font-size:9px; color:var(--muted); }
        .tool-token.ready { color:var(--sage); }
        .tool-token.placeholder { border-style:dashed; }
        .tool-catalog { border-top:1px solid var(--line); margin-top:1.1rem; }
        .tool-catalog-row { display:grid; grid-template-columns:42px minmax(150px,.75fr) minmax(280px,2fr) 112px; gap:1rem; align-items:start; padding:1rem 0; border-bottom:1px solid var(--line); }
        .tool-catalog-index { color:var(--accent); font-family:var(--mono); font-size:10px; padding-top:3px; }
        .tool-catalog-name { font-family:var(--mono); font-size:12px; color:var(--ink); overflow-wrap:anywhere; }
        .tool-catalog-desc { color:var(--ink); font-size:13px; line-height:1.5; }
        .tool-catalog-args { color:var(--muted); font-size:10px; margin-top:.32rem; }
        .tool-catalog-state { color:var(--sage); font-size:10px; text-transform:uppercase; letter-spacing:.08em; padding-top:3px; }
        .tool-catalog-state.runtime-only { color:var(--accent); }
        .tool-catalog-state.placeholder { color:var(--muted); }
        .demo-note { background:var(--paper-deep); border:1px solid var(--line); color:var(--muted); padding:.85rem 1rem; font-size:12px; line-height:1.55; margin:.2rem 0 1rem; }

        .stButton button { border:1px solid var(--line); border-radius:999px; background:transparent; color:var(--ink); min-height:2.35rem; height:auto; padding:.58rem .9rem; transition:all .16s ease; }
        .stButton button p { white-space:normal; overflow:visible; }
        .stButton button:hover { border-color:var(--accent); color:var(--accent); background:rgba(201,111,80,.04); }
        .stButton button[kind="primary"] { background:var(--ink); color:var(--paper); border-color:var(--ink); }
        .stButton button[kind="primary"] p { color:var(--paper) !important; }
        div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input { background:rgba(255,255,255,.33); border-color:var(--line); }
        [data-testid="stExpander"] { border:0; border-top:1px solid var(--line); border-radius:0; background:transparent; }
        [data-testid="stAlert"] { background:var(--paper-deep); border:1px solid var(--line); color:var(--ink); }
        [data-baseweb="tab-list"] { gap:1.2rem; border-bottom:1px solid var(--line); }
        [data-baseweb="tab"] { padding-left:0; padding-right:0; }
        [data-baseweb="tab-highlight"] { background-color:var(--accent); }

        @media (max-width: 900px) {
            .workspace-header { align-items:flex-start; flex-direction:column; }
            .workspace-meta { text-align:left; }
            .st-key-trace-panel { border-left:0; border-top:1px solid var(--line); padding:1.4rem 0 0; min-height:auto; position:static; max-height:none; overflow:visible; }
            .metric-grid, .version-strip { grid-template-columns:repeat(2,minmax(0,1fr)); }
            .tool-catalog-row { grid-template-columns:32px 1fr; gap:.45rem .8rem; }
            .tool-catalog-desc, .tool-catalog-state { grid-column:2; }
            .user-question-card { max-width:92%; }
            .hero-empty { padding-left:.2rem; padding-right:.2rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar(
    runs: list[dict[str, Any]],
) -> tuple[str, str, str, bool, int, int, Path, Path, str]:
    st.sidebar.markdown(
        """
        <div class="brand-lockup">
          <div class="brand-mark">N</div>
          <div><div class="brand-name">Bàn Nghiên cứu</div><div class="brand-kicker">Trợ lý dựa trên bằng chứng</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.sidebar.button("Nghiên cứu mới", type="primary", width="stretch"):
        reset_conversation()
        st.rerun()

    saved_transcripts = discover_transcripts()
    with st.sidebar.expander(f"Lịch sử phiên · {len(saved_transcripts)}"):
        if saved_transcripts:
            selected_session = st.selectbox(
                "Phiên đã lưu",
                range(len(saved_transcripts)),
                format_func=lambda index: saved_transcripts[index]["label"],
                label_visibility="collapsed",
                key="saved_transcript_selector",
            )
            record = saved_transcripts[selected_session]
            payload = record["payload"]
            st.caption(
                f"{payload.get('version', '—')} · {payload.get('provider', '—')} · "
                f"{payload.get('model', '—')}"
            )
            active_path = st.session_state.get("transcript_path")
            is_active = bool(active_path) and Path(active_path).resolve() == record["path"].resolve()
            if is_active:
                st.caption("Đang mở phiên này. Lượt mới sẽ tiếp tục được lưu vào cùng transcript.")
            if st.button("Mở lại phiên", width="stretch", key="open_saved_transcript"):
                try:
                    load_saved_transcript(record["path"])
                except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                    st.error(f"Không thể mở transcript: {exc}")
                else:
                    st.rerun()
        else:
            st.caption("Chưa có phiên nào. Phiên đầu tiên sẽ xuất hiện sau khi bạn gửi câu hỏi.")
        st.caption("Các lượt mới được ghi tự động sau mỗi câu trả lời.")

    st.session_state.setdefault("provider_choice", "openrouter")
    provider = st.sidebar.selectbox(
        "Nhà cung cấp mô hình",
        list(PROVIDER_META),
        format_func=lambda value: PROVIDER_META[value]["label"],
        key="provider_choice",
    )
    default_version = "v1" if available_snapshot("v1") else "v0"
    st.session_state.setdefault("version_choice", default_version)
    version = st.sidebar.selectbox(
        "Phiên bản artifact",
        VERSION_OPTIONS,
        key="version_choice",
    )
    snapshot_exists = available_snapshot(version)
    if "snapshot_choice" not in st.session_state:
        st.session_state["snapshot_choice"] = snapshot_exists
    elif not snapshot_exists:
        st.session_state["snapshot_choice"] = False
    use_snapshot = st.sidebar.toggle(
        "Dùng snapshot đã lưu",
        disabled=not snapshot_exists,
        help="Dùng artifacts/versions/<version> khi snapshot tương ứng tồn tại.",
        key="snapshot_choice",
    )
    prompt_path, tools_path, artifact_source = artifact_paths(version, use_snapshot)

    st.session_state.setdefault("model_override", "")
    model_override = st.sidebar.text_input(
        "Mô hình tùy chọn",
        placeholder=PROVIDER_META[provider]["default_model"],
        help="Để trống để dùng mô hình mặc định của nhà cung cấp.",
        key="model_override",
    )
    model = model_override.strip() or PROVIDER_META[provider]["default_model"]

    with st.sidebar.expander("Cấu hình phiên chạy"):
        st.session_state.setdefault("history_window", 5)
        st.session_state.setdefault("max_tool_rounds", 4)
        history_window = st.slider("Số cặp hội thoại được nhớ", 1, 12, key="history_window")
        max_tool_rounds = st.slider("Số vòng công cụ tối đa", 1, 8, key="max_tool_rounds")
        st.caption(artifact_source)
        st.code(str(prompt_path.relative_to(ROOT)), language=None)

    key_name = PROVIDER_META[provider]["key"]
    provider_ready = bool(os.getenv(key_name))
    readiness_class = "" if provider_ready else "offline"
    readiness_text = "Đã phát hiện API key" if provider_ready else f"Thêm {key_name} vào .env"
    st.sidebar.markdown(
        f"""
        <div class="status-line">
          <span><span class="status-dot {readiness_class}"></span>{esc(readiness_text)}</span>
          <span class="status-copy">{len(runs)} run đã lưu</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("<div class='panel-kicker' style='margin-top:1rem'>Công cụ trong runtime</div>", unsafe_allow_html=True)
    tokens = []
    tool_names = list(TOOL_FUNCTIONS)
    for name in declared_tool_names(tools_path):
        if name not in tool_names:
            tool_names.append(name)
    for name in tool_names:
        state = "ready" if name in TOOL_FUNCTIONS else "placeholder"
        title = TOOL_LABELS.get(name, "Công cụ đang chờ triển khai")
        tokens.append(f'<span class="tool-token {state}" title="{esc(title)}">{esc(name)}</span>')
    st.sidebar.markdown(f"<div class='tool-shelf'>{''.join(tokens)}</div>", unsafe_allow_html=True)

    latest = latest_runs_by_version(runs).get(version)
    if latest:
        summary = latest.get("summary", {})
        st.sidebar.caption(f"Bằng chứng {version} mới nhất")
        left, right = st.sidebar.columns(2)
        left.metric("Tình huống", percent(summary.get("case_accuracy")))
        right.metric("Định tuyến", percent(summary.get("tool_routing_accuracy")))
    else:
        st.sidebar.info(f"Chưa có run {version}. Vị trí này sẽ để trống cho tới khi có run thật.")

    if SAMPLE_TRANSCRIPT.exists() and st.sidebar.button("Tải demo ngoại tuyến", width="stretch"):
        load_demo_transcript()
        st.rerun()

    st.sidebar.caption("UI không hiển thị secret. Lỗi công cụ và nhà cung cấp vẫn được giữ lại làm bằng chứng.")
    return (
        provider,
        model,
        version,
        use_snapshot,
        history_window,
        max_tool_rounds,
        prompt_path,
        tools_path,
        artifact_source,
    )


def render_workspace_header(
    *,
    artifact_version: str,
    provider: str,
    model: str,
    artifact_source: str,
) -> None:
    st.markdown(
        f"""
        <div class="workspace-header">
          <div>
            <div class="workspace-eyebrow">Không gian nghiên cứu trực tiếp</div>
            <div class="workspace-title">Để bằng chứng tự lên tiếng.</div>
          </div>
          <div class="workspace-meta">
            <div>{esc(PROVIDER_META[provider]['label'])} · {esc(model)}</div>
            <div>{esc(artifact_source)}</div>
            <div class="artifact-pill" title="{esc(artifact_version)}">{esc(artifact_version)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_conversation() -> str | None:
    st.markdown(
        """
        <div class="hero-empty">
          <h1>Hôm nay bạn muốn nghiên cứu điều gì?</h1>
          <p>Hãy tra cứu thông tin mới, kiểm tra một nguồn hoặc thử ranh giới công cụ. Mọi lời gọi, tham số, kết quả và lỗi đều được gắn với câu trả lời.</p>
        </div>
        <div class="hairline-label">Thử một tình huống thật</div>
        """,
        unsafe_allow_html=True,
    )
    prompts = [
        ("Tin tức AI hôm nay", "Tin tức AI hôm nay có gì nổi bật?"),
        ("Tóm tắt một URL cụ thể", "Tóm tắt bài này giúp mình: https://openai.com/blog/gpt-5"),
        ("Kiểm tra ranh giới gửi", "Gửi digest lên Telegram giúp mình"),
    ]
    cols = st.columns(3)
    selected: str | None = None
    for index, (label, prompt) in enumerate(prompts):
        if cols[index].button(label, key=f"starter-{index}", width="stretch"):
            selected = prompt
    return selected


def render_turn(turn: dict[str, Any]) -> None:
    turn_index = turn.get("turn_index", "—")
    st.markdown(
        f'<div class="user-question-block">'
        f'<div class="message-role">Bạn hỏi <span>Lượt {esc(turn_index)}</span></div>'
        f'<div class="user-question-card">{esc(turn.get("user", ""))}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="assistant-role">Agent trả lời</div>', unsafe_allow_html=True)
    with st.chat_message("assistant"):
        error = turn.get("error")
        if error:
            st.error(str(error))
        else:
            answer = str(turn.get("assistant_text") or "Không nhận được câu trả lời cuối cùng.")
            st.markdown(answer)

    events = turn.get("tool_events", []) or []
    rounds = turn.get("rounds", []) or []
    status_key = str(turn.get("status", "unknown"))
    status = STATUS_LABELS.get(status_key, status_key.replace("_", " "))
    chips = [f'<span class="meta-chip accent">{esc(status)}</span>']
    chips.append(f'<span class="meta-chip">{len(rounds)} vòng</span>')
    chips.append(f'<span class="meta-chip">{len(events)} lần gọi công cụ</span>')
    st.markdown(f"<div class='turn-meta'>{''.join(chips)}</div>", unsafe_allow_html=True)
    st.markdown('<div class="turn-divider"></div>', unsafe_allow_html=True)


def _render_trace_panel_content(conversation: list[dict[str, Any]]) -> None:
    st.markdown(
        """
        <div class="panel-kicker">Dấu vết thực thi</div>
        <div class="panel-title">Agent đã làm gì?</div>
        <div class="panel-copy">Các lời gọi được nhóm theo từng vòng của mô hình. Bạn luôn có thể xem tham số và kết quả gốc.</div>
        """,
        unsafe_allow_html=True,
    )

    if not conversation:
        st.markdown(
            """
            <div class="trace-empty">
              <div class="trace-placeholder"><span class="trace-index">01</span><span>Mô hình quyết định có cần dùng công cụ hay không.</span></div>
              <div class="trace-placeholder"><span class="trace-index">02</span><span>Tham số và kết quả công cụ xuất hiện tại đây.</span></div>
              <div class="trace-placeholder"><span class="trace-index">03</span><span>Câu trả lời cuối luôn được liên kết với bằng chứng.</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    turn = conversation[-1]
    status_key = str(turn.get("status", "unknown"))
    status = STATUS_LABELS.get(status_key, status_key.replace("_", " "))
    rounds = turn.get("rounds", []) or []
    events = turn.get("tool_events", []) or []
    turn_index = turn.get("turn_index", len(conversation))
    st.markdown(
        f'<div class="trace-current">'
        f'<div class="trace-current-head"><span class="trace-current-label">Dấu vết hiện tại</span>'
        f'<span class="trace-current-turn">Lượt {esc(turn_index)}</span></div>'
        f'<div class="trace-current-question">{esc(turn.get("user", ""))}</div>'
        f'<div class="trace-current-meta">{esc(status)} · {len(rounds)} vòng · {len(events)} lần gọi công cụ</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if not rounds:
        st.info("Không ghi nhận vòng công cụ nào. Mô hình có thể đã trả lời trực tiếp hoặc nhà cung cấp gặp lỗi trước khi phản hồi.")

    for round_record in rounds:
        calls = round_record.get("tool_calls", []) or []
        st.markdown(f"**Vòng {round_record.get('round', '—')}**  ·  {len(calls)} lời gọi")
        if not calls:
            st.caption("Trả lời trực tiếp · không chọn công cụ")
        for event_index, event in enumerate(round_record.get("tool_results", []) or [], start=1):
            state, label = tool_event_state(event)
            name = str(event.get("tool", "công cụ không xác định"))
            with st.expander(f"{event_index:02d}  {name} · {label}", expanded=state != "complete"):
                st.caption(TOOL_LABELS.get(name, "Thực thi công cụ"))
                st.markdown(f"_{result_preview(event)}_")
                args_tab, result_tab = st.tabs(["Tham số", "Kết quả"])
                with args_tab:
                    st.json(event.get("args", {}), expanded=True)
                with result_tab:
                    st.json(event.get("result", {}), expanded=False)

    if len(conversation) > 1:
        history_rows = []
        for previous_turn in reversed(conversation[:-1]):
            previous_events = previous_turn.get("tool_events", []) or []
            tool_names = ", ".join(str(event.get("tool", "—")) for event in previous_events) or "Không dùng công cụ"
            history_rows.append(
                f'<div class="trace-history-row">'
                f'<strong>Lượt {esc(previous_turn.get("turn_index", "—"))}</strong>'
                f'<span>{esc(tool_names)}</span>'
                f'</div>'
            )
        st.markdown(
            f'<div class="trace-history"><div class="trace-history-title">Các lượt trước</div>'
            f'{"".join(history_rows)}</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.get("transcript_path"):
        path = Path(st.session_state["transcript_path"])
        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            relative = path
        st.caption(f"Transcript · {relative}")


def render_trace_panel(conversation: list[dict[str, Any]]) -> None:
    with st.container(key="trace-panel"):
        _render_trace_panel_content(conversation)


def render_composer() -> str | None:
    with st.form("research-composer", clear_on_submit=True, border=False):
        prompt = st.text_area(
            "Yêu cầu nghiên cứu",
            label_visibility="collapsed",
            placeholder="Hãy hỏi agent nghiên cứu…",
            height=78,
        )
        submitted = st.form_submit_button("Gửi", type="primary", width="content")
    return prompt.strip() if submitted and prompt.strip() else None


def render_chat_tab() -> str | None:
    conversation = st.session_state.get("conversation", [])
    main_col, trace_col = st.columns([1.72, 0.78], gap="large")
    selected_prompt: str | None = None
    with main_col:
        if not conversation:
            selected_prompt = render_empty_conversation()
        else:
            if st.session_state.get("demo_mode"):
                st.markdown(
                    '<div class="demo-note">Đã tải demo ngoại tuyến. Đây là dữ liệu mẫu có nhãn mock rõ ràng, không phải phiên chạy nhà cung cấp trực tiếp.</div>',
                    unsafe_allow_html=True,
                )
            for turn in conversation:
                render_turn(turn)
        composed_prompt = render_composer()
    with trace_col:
        render_trace_panel(conversation)
    return composed_prompt or selected_prompt


def render_metric_grid(run: dict[str, Any] | None) -> None:
    summary = (run or {}).get("summary", {})
    cells = []
    for key, label in METRICS:
        value = percent(summary.get(key))
        cells.append(
            f'<div class="metric-cell"><div class="metric-label">{esc(label)}</div>'
            f'<div class="metric-value">{esc(value)}</div>'
            '<div class="metric-note">Bằng chứng mới nhất đã chọn</div></div>'
        )
    st.markdown(f"<div class='metric-grid'>{''.join(cells)}</div>", unsafe_allow_html=True)


def render_tool_catalog(tools_path: Path) -> None:
    try:
        declarations = load_tool_declarations(tools_path)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        st.error(f"Không thể đọc danh mục công cụ: {exc}")
        return

    declared_by_name = {str(item.get("name")): item for item in declarations if item.get("name")}
    tool_names = list(TOOL_FUNCTIONS)
    for name in declared_by_name:
        if name not in tool_names:
            tool_names.append(name)

    st.markdown("### Danh mục công cụ")
    st.caption(
        f"Runtime hiện có {len(TOOL_FUNCTIONS)} công cụ; artifact đang chọn khai báo "
        f"{len(declared_by_name)} công cụ. Dấu * là tham số bắt buộc trong artifact."
    )

    rows: list[str] = []
    for index, name in enumerate(tool_names, start=1):
        item = declared_by_name.get(name, {})
        description = TOOL_LABELS.get(name, str(item.get("description", "Chưa có mô tả.")))
        required = set(item.get("parameters", {}).get("required", []) or [])
        if name in TOOL_FUNCTIONS:
            parameter_names = list(inspect.signature(TOOL_FUNCTIONS[name]).parameters)
        else:
            parameter_names = list(item.get("parameters", {}).get("properties", {}))
        parameter_html = ", ".join(
            f"<code>{esc(parameter)}{'*' if parameter in required else ''}</code>"
            for parameter in parameter_names
        ) or "Không có"
        connected = name in TOOL_FUNCTIONS
        declared = name in declared_by_name
        if connected and declared:
            state_class, state_label = "", "Đã khai báo"
        elif connected:
            state_class, state_label = "runtime-only", "Có runtime"
        else:
            state_class, state_label = "placeholder", "Placeholder"
        rows.append(
            f'<div class="tool-catalog-row">'
            f'<div class="tool-catalog-index">{index:02d}</div>'
            f'<div class="tool-catalog-name">{esc(name)}</div>'
            f'<div class="tool-catalog-desc">{esc(description)}'
            f'<div class="tool-catalog-args">Tham số: {parameter_html}</div></div>'
            f'<div class="tool-catalog-state {state_class}">{state_label}</div>'
            f'</div>'
        )
    st.markdown(f'<div class="tool-catalog">{"".join(rows)}</div>', unsafe_allow_html=True)


def render_version_strip(runs: list[dict[str, Any]]) -> None:
    latest = latest_runs_by_version(runs)
    slots = []
    for version in ("v0", "v1", "v2", "v3"):
        run = latest.get(version)
        if run:
            summary = run.get("summary", {})
            slots.append(
                f'<div class="version-slot"><div class="version-name">{version}</div>'
                f'<div class="version-detail">{percent(summary.get("case_accuracy"))} độ chính xác<br>'
                f'{esc(run.get("provider", "—"))} · {esc(run.get("suite", "—"))}</div></div>'
            )
        else:
            slots.append(
                f'<div class="version-slot pending"><div class="version-name">{version}</div>'
                '<div class="version-detail">Đang chờ run thật<br>Không dùng dữ liệu cải thiện giả</div></div>'
            )
    st.markdown(f"<div class='version-strip'>{''.join(slots)}</div>", unsafe_allow_html=True)


def scenario_rows(runs: list[dict[str, Any]], case_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for run in reversed(runs):
        for case in run.get("results", []) or []:
            if str(case.get("id")) != case_id:
                continue
            result = case.get("result", {}) or {}
            calls = result.get("actual_tool_calls", []) or []
            rows.append(
                {
                    "phiên bản": run.get("version"),
                    "bộ test": run.get("suite"),
                    "đạt": result.get("passed"),
                    "luồng công cụ": " → ".join(str(item.get("name", "?")) for item in calls) or "không dùng công cụ",
                    "định tuyến": result.get("routing_correct"),
                    "tham số": result.get("args_correct"),
                    "sai lệch": result.get("observed_mismatch") or "—",
                    "run": run.get("run_id"),
                }
            )
    return rows


def render_evidence_tab(
    runs: list[dict[str, Any]],
    selected_version: str,
    active_prompt_hash: str,
    active_tools_hash: str,
) -> None:
    st.markdown("### Bằng chứng theo phiên bản")
    st.caption("Chỉ sử dụng run JSON thật. Phiên bản chưa chạy sẽ để trống cho tới thí nghiệm tối ưu tiếp theo.")
    render_version_strip(runs)

    if not runs:
        render_metric_grid(None)
        st.warning("Không tìm thấy run JSON trong runs/. Hãy chạy baseline evaluator để tạo dữ liệu cho khu vực này.")
        return

    run_labels = {
        str(run.get("run_id", Path(run.get("_path", "run")).stem)): run
        for run in runs
    }
    selected_id = st.selectbox(
        "Run bằng chứng",
        list(run_labels),
        index=next((i for i, value in enumerate(run_labels) if run_labels[value].get("version") == selected_version), 0),
    )
    selected = run_labels[selected_id]
    render_metric_grid(selected)

    if selected.get("version") == selected_version:
        prompt_matches = selected.get("prompt_hash") == active_prompt_hash
        tools_match = selected.get("tools_hash") == active_tools_hash
        if not (prompt_matches and tools_match):
            st.warning(
                f"Run {selected.get('run_id', selected_id)} dùng artifact cũ và không khớp snapshot {selected_version} hiện tại. "
                f"Hãy chạy lại eval {selected_version} trước khi dùng metric này làm bằng chứng cho phiên bản mới."
            )

    summary = selected.get("summary", {})
    meta_cols = st.columns(4)
    meta_cols[0].metric("Đã đo", f"{summary.get('measured_cases', '—')}/{summary.get('total_cases', '—')}")
    meta_cols[1].metric("Lỗi nhà cung cấp", summary.get("provider_error_cases", "—"))
    meta_cols[2].metric("Hash prompt", compact_hash(selected.get("prompt_hash")))
    meta_cols[3].metric("Hash công cụ", compact_hash(selected.get("tools_hash")))

    st.markdown("#### Cùng một tình huống qua nhiều phiên bản")
    case_ids = sorted(
        {
            str(case.get("id"))
            for run in runs
            for case in (run.get("results", []) or [])
            if case.get("id")
        }
    )
    if case_ids:
        case_id = st.selectbox("Tình huống", case_ids)
        rows = scenario_rows(runs, case_id)
        st.dataframe(rows, width="stretch", hide_index=True)
        if len({row["phiên bản"] for row in rows}) < 2:
            st.caption("Hiện chỉ có một phiên bản chứa tình huống này. Các run sau sẽ tự động xuất hiện trong cùng bảng.")

    st.markdown("#### Kiểm tra từng tình huống")
    results = selected.get("results", []) or []
    for case in results:
        result = case.get("result", {}) or {}
        state = "đạt" if result.get("passed") else "cần xem lại"
        with st.expander(f"{case.get('id', 'Tình huống chưa đặt tên')} · {state}"):
            request_text = case.get("input") or "Tình huống đa lượt"
            st.markdown(f"**Yêu cầu**  \n\n{request_text}")
            left, right = st.columns(2)
            with left:
                st.caption("Kỳ vọng")
                st.json(case.get("expect", {}), expanded=False)
            with right:
                st.caption("Quan sát thực tế")
                st.json(
                    {
                        "tool_calls": result.get("actual_tool_calls", []),
                        "mismatch": result.get("observed_mismatch"),
                        "failures": result.get("failures", []),
                    },
                    expanded=False,
                )


def execute_prompt(
    prompt: str,
    *,
    provider_name: str,
    model: str,
    version: str,
    prompt_path: Path,
    tools_path: Path,
    history_window: int,
    max_tool_rounds: int,
) -> None:
    if st.session_state.get("demo_mode"):
        reset_conversation()
        st.session_state["conversation"] = []
        st.session_state["history"] = []
        st.session_state["demo_mode"] = False

    system_prompt = prompt_path.read_text(encoding="utf-8")
    declarations = load_tool_declarations(tools_path)
    tools = to_openai_tools(declarations)

    if "transcript" not in st.session_state:
        transcript, transcript_path = new_transcript(
            version=version,
            provider=provider_name,
            model=model,
            prompt_path=prompt_path,
            tools_path=tools_path,
            history_window=history_window,
            max_tool_rounds=max_tool_rounds,
        )
        st.session_state["transcript"] = transcript
        st.session_state["transcript_path"] = transcript_path

    transcript = st.session_state["transcript"]
    turn_index = len(transcript.get("turns", [])) + 1
    turn_record: dict[str, Any] = {
        "turn_index": turn_index,
        "started_at": now_iso(),
        "user": prompt,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
    }

    messages = [
        {"role": "system", "content": system_prompt},
        *trim_history(st.session_state.get("history", []), history_window),
        {"role": "user", "content": prompt},
    ]

    try:
        provider = make_provider(provider_name)
        result = run_model_tool_loop(
            provider=provider,
            messages=messages,
            tools=tools,
            model=model,
            max_tool_rounds=max_tool_rounds,
        )
        turn_record.update(result)
        answer = str(result.get("assistant_text", ""))
        st.session_state["history"].append({"role": "user", "content": prompt})
        st.session_state["history"].append({"role": "assistant", "content": answer})
    except Exception as exc:  # Provider/tool errors are evidence and belong in the transcript.
        turn_record.update(
            {
                "status": "provider_error",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )

    turn_record["ended_at"] = now_iso()
    transcript.setdefault("turns", []).append(turn_record)
    st.session_state["conversation"].append(turn_record)
    write_transcript(Path(st.session_state["transcript_path"]), transcript)


def main() -> None:
    st.set_page_config(
        page_title="Bàn Nghiên cứu",
        page_icon="N",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_css()
    runs = discover_runs()
    (
        provider,
        model,
        version,
        use_snapshot,
        history_window,
        max_tool_rounds,
        prompt_path,
        tools_path,
        artifact_source,
    ) = render_sidebar(runs)

    artifact = build_artifact_version(version, prompt_path, tools_path)
    config_key = session_config_key(
        provider=provider,
        model=model,
        version=version,
        use_snapshot=use_snapshot,
        prompt_path=prompt_path,
        tools_path=tools_path,
        history_window=history_window,
        max_tool_rounds=max_tool_rounds,
    )
    if st.session_state.get("transcript_config") != "demo":
        ensure_session(config_key)

    render_workspace_header(
        artifact_version=artifact.artifact_version,
        provider=provider,
        model=model,
        artifact_source=artifact_source,
    )

    chat_tab, tools_tab, evidence_tab = st.tabs(["Hội thoại", "Công cụ", "Phòng bằng chứng"])
    with chat_tab:
        suggested_prompt = render_chat_tab()
    with tools_tab:
        render_tool_catalog(tools_path)
    with evidence_tab:
        render_evidence_tab(
            runs,
            version,
            artifact.prompt_hash,
            artifact.tools_hash,
        )

    submitted = suggested_prompt
    if submitted:
        with st.spinner("Đang nghiên cứu và ghi lại dấu vết thực thi…"):
            execute_prompt(
                submitted,
                provider_name=provider,
                model=model,
                version=version,
                prompt_path=prompt_path,
                tools_path=tools_path,
                history_window=history_window,
                max_tool_rounds=max_tool_rounds,
            )
        st.rerun()


if __name__ == "__main__":
    main()
