# Personal Model Technical Share HTML Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the current Chinese Markdown sharing draft into one self-contained, browser-openable HTML presentation with an embedded interactive Memory Formation / Memory Recall diagram.

**Architecture:** The HTML file is the presentation source of truth. It contains all CSS, JavaScript, article copy, diagram stage data, navigation, and print rules inline, with no CDN or build-time dependency. The existing Markdown file remains as a historical backup and is no longer edited after the conversion.

**Tech Stack:** Semantic HTML5, inline CSS, vanilla JavaScript, Python standard-library tests, browser smoke testing.

## Global Constraints

- Output file: `docs/personal-model-technical-share.html`.
- Open directly through `file://`; no server is required.
- No external CSS, JavaScript, fonts, images, or network requests.
- Preserve the approved Chinese narrative order and synthetic names 小张、小李、项目 A/B/C.
- Embed the two interactive flow lanes directly in the HTML.
- Clicking a stage expands its horizontal sub-flow and vertical mechanism/metrics detail.
- Use the reference report's narrative rhythm and visual hierarchy without copying its content.
- Keep current implementation boundaries explicit, especially incomplete exact Capture lineage.
- Do not commit unless the user explicitly requests a commit.

---

### Task 1: Add the HTML artifact contract

**Files:**
- Create: `tests/test_technical_share_html.py`
- Create: `docs/personal-model-technical-share.html`

**Interfaces:**
- Consumes: current content in `docs/personal-model-technical-share.md`
- Produces: a UTF-8, self-contained HTML document that can be opened from disk

- [ ] **Step 1: Write the failing artifact tests**

Create tests that assert:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "docs" / "personal-model-technical-share.html"


def test_technical_share_html_is_self_contained() -> None:
    text = HTML.read_text(encoding="utf-8")
    assert text.startswith("<!doctype html>")
    assert '<html lang="zh-CN">' in text
    assert "<style>" in text
    assert "<script>" in text
    assert 'src="http' not in text
    assert 'href="http' not in text


def test_technical_share_html_contains_narrative_spine() -> None:
    text = HTML.read_text(encoding="utf-8")
    for phrase in (
        "Personal Memory 是什么、为什么需要它",
        "Memory Formation",
        "Memory Recall",
        "走一个实例",
        "小张",
        "小李",
        "项目 A",
    ):
        assert phrase in text
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
uv run pytest tests/test_technical_share_html.py -q
```

Expected: failure because `docs/personal-model-technical-share.html` does not exist.

- [ ] **Step 3: Create the minimal HTML shell**

Add the doctype, Chinese language declaration, title, responsive viewport, inline `<style>`, Hero, sticky table of contents, `<main>`, and inline `<script>`.

- [ ] **Step 4: Run the artifact tests**

Run:

```bash
uv run pytest tests/test_technical_share_html.py -q
```

Expected: both tests pass.

---

### Task 2: Port the approved narrative and citations

**Files:**
- Modify: `docs/personal-model-technical-share.html`
- Modify: `tests/test_technical_share_html.py`

**Interfaces:**
- Consumes: approved opening and chapter 0 copy from the Markdown draft
- Produces: the report opening, glossary, two root causes, solution overview, three technical goals, and the complete 小张/小李 example

- [ ] **Step 1: Extend tests for section anchors**

Assert that the HTML includes stable IDs:

```python
def test_technical_share_html_has_stable_sections() -> None:
    text = HTML.read_text(encoding="utf-8")
    for section_id in (
        "opening",
        "flow",
        "example",
        "collection",
        "state",
        "formation",
        "recall",
        "delivery",
        "evaluation",
        "outlook",
    ):
        assert f'id="{section_id}"' in text
```

- [ ] **Step 2: Port the article copy**

Use semantic `<section>`, `<h2>`, `<h3>`, `<p>`, `<ul>`, and `<pre>` elements. Render terminology as compact glossary cards and the two root causes as side-by-side cards.

- [ ] **Step 3: Port fact references as native disclosures**

Render `[事实引用 1]`, `[事实引用 2]`, and `[事实引用 3]` with `<details><summary>…</summary>…</details>`, preserving Fact, Relation, Behavior Pattern, Supporting Facts, and Raw Evidence.

- [ ] **Step 4: Verify narrative and anchors**

Run:

```bash
uv run pytest tests/test_technical_share_html.py -q
```

Expected: all tests pass.

---

### Task 3: Embed the interactive two-lane flow

**Files:**
- Modify: `docs/personal-model-technical-share.html`
- Modify: `tests/test_technical_share_html.py`

**Interfaces:**
- Consumes: stage definitions already validated in the Cursor Canvas
- Produces: browser-native stage selection, expansion, and chapter navigation

- [ ] **Step 1: Add interaction contract tests**

Assert the HTML contains:

```python
def test_technical_share_html_embeds_interactive_memory_flow() -> None:
    text = HTML.read_text(encoding="utf-8")
    assert 'data-lane="formation"' in text
    assert 'data-lane="recall"' in text
    assert "stageDetails" in text
    assert "selectStage" in text
    assert "scrollIntoView" in text
    for stage in (
        "collect",
        "filter",
        "normalize",
        "state",
        "delta",
        "sediment",
        "present",
        "heads",
        "fuse",
        "chains",
        "deliver",
    ):
        assert f'data-stage="{stage}"' in text
```

- [ ] **Step 2: Add two clickable lanes**

Render:

```text
Memory Formation:
collect → filter → normalize → state → delta → sediment

Memory Recall:
present → heads → fuse → chains → deliver
```

Each stage is a real `<button>` with `data-stage`, keyboard focus, and `aria-expanded`.

- [ ] **Step 3: Add the expansion panel**

Embed a `stageDetails` object. `selectStage(id)` renders:

- stage question
- input and output
- horizontal child flow
- mechanisms
- invariants
- instrumentation and evaluation
- implementation boundary

Clicking the selected stage again collapses the panel.

- [ ] **Step 4: Add chapter synchronization**

Map each stage to a stable section ID and call:

```javascript
document.getElementById(sectionId)?.scrollIntoView({
  behavior: "smooth",
  block: "start",
});
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/test_technical_share_html.py -q
```

Expected: all tests pass.

---

### Task 4: Add presentation and print behavior

**Files:**
- Modify: `docs/personal-model-technical-share.html`
- Modify: `tests/test_technical_share_html.py`

**Interfaces:**
- Consumes: complete report and interactive flow
- Produces: a presentation-ready browser document and readable printed/PDF output

- [ ] **Step 1: Add visual contract tests**

Assert the file contains a sticky table of contents, active-section logic, responsive breakpoints, and `@media print`.

- [ ] **Step 2: Implement presentation styling**

Use:

- restrained blue/purple accent
- 1000px maximum article width
- sticky, scroll-aware table of contents
- white section surfaces on a light neutral background
- glossary cards, insight callouts, code blocks, KPI callouts, and comparison cards
- no external fonts or icons

- [ ] **Step 3: Implement scroll spy**

Use `IntersectionObserver` to mark the current navigation link active while scrolling.

- [ ] **Step 4: Add print rules**

Hide interactive controls that do not print meaningfully, expand essential text, remove shadows, and avoid splitting examples and citations across pages where possible.

- [ ] **Step 5: Run all artifact tests**

Run:

```bash
uv run pytest tests/test_technical_share_html.py -q
```

Expected: all tests pass.

---

### Task 5: Browser smoke verification and source handoff

**Files:**
- Modify: `docs/personal-model-technical-share.md`

**Interfaces:**
- Consumes: final standalone HTML
- Produces: verified local presentation and an archived Markdown source notice

- [ ] **Step 1: Open the HTML through `file://`**

Verify in a browser:

- Hero and sticky TOC render correctly.
- Formation and Recall lanes fit at desktop width.
- Stage click expands details.
- Stage click scrolls to the correct chapter.
- Fact references expand and collapse.
- No console errors or network requests occur.
- Narrow viewport stacks cards without horizontal page overflow.

- [ ] **Step 2: Check print preview**

Verify headings, examples, citations, and code blocks remain readable in portrait PDF output.

- [ ] **Step 3: Mark Markdown as archived**

Add a short note at the top of the Markdown file pointing to the HTML as the canonical presentation source. Do not delete the Markdown history.

- [ ] **Step 4: Final verification**

Run:

```bash
uv run pytest tests/test_technical_share_html.py -q
```

Expected: all tests pass.
