# Sound Barrier Standard Query System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local sound barrier standard query system from `docs/国内声屏障标准汇总表.xlsx`.

**Architecture:** The system imports the Excel workbook into normalized clause records, exposes deterministic search/comparison/summarization APIs, and serves a small local web UI through Python standard library HTTP tools. AI assistant behavior is retrieval-grounded and extractive, so every answer links back to source records.

**Tech Stack:** Python 3.11+, uv project metadata, standard library `zipfile`/`xml.etree` for `.xlsx`, `unittest`, browser UI with HTML/CSS/JavaScript.

---

### Task 1: Project Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/sound_barrier_query/__init__.py`
- Create: `src/sound_barrier_query/models.py`
- Create: `tests/test_query_engine.py`

- [ ] **Step 1: Write the failing import test**

```python
from sound_barrier_query.models import StandardClause


def test_clause_source_id_contains_sheet_and_cell():
    clause = StandardClause(
        sheet="岩棉",
        row=3,
        column=4,
        product="岩棉",
        item="密度kg/m3",
        standard="GB/T 25975-2018",
        requirement="80~120",
    )

    assert clause.source_id == "岩棉!D3"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run python -m unittest tests.test_query_engine -v`

- [ ] **Step 3: Implement the dataclass**

Create `StandardClause` with `sheet`, `row`, `column`, `product`, `item`, `standard`, `requirement`, `source_id`, and `as_dict()`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run python -m unittest tests.test_query_engine -v`

### Task 2: Workbook Import

**Files:**
- Create: `src/sound_barrier_query/xlsx_loader.py`
- Modify: `tests/test_query_engine.py`

- [ ] **Step 1: Write failing loader tests**

Test that `load_workbook_clauses("docs/国内声屏障标准汇总表.xlsx")` returns clauses containing product `岩棉`, item `密度kg/m³`, and a source id.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `uv run python -m unittest tests.test_query_engine.TestWorkbookLoader -v`

- [ ] **Step 3: Implement `.xlsx` parsing**

Use standard library zip/XML parsing, shared strings, sheet rels, row/cell coordinates, merged-ish forward fill for product cells, and skip `WpsReserved_CellImgList`.

- [ ] **Step 4: Run loader tests**

Run: `uv run python -m unittest tests.test_query_engine.TestWorkbookLoader -v`

### Task 3: Query Engine

**Files:**
- Create: `src/sound_barrier_query/search.py`
- Modify: `tests/test_query_engine.py`

- [ ] **Step 1: Write failing search tests**

Cover standard search (`Q/CR760`), product comparison (`岩棉`), keyword search (`面密度`), and source links.

- [ ] **Step 2: Run focused tests**

Run: `uv run python -m unittest tests.test_query_engine.TestSearchEngine -v`

- [ ] **Step 3: Implement search engine**

Normalize Chinese punctuation, spaces, `/`, and case; support standard/product/keyword searches and product comparison grouped by item.

- [ ] **Step 4: Run focused tests**

Run: `uv run python -m unittest tests.test_query_engine.TestSearchEngine -v`

### Task 4: Retrieval-Grounded Assistant

**Files:**
- Create: `src/sound_barrier_query/assistant.py`
- Modify: `tests/test_query_engine.py`

- [ ] **Step 1: Write failing assistant test**

Ask `岩棉密度有什么要求` and assert the answer includes summary text, related clauses, and source links.

- [ ] **Step 2: Run focused test**

Run: `uv run python -m unittest tests.test_query_engine.TestAssistant -v`

- [ ] **Step 3: Implement assistant**

Extract query terms, retrieve top clauses, group by product/item, and render concise grounded summaries.

- [ ] **Step 4: Run focused test**

Run: `uv run python -m unittest tests.test_query_engine.TestAssistant -v`

### Task 5: Local Web App

**Files:**
- Create: `src/sound_barrier_query/web.py`
- Create: `src/sound_barrier_query/static/index.html`
- Create: `src/sound_barrier_query/static/styles.css`
- Create: `src/sound_barrier_query/static/app.js`
- Modify: `README.md`

- [ ] **Step 1: Write failing API smoke test**

Instantiate the app data layer and assert `/api/search` response payload shape through handler helpers.

- [ ] **Step 2: Implement local HTTP server**

Serve static UI and JSON endpoints: `/api/search`, `/api/compare`, `/api/assistant`, `/api/meta`.

- [ ] **Step 3: Run relevant tests**

Run: `uv run python -m unittest tests.test_query_engine -v`

- [ ] **Step 4: Start server**

Run: `uv run python -m sound_barrier_query.web --port 8765`

### Notes

- No git commit steps will be executed because `D:\中驰股份\声学分析\检测2.0` is not a git repository.
- Only the related unittest module is run, matching the local project instruction.
