from __future__ import annotations

import unittest
from pathlib import Path


class TestStaticUi(unittest.TestCase):
    def test_home_navigation_and_library_assets_exist(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="home-view"', html)
        self.assertIn('id="library-view"', html)
        self.assertIn('id="assistant-view"', html)
        self.assertIn('id="nav-home"', html)
        self.assertIn('id="nav-library"', html)
        self.assertIn('id="nav-assistant"', html)
        self.assertIn('id="home-search"', html)
        self.assertIn("可输入：岩棉厚度、金属单元板面密度、Q/CR760", html)
        self.assertIn('id="stat-clauses"', html)
        self.assertIn('id="stat-materials"', html)
        self.assertIn('id="stat-standards"', html)
        self.assertIn('id="nav-toggle"', html)
        self.assertIn("view-hidden", css)
        self.assertIn("sidebar-collapsed", css)
        self.assertIn("showView", js)
        self.assertIn("sidebar-collapsed", js)
        self.assertIn("material_groups", js)
        self.assertIn("renderNavGroup", js)
        self.assertIn("项目名称", js)

    def test_static_theme_uses_blue_white_palette(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        css = (static_dir / "styles.css").read_text(encoding="utf-8")

        self.assertIn("--accent: #2563eb", css)
        self.assertNotIn("#fbf6ea", css)
        self.assertNotIn("#fff8eb", css)
        self.assertNotIn("#f0dfbd", css)

    def test_chat_view_has_input_and_messages(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="chat-messages"', html)
        self.assertIn('id="chat-input"', html)
        self.assertIn('id="chat-send"', html)
        self.assertIn('id="chat-form"', html)
        self.assertIn(".chat-shell", css)
        self.assertIn(".chat-bubble", css)
        self.assertIn('fetch("/api/chat"', js)
        self.assertIn("submitChatMessage", js)
        self.assertIn("renderMarkdown", js)
        self.assertIn("renderMarkdownTable", js)
        self.assertIn(".chat-markdown table", css)
        self.assertNotIn("${escapeHtml(entry.answer || \"\")}", js)

    def test_home_ai_assistant_card_submits_into_chat(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('class="home-ai-card"', html)
        self.assertIn("AI助手", html)
        self.assertIn('id="home-ai-input"', html)
        self.assertIn('id="home-ai-form"', html)
        self.assertIn("适合提问：帮我总结岩棉相关标准", html)
        self.assertIn("帮我总结岩棉相关标准", html)
        self.assertIn(".home-ai-card", css)
        self.assertIn("submitHomeAssistantQuestion", js)
        self.assertIn('showView("assistant")', js)
        self.assertIn("chatInputEl.value = question", js)

    def test_floating_ai_assistant_entry_is_fixed_draggable_and_opens_chat(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="floating-ai-assistant"', html)
        self.assertIn("AI助手", html)
        self.assertIn('aria-label="打开AI助手"', html)
        self.assertIn(".floating-ai-assistant", css)
        self.assertIn("position: fixed;", css)
        self.assertIn("border-radius: 50%;", css)
        self.assertIn("touch-action: none;", css)
        self.assertIn("#e0f2fe", css)
        self.assertIn("#7dd3fc", css)
        self.assertNotIn("linear-gradient(145deg, #38bdf8 0%, var(--accent) 48%, #1e3a8a 100%)", css)
        self.assertIn("initFloatingAssistant", js)
        self.assertIn("floatingAssistantEl", js)
        self.assertIn("handleFloatingAssistantClick", js)
        self.assertIn('showView("assistant")', js)
        self.assertIn("ensureChatGreeting();", js)

    def test_library_search_uses_fuzzy_endpoint_and_summary_panel(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="assistant-panel"', html)
        self.assertIn('class="query-hint"', html)
        self.assertIn("标准库搜索需要输入与 Excel 中一致的关键词才能命中", html)
        self.assertIn("如果不确定关键词，请使用 AI助手", html)
        self.assertIn('class="query-examples"', html)
        self.assertIn("例如：岩棉、金属单元板、面密度、Q/CR760", html)
        self.assertIn(".query-hint", css)
        self.assertIn(".query-examples", css)
        self.assertIn("/api/fuzzy-search", js)
        self.assertIn("renderFuzzySearchResult", js)
        self.assertIn("renderSearchSummary", js)

    def test_tables_use_compact_column_widths_and_match_highlight(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        css = (static_dir / "styles.css").read_text(encoding="utf-8")
        js = (static_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn("renderColumnGroup", js)
        self.assertIn("<colgroup>", js)
        self.assertIn("tableMinWidth", js)
        self.assertIn("isMatchedRow", js)
        self.assertIn("match-row", js)
        self.assertIn("width: 100%;", css)
        self.assertNotIn("width: max-content", css)
        self.assertIn("col.index-col { width: 64px; }", css)
        self.assertIn("col.part-col { width: 120px; }", css)
        self.assertIn("col.item-col { width: 180px; }", css)
        self.assertNotIn("col.standard-col { width: 220px; }", css)
        self.assertIn("tbody tr.match-row", css)

    def test_table_body_cells_are_center_aligned(self):
        static_dir = Path(__file__).resolve().parents[1] / "src" / "sound_barrier_query" / "static"
        css = (static_dir / "styles.css").read_text(encoding="utf-8")

        self.assertIn("th, td", css)
        self.assertIn("text-align: center;", css)
        self.assertIn(".requirement { white-space: pre-wrap; text-align: center; }", css)
        self.assertNotIn(".requirement { white-space: pre-wrap; text-align: left; }", css)


if __name__ == "__main__":
    unittest.main()
