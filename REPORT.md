# SmartTasks Agent: Raw Messages API vs. Claude Agent SDK Report

## 1. Domain Overview & Four Core Pillars

**SmartTasks** is a personal task and schedule management assistant that helps users organize tasks by category and priority, verify official public holidays before committing to deadlines, and enforce strict work-life and scheduling restrictions across sessions.

1. **Tools (4 Custom Tools in `shared/tools_impl.py`)**:
   - `add_task` *(internal)*: Adds or updates a task (`title`, `due_date`, `category`, `priority`) in `data/tasks.json` after validating against saved scheduling rules.
   - `get_tasks` *(internal)*: Retrieves scheduled tasks with optional `category` and `query` filters.
   - `remove_task` *(internal)*: Removes/completes a task from `data/tasks.json` (raising a structured tool error with `is_error=True` if the task is not present).
   - `check_public_holidays` *(external — Nager.Date Public Holidays API)*: Queries `https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}` to check official public holidays for deadline planning.
2. **Persistent Cross-Session Memory**:
   - Persists scheduling rules and work-life boundaries (`No Friday tasks`, `No weekend work on Saturday or Sunday`) on disk (`data/memory.json` and `CLAUDE.md`) so new agent instances in subsequent sessions enforce them automatically.
3. **Context Engineering**:
   - In `API/harness/context.py`, each turn receives only the relevant scheduling rules and only the task slice matching categories/titles mentioned in the user's prompt (omitting unrelated tasks).
   - In `SDK/`, `CLAUDE.md` is loaded via `setting_sources=["project"]` and the agent fetches specific task categories on demand via `get_tasks`.
4. **Token Optimization**:
   - Raw `Nager.Date` responses return 12–15 full holiday JSON objects per year (including `counties`, `launchYear`, `types`, `fixed`, `global` fields). `check_public_holidays` strips verbose metadata to return a compact single-line summary (`YYYY-MM-DD: Name (LocalName)`) for the top N holidays (~82% token reduction on tool outputs).

---

## 2. Benchmark Comparison: Raw API vs. Claude Agent SDK

Both versions were evaluated from a clean state (`reset_state`) on `scenario.json` (7 turns across 2 sessions, `model="claude-opus-4-6"`, `effort="medium"`).

### Aggregate Metrics Summary

| Metric | Raw Messages API (`API/`) | Claude Agent SDK (`SDK/`) | Delta (SDK vs. API) |
| :--- | ---: | ---: | ---: |
| **Input Tokens (Uncached)** | 5,740 | 2,870 | -2,870 (-50.0%) |
| **Cache Read Tokens** | 7,412 | 16,566 | +9,154 (+123.5%) |
| **Cache Write Tokens** | 1,346 | 3,012 | +1,666 (+123.8%) |
| **Output Tokens** | 1,298 | 1,465 | +167 (+12.9%) |
| **Total Tokens** | 15,796 | 23,913 | +8,117 (+51.4%) |
| **Cache Hit Rate (%)** | **51.12%** | **73.79%** | **+22.67 pp** |
| **Total Model Calls** | 13 | 13 | 0 |
| **Total Cost (USD)** | **$0.219806** | **$0.234249** | **+$0.014443 (+6.6%)** |
| **Checks Passed** | **7 / 7 (100%)** | **7 / 7 (100%)** | Equal |

### Per-Turn Breakdown

| Turn | Session | Scenario Action | API In / CacheRead / CacheWrite / Out | API Cost ($) | SDK In / CacheRead / CacheWrite / Out | SDK Cost ($) |
| :---: | :---: | :--- | :---: | ---: | :---: | ---: |
| **1** | `session_1` | Save scheduling rules + add 3 tasks | 390 / 676 / 676 / 225 | $0.036414 | 324 / 1,506 / 1,506 / 302 | $0.058007 |
| **2** | `session_1` | Remove `draft team slides` + add 2 tasks | 1,095 / 1,352 / 0 / 218 | $0.034803 | 410 / 3,012 / 0 / 246 | $0.029118 |
| **3** | `session_1` | External `check_public_holidays(US)` | 1,320 / 1,352 / 0 / 260 | $0.041328 | 520 / 3,012 / 0 / 280 | $0.033318 |
| **4** | `session_1` | Selective `get_tasks(work)` | 1,610 / 1,352 / 0 / 115 | $0.034803 | 636 / 3,012 / 0 / 124 | $0.023358 |
| **5** | `session_2` | Fresh instance: recall rules & tasks | 182 / 670 / 670 / 132 | $0.026198 | 254 / 1,506 / 1,506 / 140 | $0.044806 |
| **6** | `session_2` | Contradiction: schedule Friday & Saturday work | 280 / 670 / 0 / 78 | $0.011055 | 200 / 1,506 / 0 / 78 | $0.011109 |
| **7** | `session_2` | Add Thursday deployment + `check_public_holidays(GB)` | 863 / 1,340 / 0 / 270 | $0.035205 | 526 / 3,012 / 0 / 295 | $0.034533 |

---

## 3. Lines of Code (LOC) per Harness Responsibility: API vs. SDK

Non-empty, non-comment lines of code measured automatically by `shared/evaluator.py`:

| Harness Responsibility | API File (`API/harness/`) | API LOC | SDK Replacement Mechanism | SDK `# replaces:` Lines |
| :--- | :--- | ---: | :--- | ---: |
| **Agent Loop** | `API/harness/loop.py` | 116 | `client.query()` + `client.receive_response()` | 3 |
| **Tools & Dispatch** | `API/harness/tools.py` | 147 | `@tool`, `create_sdk_mcp_server`, `allowed_tools`, `strict_mcp_config=True` | 19 |
| **Conversation History** | `API/harness/history.py` | 65 | `resume=session_id` | 2 |
| **Persistent Memory** | `API/harness/memory.py` | 102 | `CLAUDE.md` with `setting_sources=["project"]` | 1 |
| **Context Engineering** | `API/harness/context.py` | 48 | `system_prompt` + automatic project context loading | 1 |
| **Context Compaction** | `API/harness/compaction.py` | 78 | Automatic SDK context window management | 1 |
| **Prompt Caching** | `API/harness/caching.py` | 44 | Automatic SDK ephemeral cache breakpoints | 1 |
| **Token & Cost Tracking** | `API/harness/tokens.py` | 77 | `ResultMessage.usage` & `ResultMessage.total_cost_usd` | 2 |
| **Harness Subtotal** | **8 Files in `API/harness/`** | **677** | **Declarative SDK Configuration** | **30** |
| **Entrypoint & Agent Glue** | `API/main.py` (85) + `API/agent.py` (56) | 141 | `SDK/main.py` (87) + `SDK/agent.py` (116) + `SDK/tools.py` (94)* | 297 |
| **Total Package LOC** | **All files in `API/`** | **818** | **All files in `SDK/`** | **297** |

*\*Note: `SDK/tools.py` (94 LOC) includes the 19 `# replaces: tools.py` declarations plus the thin `@tool` wrappers around `shared/tools_impl.py`. Overall, the SDK reduced harness-specific code from 677 LOC to 30 declarative configuration lines (a **95.6% reduction** in harness orchestration code).*

---

## 4. Analysis & Reflection Questions

### Q1: Where did the SDK cost more tokens and where less, and why?
- **Where the SDK cost MORE tokens (Session-start turns: Turn 1 and Turn 5)**:
  - On Turn 1 (`session_1` cold start) and Turn 5 (`session_2` cold start), the SDK wrote **1,506 cache creation tokens** per session start compared to only **676 cache creation tokens** in the raw API (+122.8% higher static prompt footprint).
  - **Why**: Claude Code injects its own built-in harness scaffolding, system instructions, environment metadata, built-in file tool schemas (`Read`, `Write`, `Edit`), and the full `CLAUDE.md` file (`setting_sources=["project"]`). Additionally, in Turn 1, the SDK invoked the built-in `Write` tool to persist scheduling rules to `CLAUDE.md`, adding output tokens.
- **Where the SDK cost LESS uncached input tokens (Mid-session turns: Turns 2, 3, 4, and 7)**:
  - During Turns 2–4, uncached input tokens in the SDK were significantly lower (e.g., Turn 4 used 636 uncached input tokens in the SDK vs. 1,610 in the API, costing `$0.023358` vs. `$0.034803`).
  - **Why**: In the raw API, `context.py` dynamically mutates the `system` prompt string on every turn to inject the selective task slice (`Relevant Task Slice (...)`). Because the `system` block sits at the beginning of the prompt prefix, any change to the dynamic task slice invalidates downstream prefix caching for the conversation history. By contrast, the SDK keeps its static system prefix and `CLAUDE.md` constant within a session, achieving a **73.79% cache hit rate** vs. **51.12%** in the API.

### Q2: What control did you have in the API that you lost in the SDK?
1. **Fine-Grained Per-Turn Context Selection (`context.py`)**:
   - In the raw API, `context.py` inspects the user's message before every call and injects *only* the matching task category and relevant scheduling rules. In the SDK, `setting_sources=["project"]` loads the entire `CLAUDE.md` file unconditionally into every session.
2. **Custom Compaction Policy & Thresholds (`compaction.py`)**:
   - In the raw API, we controlled the exact compaction trigger (`max_messages=6`, `max_chars=2200`) and the exact summarization format (triggered on Turn 7, shrinking the window from 7 to 5 messages). In the SDK, compaction only triggers near the model's full context window limit using an opaque internal prompt.
3. **Explicit Cache Breakpoint Placement (`caching.py`)**:
   - In the raw API, we chose exactly which 3 blocks received `{"cache_control": {"type": "ephemeral"}}`. In the SDK, breakpoint placement is managed internally by the Claude Code runtime.
4. **Deterministic Pre-Execution Memory Extraction (`memory.py`)**:
   - In the raw API, `memory.py` deterministically parses and persists scheduling constraints (`No Friday tasks`, `No weekend work`) before the model even runs. In the SDK, persisting to `CLAUDE.md` relies on the model choosing to invoke a file-writing tool.
5. **Minimal System Prompt & Zero Built-In Tool Overhead (`tools.py`)**:
   - In the raw API, *only* our 4 JSON tool schemas and our concise system prompt are sent. In the SDK, even with `allowed_tools` and `strict_mcp_config=True`, the Claude Code runtime carries a larger baseline prompt footprint.

### Q3: Which version would you choose for this agent, and why?
For **SmartTasks**, I would choose the **Raw Messages API (`API/`)** for production deployment, while using the **Claude Agent SDK (`SDK/`)** for rapid prototyping:

1. **Deterministic Enforcement of Scheduling Boundaries**: SmartTasks enforces strict work-life boundaries (`no Friday tasks`, `no weekend work`). Having a deterministic `memory.py` + `context.py` pipeline in the raw API guarantees that scheduling rules are extracted, stored in structured JSON (`data/memory.json`), and injected into every scheduling turn without relying on the model remembering to edit `CLAUDE.md`.
2. **Lower Cold-Start Cost for Quick Task Check-Ins**: Typical task manager interactions are short (1–3 turns per session: adding a reminder or checking today's work tasks). Because short sessions are dominated by Turn 1 cache-write overhead, the raw API's tiny static footprint (676 tokens vs. 1,506 tokens in SDK) makes it **37% cheaper on Turn 1** (`$0.0364` vs. `$0.0580`).
3. **Zero Subprocess Dependency**: The raw API runs as a lightweight Python process using `httpx`/`anthropic`, whereas the Claude Agent SDK spawns a CLI subprocess (`claude`) and MCP server transport, which is heavier to deploy in a backend service.
