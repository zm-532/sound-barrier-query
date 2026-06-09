const state = {
  materials: [],
  materialGroups: [],
  activeMaterial: "",
  currentView: "home",
  chatHistory: [],
  chatBusy: false,
  aiConfigured: false,
  metaLoaded: false,
};

const homeView = document.querySelector("#home-view");
const libraryView = document.querySelector("#library-view");
const assistantView = document.querySelector("#assistant-view");
const navHome = document.querySelector("#nav-home");
const navLibrary = document.querySelector("#nav-library");
const navAssistant = document.querySelector("#nav-assistant");
const floatingAssistantEl = document.querySelector("#floating-ai-assistant");
const homeSearchInput = document.querySelector("#home-search");
const homeSearchButton = document.querySelector("#home-search-button");
const homeAiFormEl = document.querySelector("#home-ai-form");
const homeAiInputEl = document.querySelector("#home-ai-input");
const queryInput = document.querySelector("#query");
const searchButton = document.querySelector("#search");
const resultsEl = document.querySelector("#results");
const countEl = document.querySelector("#count");
const metaEl = document.querySelector("#meta");
const navEl = document.querySelector("#material-nav");
const tableTitleEl = document.querySelector("#table-title");
const tableSubtitleEl = document.querySelector("#table-subtitle");
const breadcrumbEl = document.querySelector("#breadcrumb");
const assistantPanel = document.querySelector("#assistant-panel");
const summaryEl = document.querySelector("#summary");
const suggestionsEl = document.querySelector("#suggestions");
const navToggle = document.querySelector("#nav-toggle");

const chatMessagesEl = document.querySelector("#chat-messages");
const chatFormEl = document.querySelector("#chat-form");
const chatInputEl = document.querySelector("#chat-input");
const chatSendEl = document.querySelector("#chat-send");
const chatClearEl = document.querySelector("#chat-clear");
const chatStatusEl = document.querySelector("#chat-status");
const chatSuggestionEls = document.querySelectorAll(".chat-suggestions button");
const floatingAssistantDrag = {
  pointerId: null,
  offsetY: 0,
  startY: 0,
  moved: false,
  suppressClick: false,
};

navHome.addEventListener("click", () => showView("home"));
navLibrary.addEventListener("click", () => {
  showView("library");
  if (!state.activeMaterial && state.materials.length) {
    loadMaterial(state.materials[0]);
  }
});
navAssistant.addEventListener("click", () => {
  openAssistantView();
});
initFloatingAssistant();
homeSearchButton.addEventListener("click", () => runSearch(homeSearchInput.value));
homeSearchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    runSearch(homeSearchInput.value);
  }
});
homeAiFormEl.addEventListener("submit", (event) => {
  event.preventDefault();
  submitHomeAssistantQuestion();
});
searchButton.addEventListener("click", () => runSearch(queryInput.value));
queryInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    runSearch(queryInput.value);
  }
});

document.querySelector("#home").addEventListener("click", () => {
  showView("home");
});

navToggle.addEventListener("click", () => {
  const collapsed = document.body.classList.toggle("sidebar-collapsed");
  navToggle.textContent = collapsed ? "›" : "‹";
  navToggle.setAttribute("aria-expanded", String(!collapsed));
  navToggle.setAttribute("aria-label", collapsed ? "展开导航" : "折叠导航");
  navToggle.setAttribute("title", collapsed ? "展开导航" : "折叠导航");
});

document.querySelectorAll(".quick-actions button").forEach((button) => {
  button.addEventListener("click", () => {
    runSearch(button.dataset.query);
  });
});

chatFormEl.addEventListener("submit", (event) => {
  event.preventDefault();
  submitChatMessage();
});

chatInputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitChatMessage();
  }
});

chatClearEl.addEventListener("click", () => {
  state.chatHistory = [];
  renderChatMessages();
  ensureChatGreeting();
});

chatSuggestionEls.forEach((button) => {
  button.addEventListener("click", () => {
    chatInputEl.value = button.dataset.question || "";
    submitChatMessage();
  });
});

async function loadMeta() {
  const data = await fetchJson("/api/meta");
  state.materialGroups = data.material_groups || [{ name: "国内标准", materials: data.materials || [] }];
  state.materials = state.materialGroups.flatMap((group) => group.materials || []);
  state.aiConfigured = Boolean(data.ai_configured);
  state.metaLoaded = true;
  metaEl.textContent = `已载入 ${data.clause_count} 条标准内容，覆盖 ${state.materials.length} 类材料/产品、${data.standards.length} 个标准或技术文件`;
  document.querySelector("#stat-clauses").textContent = data.clause_count;
  document.querySelector("#stat-materials").textContent = state.materials.length;
  document.querySelector("#stat-standards").textContent = data.standards.length;
  renderNav();
  updateChatStatus();
  refreshGreeting();
  showView("home");
}

function updateChatStatus() {
  if (!chatStatusEl) {
    return;
  }
  chatStatusEl.textContent = state.aiConfigured
    ? "基于声屏障标准汇总表检索增强回答"
    : "AI接口未配置完整，请在 .env 中配置 BASE_URL/API_KEY/MODEL";
}

function ensureChatGreeting() {
  if (state.chatHistory.length) {
    return;
  }
  if (!state.metaLoaded) {
    state.chatHistory.push({
      role: "assistant",
      answer: "正在检查 AI 接口配置…",
      sources: [],
      pending: true,
    });
    renderChatMessages();
    return;
  }
  state.chatHistory.push({
    role: "assistant",
    answer: state.aiConfigured
      ? "您好，我是声屏障标准库的 AI 助手。请直接输入您要查询的问题，例如「岩棉的国内标准和项目名称」。"
      : "AI 接口尚未配置完整，请联系管理员在 .env 中填写 BASE_URL/API_KEY/MODEL 后再试。",
    sources: [],
    error: state.aiConfigured ? null : "config_missing",
  });
  renderChatMessages();
}

function refreshGreeting() {
  if (!state.metaLoaded) {
    return;
  }
  if (state.chatHistory.length === 0) {
    ensureChatGreeting();
    return;
  }
  const onlyGreeting =
    state.chatHistory.length === 1 &&
    state.chatHistory[0].role === "assistant" &&
    !state.chatHistory[0].loading &&
    !state.chatHistory[0].sources?.length;
  if (!onlyGreeting) {
    updateChatStatus();
    return;
  }
  const last = state.chatHistory[0];
  const isPending = Boolean(last.pending);
  const expectedConfigured = state.aiConfigured;
  const currentlyShownConfigured = !isPending && !last.error;
  if (expectedConfigured === currentlyShownConfigured) {
    state.chatHistory[0] = {
      role: "assistant",
      answer: expectedConfigured
        ? "您好，我是声屏障标准库的 AI 助手。请直接输入您要查询的问题，例如「岩棉的国内标准和项目名称」。"
        : "AI 接口尚未配置完整，请联系管理员在 .env 中填写 BASE_URL/API_KEY/MODEL 后再试。",
      sources: [],
      error: expectedConfigured ? null : "config_missing",
    };
  }
  updateChatStatus();
  renderChatMessages();
}

async function submitChatMessage() {
  if (state.chatBusy) {
    return;
  }
  const question = chatInputEl.value.trim();
  if (!question) {
    return;
  }
  chatInputEl.value = "";
  state.chatHistory.push({ role: "user", answer: question });
  const loadingEntry = { role: "assistant", loading: true };
  state.chatHistory.push(loadingEntry);
  renderChatMessages();
  setChatBusy(true);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question }),
    });
    const data = await response.json();
    state.chatHistory.pop();
    state.chatHistory.push({
      role: "assistant",
      answer: data.answer || "AI助手暂时无法回答，请稍后重试。",
      sources: Array.isArray(data.sources) ? data.sources : [],
      error: data.error || null,
    });
  } catch (error) {
    state.chatHistory.pop();
    state.chatHistory.push({
      role: "assistant",
      answer: "AI助手暂时无法回答，请稍后重试。",
      sources: [],
      error: "network",
    });
  } finally {
    setChatBusy(false);
    renderChatMessages();
  }
}

async function submitHomeAssistantQuestion() {
  if (state.chatBusy) {
    return;
  }
  const question = homeAiInputEl.value.trim();
  if (!question) {
    homeAiInputEl.focus();
    return;
  }
  homeAiInputEl.value = "";
  showView("assistant");
  ensureChatGreeting();
  chatInputEl.value = question;
  await submitChatMessage();
  chatInputEl.focus();
}

function setChatBusy(busy) {
  state.chatBusy = busy;
  chatSendEl.disabled = busy;
  chatInputEl.disabled = busy;
}

function openAssistantView() {
  showView("assistant");
  ensureChatGreeting();
  window.requestAnimationFrame(() => chatInputEl?.focus());
}

function handleFloatingAssistantClick(event) {
  if (floatingAssistantDrag.suppressClick) {
    event.preventDefault();
    floatingAssistantDrag.suppressClick = false;
    return;
  }
  openAssistantView();
}

function initFloatingAssistant() {
  if (!floatingAssistantEl) {
    return;
  }
  const clampFloatingTop = (top) => {
    const rect = floatingAssistantEl.getBoundingClientRect();
    const padding = 12;
    const minTop = padding;
    const maxTop = Math.max(minTop, window.innerHeight - rect.height - padding);
    return Math.min(Math.max(top, minTop), maxTop);
  };

  const setTop = (top) => {
    floatingAssistantEl.style.top = `${clampFloatingTop(top)}px`;
  };

  floatingAssistantEl.addEventListener("click", handleFloatingAssistantClick);
  floatingAssistantEl.addEventListener("pointerdown", (event) => {
    floatingAssistantDrag.pointerId = event.pointerId;
    floatingAssistantDrag.offsetY = event.clientY - floatingAssistantEl.getBoundingClientRect().top;
    floatingAssistantDrag.startY = event.clientY;
    floatingAssistantDrag.moved = false;
    floatingAssistantEl.setPointerCapture(event.pointerId);
  });

  floatingAssistantEl.addEventListener("pointermove", (event) => {
    if (floatingAssistantDrag.pointerId !== event.pointerId) {
      return;
    }
    const distance = Math.abs(event.clientY - floatingAssistantDrag.startY);
    if (distance > 4) {
      floatingAssistantDrag.moved = true;
      floatingAssistantEl.classList.add("is-dragging");
    }
    setTop(event.clientY - floatingAssistantDrag.offsetY);
  });

  floatingAssistantEl.addEventListener("pointerup", (event) => {
    if (floatingAssistantDrag.pointerId !== event.pointerId) {
      return;
    }
    floatingAssistantEl.releasePointerCapture(event.pointerId);
    floatingAssistantEl.classList.remove("is-dragging");
    floatingAssistantDrag.pointerId = null;
    floatingAssistantDrag.suppressClick = floatingAssistantDrag.moved;
  });

  floatingAssistantEl.addEventListener("pointercancel", (event) => {
    if (floatingAssistantDrag.pointerId !== event.pointerId) {
      return;
    }
    floatingAssistantEl.classList.remove("is-dragging");
    floatingAssistantDrag.pointerId = null;
    floatingAssistantDrag.suppressClick = false;
  });

  window.addEventListener("resize", () => {
    setTop(floatingAssistantEl.getBoundingClientRect().top);
  });
}

function renderChatMessages() {
  if (!chatMessagesEl) {
    return;
  }
  chatMessagesEl.innerHTML = state.chatHistory
    .map((entry) => renderChatEntry(entry))
    .join("");
  chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
}

function renderChatEntry(entry) {
  if (entry.loading) {
    return `
      <div class="chat-message assistant loading">
        <div class="chat-bubble">正在检索标准库…</div>
      </div>`;
  }
  const classes = ["chat-message", entry.role];
  if (entry.error) {
    classes.push("error");
  }
  const sources = renderChatSources(entry.sources || []);
  const bubble = entry.role === "assistant"
    ? renderMarkdown(entry.answer || "")
    : escapeHtml(entry.answer || "");
  return `
    <div class="${classes.join(" ")}">
      <div class="chat-bubble">${bubble}</div>
      ${sources}
    </div>`;
}

function renderMarkdown(value) {
  const text = stripThinkBlocks(String(value || ""));
  const lines = text.split(/\r?\n/);
  const html = [];
  let listType = "";
  let index = 0;

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = "";
    }
  };

  while (index < lines.length) {
    const rawLine = lines[index];
    const line = rawLine.trim();
    if (!line) {
      closeList();
      index += 1;
      continue;
    }

    if (isMarkdownTableStart(lines, index)) {
      closeList();
      const table = collectMarkdownTable(lines, index);
      html.push(renderMarkdownTable(table.rows));
      index = table.nextIndex;
      continue;
    }

    if (/^---+$/.test(line)) {
      closeList();
      html.push("<hr>");
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length + 2;
      html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }

    const unordered = line.match(/^[-*]\s+(.+)$/);
    if (unordered) {
      if (listType !== "ul") {
        closeList();
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      index += 1;
      continue;
    }

    const ordered = line.match(/^\d+[.、]\s+(.+)$/);
    if (ordered) {
      if (listType !== "ol") {
        closeList();
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      index += 1;
      continue;
    }

    closeList();
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
    index += 1;
  }

  closeList();
  return `<div class="chat-markdown">${html.join("")}</div>`;
}

function isMarkdownTableStart(lines, index) {
  const current = (lines[index] || "").trim();
  const next = (lines[index + 1] || "").trim();
  return isMarkdownTableRow(current) && isMarkdownTableSeparator(next);
}

function collectMarkdownTable(lines, startIndex) {
  const rows = [];
  let index = startIndex;
  while (index < lines.length) {
    const line = (lines[index] || "").trim();
    if (!isMarkdownTableRow(line)) {
      break;
    }
    if (!isMarkdownTableSeparator(line)) {
      rows.push(parseMarkdownTableRow(line));
    }
    index += 1;
  }
  return { rows, nextIndex: index };
}

function renderMarkdownTable(rows) {
  if (!rows.length) {
    return "";
  }
  const header = rows[0];
  const body = rows.slice(1);
  return `
    <div class="chat-table-wrap">
      <table>
        <thead>
          <tr>${header.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr>
        </thead>
        <tbody>
          ${body
            .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`)
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function isMarkdownTableRow(line) {
  return line.startsWith("|") && line.endsWith("|") && line.split("|").length >= 3;
}

function isMarkdownTableSeparator(line) {
  if (!isMarkdownTableRow(line)) {
    return false;
  }
  return parseMarkdownTableRow(line).every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function parseMarkdownTableRow(line) {
  return line
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

function stripThinkBlocks(value) {
  return value
    .replace(/<think\b[^>]*>[\s\S]*?<\/think>/gi, "")
    .replace(/<think\b[^>]*>[\s\S]*$/gi, "")
    .trim();
}

function renderChatSources(sources) {
  if (!sources.length) {
    return "";
  }
  const items = sources
    .map((source) => {
      const label = `${source.product || ""} / ${source.item || ""}`.trim().replace(/^[/ ]+|[/ ]+$/g, "");
      const standard = source.standard ? `（${escapeHtml(source.standard)}）` : "";
      const requirement = source.requirement ? `: ${escapeHtml(source.requirement)}` : "";
      const meta = source.source_id ? `<span class="source-meta">来源：${escapeHtml(source.source_id)}</span>` : "";
      return `<li><strong>${escapeHtml(label || source.product || "标准条款")}</strong>${standard}${requirement}${meta}</li>`;
    })
    .join("");
  return `
    <details class="chat-sources">
      <summary>查看 ${sources.length} 条来源</summary>
      <ul>${items}</ul>
    </details>`;
}

function renderNav() {
  navEl.innerHTML = state.materialGroups
    .map((group) => renderNavGroup(group))
    .join("");

  navEl.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => loadMaterial(button.dataset.material));
  });
}

function renderNavGroup(group) {
  const name = group.name || "标准库";
  const label = name === "国内标准" ? "CN 国内标准" : name;
  const materials = group.materials || [];
  return `
    <div class="nav-group">
      <div class="nav-group-title">${escapeHtml(label)}</div>
      ${materials
        .map(
          (material) =>
            `<button type="button" data-material="${escapeHtml(material)}">${escapeHtml(material)}</button>`
        )
        .join("")}
    </div>
  `;
}

async function runSearch(rawQuery) {
  const query = String(rawQuery || queryInput.value || "").trim();
  if (!query) {
    return;
  }

  showView("library");
  queryInput.value = query;
  const data = await fetchJson(`/api/fuzzy-search?q=${encodeURIComponent(query)}`);
  renderFuzzySearchResult(data);
}

async function loadMaterial(material) {
  const data = await fetchJson(`/api/material-table?q=${encodeURIComponent(material)}`);
  state.activeMaterial = data.material;
  showView("library");
  assistantPanel.classList.add("hidden");
  queryInput.value = data.material;
  setActiveNav(data.material);
  renderMaterialTable(data);
}

function showView(view) {
  state.currentView = view;
  homeView.classList.toggle("view-hidden", view !== "home");
  libraryView.classList.toggle("view-hidden", view !== "library");
  assistantView.classList.toggle("view-hidden", view !== "assistant");
  navHome.classList.toggle("active", view === "home");
  navLibrary.classList.toggle("active", view === "library");
  navAssistant.classList.toggle("active", view === "assistant");
}

function renderFuzzySearchResult(data) {
  const query = data.query || queryInput.value || "";
  queryInput.value = query;
  renderSearchSummary(data);

  if (data.result_type === "material_table" && data.table) {
    state.activeMaterial = data.table.material || "";
    setActiveNav(state.activeMaterial);
    renderMaterialTable({
      ...data.table,
      highlight_terms: data.matched_terms || [],
    });
    return;
  }

  setActiveNav("");
  renderClauseRowsAsTable(query, data.results || []);
}

function renderSearchSummary(data) {
  const summary = data.summary || "已完成模糊检索。";
  assistantPanel.classList.remove("hidden");
  summaryEl.textContent = summary;

  const chips = [];
  if (data.matched_material) {
    chips.push({ label: `材料：${data.matched_material}`, tone: "matched" });
  }
  (data.matched_terms || []).forEach((term) => {
    chips.push({ label: `命中：${term}`, tone: "matched" });
  });
  (data.missing_terms || []).forEach((term) => {
    chips.push({ label: `未命中：${term}`, tone: "missing" });
  });

  suggestionsEl.innerHTML = chips
    .map((chip) => `<span class="suggestion ${chip.tone}">${escapeHtml(chip.label)}</span>`)
    .join("");
}

function renderMaterialTable(data) {
  tableTitleEl.textContent = data.material;
  tableSubtitleEl.textContent = `${data.title}，共 ${data.rows.length} 行数据`;
  breadcrumbEl.textContent = `首页 › ${data.group || "标准库"} › ${data.material}`;
  countEl.textContent = `${data.rows.length} 行`;

  const columns = [...data.base_columns, ...data.standard_columns];
  resultsEl.innerHTML = `
    <table style="min-width: ${tableMinWidth(columns)}px;">
      ${renderColumnGroup(columns)}
      <thead>
        <tr class="table-band">
          <th colspan="${columns.length}">${escapeHtml(data.title)}</th>
        </tr>
        <tr>
          ${columns
            .map((column) => `<th class="${columnClass(column)}">${escapeHtml(displayColumnName(column))}</th>`)
            .join("")}
        </tr>
      </thead>
      <tbody>
        ${data.rows
          .map(
            (row) => `
              <tr${isMatchedRow(row, data.highlight_terms || []) ? ' class="match-row"' : ""}>
                ${columns
                  .map(
                    (column) =>
                      `<td class="${columnClass(column)} requirement">${escapeHtml(row[column] || "")}</td>`
                  )
                  .join("")}
              </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

function renderClauseRowsAsTable(query, clauses) {
  tableTitleEl.textContent = `检索结果：${query}`;
  tableSubtitleEl.textContent = "未匹配到单一材料时，以下为严格来自标准库的条款结果";
  breadcrumbEl.textContent = `首页 › 检索 › ${query}`;
  countEl.textContent = `${clauses.length} 条`;

  if (!clauses.length) {
    resultsEl.innerHTML = `<div class="empty">暂无结果</div>`;
    return;
  }

  const columns = ["材料/产品", "项目名称", "标准", "技术要求", "来源"];
  resultsEl.innerHTML = `
    <table style="min-width: ${tableMinWidth(columns)}px;">
      ${renderColumnGroup(columns)}
      <thead>
        <tr>
          <th class="part-col">材料/产品</th>
          <th class="item-col">项目名称</th>
          <th class="standard-col">标准</th>
          <th class="standard-col">技术要求</th>
          <th class="part-col">来源</th>
        </tr>
      </thead>
      <tbody>
        ${clauses
          .map(
            (row) => `
              <tr id="${escapeHtml(String(row.source_link).slice(1))}">
                <td>${escapeHtml(row.product)}</td>
                <td class="item-col">${escapeHtml(row.item)}</td>
                <td>${escapeHtml(row.standard)}</td>
                <td class="requirement">${escapeHtml(row.requirement)}</td>
                <td><a class="source-link" href="${escapeHtml(row.source_link)}">${escapeHtml(
                  row.source_id
                )}</a></td>
              </tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

function setActiveNav(material) {
  navEl.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", button.dataset.material === material);
  });
}

function findMaterial(query) {
  const normalizedQuery = normalize(query);
  return (
    state.materials.find((material) => normalize(material) === normalizedQuery) ||
    state.materials.find((material) => normalize(material).includes(normalizedQuery)) ||
    state.materials.find((material) => normalizedQuery.includes(normalize(material))) ||
    ""
  );
}

function renderColumnGroup(columns) {
  return `
      <colgroup>
        ${columns.map((column) => `<col class="${columnClass(column)}">`).join("")}
      </colgroup>`;
}

function tableMinWidth(columns) {
  return columns.reduce((total, column) => total + columnWidth(column), 0);
}

function columnWidth(column) {
  const className = columnClass(column);
  if (className === "index-col") {
    return 64;
  }
  if (className === "part-col" || className === "source-col") {
    return 120;
  }
  if (className === "item-col") {
    return 180;
  }
  return 220;
}

function isMatchedRow(row, terms) {
  if (!terms.length) {
    return false;
  }
  const haystack = normalize(Object.values(row).join(""));
  return terms.some((term) => haystack.includes(normalize(term)));
}

function columnClass(column) {
  if (column === "序号") {
    return "index-col";
  }
  if (column === "部件" || column === "材料/产品") {
    return "part-col";
  }
  if (column === "检测项目" || column === "项目名称") {
    return "item-col";
  }
  if (column === "来源") {
    return "source-col";
  }
  return "standard-col";
}

function displayColumnName(column) {
  return column === "检测项目" ? "项目名称" : column;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return response.json();
}

function normalize(value) {
  return String(value)
    .toUpperCase()
    .replaceAll("Ⅰ", "I")
    .replaceAll("Ⅱ", "II")
    .replace(/[\s　《》〈〉（）()第部分：:、，,。./\\\-—_]/g, "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

loadMeta().catch((error) => {
  metaEl.textContent = error.message;
});
