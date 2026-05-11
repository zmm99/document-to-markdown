const state = {
  user: null,
  tasks: [],
  documents: [],
  selectedTaskId: null,
  selectedFileId: null,
  pollTimer: null,
  taskPagination: {
    page: 1,
    pageSize: 10,
    total: 0,
  },
  documentPagination: {
    page: 1,
    pageSize: 10,
    total: 0,
  },
};

const els = {
  loginView: document.getElementById("loginView"),
  appView: document.getElementById("appView"),
  loginForm: document.getElementById("loginForm"),
  loginMessage: document.getElementById("loginMessage"),
  usernameInput: document.getElementById("usernameInput"),
  passwordInput: document.getElementById("passwordInput"),
  logoutButton: document.getElementById("logoutButton"),
  refreshButton: document.getElementById("refreshButton"),
  sessionText: document.getElementById("sessionText"),
  uploadForm: document.getElementById("uploadForm"),
  fileInput: document.getElementById("fileInput"),
  uploadMessage: document.getElementById("uploadMessage"),
  taskStatusFilter: document.getElementById("taskStatusFilter"),
  taskDateRangeButton: document.getElementById("taskDateRangeButton"),
  taskDateRangeMenu: document.getElementById("taskDateRangeMenu"),
  taskStartDateInput: document.getElementById("taskStartDateInput"),
  taskEndDateInput: document.getElementById("taskEndDateInput"),
  taskDateRangeClear: document.getElementById("taskDateRangeClear"),
  taskDateRangeApply: document.getElementById("taskDateRangeApply"),
  taskSearchInput: document.getElementById("taskSearchInput"),
  taskTableBody: document.getElementById("taskTableBody"),
  taskCount: document.getElementById("taskCount"),
  taskPageSizeSelect: document.getElementById("taskPageSizeSelect"),
  taskPrevPageButton: document.getElementById("taskPrevPageButton"),
  taskNextPageButton: document.getElementById("taskNextPageButton"),
  taskPageInfo: document.getElementById("taskPageInfo"),
  documentFormatFilter: document.getElementById("documentFormatFilter"),
  documentDateRangeButton: document.getElementById("documentDateRangeButton"),
  documentDateRangeMenu: document.getElementById("documentDateRangeMenu"),
  documentStartDateInput: document.getElementById("documentStartDateInput"),
  documentEndDateInput: document.getElementById("documentEndDateInput"),
  documentDateRangeClear: document.getElementById("documentDateRangeClear"),
  documentDateRangeApply: document.getElementById("documentDateRangeApply"),
  documentSearchInput: document.getElementById("documentSearchInput"),
  documentTableBody: document.getElementById("documentTableBody"),
  documentCount: document.getElementById("documentCount"),
  documentPageSizeSelect: document.getElementById("documentPageSizeSelect"),
  documentPrevPageButton: document.getElementById("documentPrevPageButton"),
  documentNextPageButton: document.getElementById("documentNextPageButton"),
  documentPageInfo: document.getElementById("documentPageInfo"),
  modalOverlay: document.getElementById("modalOverlay"),
  modalTitle: document.getElementById("modalTitle"),
  modalBody: document.getElementById("modalBody"),
  modalCloseButton: document.getElementById("modalCloseButton"),
  toast: document.getElementById("toast"),
};

const terminalStatuses = new Set(["success", "failed", "timeout", "cancelled"]);

const statusLabels = {
  queued: "排队中",
  running: "转换中",
  success: "成功",
  failed: "失败",
  timeout: "超时",
  cancelled: "已取消",
  uploaded: "已上传",
};

const stageLabels = {
  created: "已创建",
  queued: "排队中",
  validating: "校验文件",
  converting: "转换中",
  completed: "已完成",
  failed: "失败",
  timeout: "超时",
  cancelled: "已取消",
  interrupted: "已中断",
};

const messageLabels = {
  "task is waiting for conversion": "等待转换",
  "retry task is waiting for conversion": "重试任务等待转换",
  "reconvert task is waiting for conversion": "重新转换任务等待执行",
  "file validation completed": "文件校验完成",
  "document conversion started": "开始转换文档",
  "document conversion completed": "转换完成",
  "document conversion completed from cache": "命中缓存，转换完成",
  "task was cancelled": "任务已取消",
  "task was cancelled before deletion": "任务删除前已取消",
  "task was interrupted by service restart": "服务重启导致任务中断",
  "document conversion failed": "文档转换失败",
  "document conversion timed out": "文档转换超时",
  "uploaded file not found": "上传文件不存在",
  waiting: "等待中",
};

function translateStatus(value) {
  return statusLabels[value] || value || "";
}

function translateStage(value) {
  return stageLabels[value] || value || "";
}

function translateMessage(value) {
  return messageLabels[value] || value || "";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ["KB", "MB", "GB"];
  let size = bytes / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`;
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    els.toast.hidden = true;
  }, 3200);
}

function apiMessage(errorPayload, fallback) {
  const detail = errorPayload?.detail;
  if (detail?.message) {
    return detail.message;
  }
  if (detail?.error_code) {
    return detail.error_code;
  }
  return fallback;
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    credentials: "include",
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  });

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new Error(apiMessage(payload, `请求失败: ${response.status}`));
  }

  return payload;
}

function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, value);
    }
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

function paginationFor(kind) {
  return kind === "task" ? state.taskPagination : state.documentPagination;
}

function totalPages(pagination) {
  return Math.max(1, Math.ceil((Number(pagination.total) || 0) / pagination.pageSize));
}

function pageOffset(pagination) {
  return (pagination.page - 1) * pagination.pageSize;
}

function updatePagination(kind) {
  const prefix = kind === "task" ? "task" : "document";
  const pagination = paginationFor(kind);
  const pages = totalPages(pagination);
  els[`${prefix}PageInfo`].textContent = `${pagination.page} / ${pages}`;
  els[`${prefix}PrevPageButton`].disabled = pagination.page <= 1;
  els[`${prefix}NextPageButton`].disabled = pagination.page >= pages;
  els[`${prefix}PageSizeSelect`].value = String(pagination.pageSize);
}

async function changePage(kind, direction) {
  const pagination = paginationFor(kind);
  const nextPage = pagination.page + direction;
  if (nextPage < 1 || nextPage > totalPages(pagination)) {
    return;
  }
  pagination.page = nextPage;
  if (kind === "task") {
    await refreshTasks();
  } else {
    await refreshDocuments();
  }
}

async function changePageSize(kind) {
  const prefix = kind === "task" ? "task" : "document";
  const pagination = paginationFor(kind);
  pagination.pageSize = Number(els[`${prefix}PageSizeSelect`].value) || 10;
  pagination.page = 1;
  if (kind === "task") {
    await refreshTasks();
  } else {
    await refreshDocuments();
  }
}

function rangeLabel(start, end) {
  if (start && end) {
    return `${start} 至 ${end}`;
  }
  if (start) {
    return `${start} 起`;
  }
  if (end) {
    return `截至 ${end}`;
  }
  return "日期范围";
}

function updateRangeButton(kind) {
  const prefix = kind === "task" ? "task" : "document";
  const start = els[`${prefix}StartDateInput`].value;
  const end = els[`${prefix}EndDateInput`].value;
  els[`${prefix}DateRangeButton`].textContent = rangeLabel(start, end);
}

function closeRangeMenus(exceptKind = null) {
  if (exceptKind !== "task") {
    els.taskDateRangeMenu.hidden = true;
  }
  if (exceptKind !== "document") {
    els.documentDateRangeMenu.hidden = true;
  }
}

function toggleRangeMenu(kind) {
  const prefix = kind === "task" ? "task" : "document";
  const menu = els[`${prefix}DateRangeMenu`];
  const nextHidden = !menu.hidden;
  closeRangeMenus(kind);
  menu.hidden = nextHidden;
}

async function applyRange(kind) {
  const prefix = kind === "task" ? "task" : "document";
  const start = els[`${prefix}StartDateInput`].value;
  const end = els[`${prefix}EndDateInput`].value;
  if (start && end && start > end) {
    showToast("开始日期不能晚于结束日期");
    return;
  }
  updateRangeButton(kind);
  closeRangeMenus();
  if (kind === "task") {
    await refreshTasks({ resetPage: true });
  } else {
    await refreshDocuments({ resetPage: true });
  }
}

async function clearRange(kind) {
  const prefix = kind === "task" ? "task" : "document";
  els[`${prefix}StartDateInput`].value = "";
  els[`${prefix}EndDateInput`].value = "";
  updateRangeButton(kind);
  closeRangeMenus();
  if (kind === "task") {
    await refreshTasks({ resetPage: true });
  } else {
    await refreshDocuments({ resetPage: true });
  }
}

function setView(authenticated) {
  els.loginView.hidden = authenticated;
  els.appView.hidden = !authenticated;
}

function openModal(title, bodyHtml) {
  els.modalTitle.textContent = title;
  els.modalBody.innerHTML = bodyHtml;
  els.modalOverlay.hidden = false;
}

function closeModal() {
  els.modalOverlay.hidden = true;
  els.modalTitle.textContent = "";
  els.modalBody.innerHTML = "";
}

function linkButton(url, text, enabled = true) {
  if (!url || !enabled) {
    return `<a class="button disabled" href="#" tabindex="-1" aria-disabled="true">${escapeHtml(text)}</a>`;
  }
  return `<a class="button" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(text)}</a>`;
}

function stripMarkdownUrlTitle(value) {
  const text = String(value || "").trim();
  if (text.startsWith("<") && text.endsWith(">")) {
    return text.slice(1, -1);
  }
  const match = text.match(/^(\S+)(?:\s+["'][^"']*["'])?$/);
  return match ? match[1] : text;
}

function resolveMarkdownUrl(value, fileId, image = false) {
  const rawUrl = stripMarkdownUrlTitle(value).replaceAll("\\", "/");
  if (!rawUrl) {
    return "#";
  }

  if (/^(https?:|blob:)/i.test(rawUrl) || rawUrl.startsWith("/")) {
    return rawUrl;
  }
  if (image && /^data:image\//i.test(rawUrl)) {
    return rawUrl;
  }
  if (!image && /^mailto:/i.test(rawUrl)) {
    return rawUrl;
  }

  const rawPathPart = rawUrl.split(/[?#]/)[0];
  const suffix = rawUrl.slice(rawPathPart.length);
  const pathPart = rawPathPart.replace(/^\.?\//, "");
  const assetMatch = pathPart.match(/(?:^|\/)assets\/([^/]+)$/i);
  const imageNameMatch = pathPart.match(/^(image-\d+\.[a-z0-9]+)$/i);
  const assetName = assetMatch?.[1] || imageNameMatch?.[1];
  if (image && fileId && assetName) {
    return `/api/documents/${encodeURIComponent(fileId)}/assets/${encodeURIComponent(assetName)}${suffix}`;
  }

  return "#";
}

function renderInlineMarkdown(text, fileId) {
  const tokens = [];
  const stash = (html) => {
    const token = `@@MDTOKEN${tokens.length}@@`;
    tokens.push(html);
    return token;
  };

  let source = String(text || "");
  source = source.replace(/`([^`]+)`/g, (_match, code) => stash(`<code>${escapeHtml(code)}</code>`));
  source = source.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_match, alt, url) => {
    const src = resolveMarkdownUrl(url, fileId, true);
    return stash(
      `<img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy" referrerpolicy="no-referrer">`
    );
  });
  source = source.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_match, label, url) => {
    const href = resolveMarkdownUrl(url, fileId, false);
    return stash(
      `<a href="${escapeHtml(href)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`
    );
  });

  let html = escapeHtml(source)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*\s][^*]*?)\*/g, "<em>$1</em>")
    .replace(/_([^_\s][^_]*?)_/g, "<em>$1</em>");

  tokens.forEach((tokenHtml, index) => {
    html = html.replaceAll(`@@MDTOKEN${index}@@`, tokenHtml);
  });
  return html;
}

function isTableSeparator(line) {
  if (!line.includes("|")) {
    return false;
  }
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim()));
}

function splitTableRow(line) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function isMarkdownBlockStart(line, nextLine) {
  const trimmed = line.trim();
  return (
    /^#{1,6}\s+/.test(trimmed) ||
    /^```/.test(trimmed) ||
    /^>\s?/.test(trimmed) ||
    /^[-*+]\s+/.test(trimmed) ||
    /^\d+\.\s+/.test(trimmed) ||
    /^[-*_]{3,}$/.test(trimmed) ||
    (line.includes("|") && nextLine && isTableSeparator(nextLine))
  );
}

function renderMarkdown(markdown, fileId) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }

    const fence = trimmed.match(/^```(\w+)?/);
    if (fence) {
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      const lang = fence[1] ? ` data-lang="${escapeHtml(fence[1])}"` : "";
      html.push(`<pre${lang}><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      html.push(`<h${level}>${renderInlineMarkdown(heading[2], fileId)}</h${level}>`);
      index += 1;
      continue;
    }

    if (/^[-*_]{3,}$/.test(trimmed)) {
      html.push("<hr>");
      index += 1;
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = splitTableRow(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].trim() && lines[index].includes("|")) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      html.push(
        `<div class="markdown-table-wrap"><table><thead><tr>${headers
          .map((cell) => `<th>${renderInlineMarkdown(cell, fileId)}</th>`)
          .join("")}</tr></thead><tbody>${rows
          .map(
            (row) =>
              `<tr>${headers
                .map((_header, cellIndex) => `<td>${renderInlineMarkdown(row[cellIndex] || "", fileId)}</td>`)
                .join("")}</tr>`
          )
          .join("")}</tbody></table></div>`
      );
      continue;
    }

    if (/^>\s?/.test(trimmed)) {
      const quoteLines = [];
      while (index < lines.length && /^>\s?/.test(lines[index].trim())) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      html.push(`<blockquote>${renderMarkdown(quoteLines.join("\n"), fileId)}</blockquote>`);
      continue;
    }

    if (/^[-*+]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
      const ordered = /^\d+\.\s+/.test(trimmed);
      const items = [];
      const itemPattern = ordered ? /^\d+\.\s+(.+)$/ : /^[-*+]\s+(.+)$/;
      while (index < lines.length && itemPattern.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(itemPattern, "$1"));
        index += 1;
      }
      html.push(
        `<${ordered ? "ol" : "ul"}>${items
          .map((item) => `<li>${renderInlineMarkdown(item, fileId)}</li>`)
          .join("")}</${ordered ? "ol" : "ul"}>`
      );
      continue;
    }

    const paragraphLines = [trimmed];
    index += 1;
    while (
      index < lines.length &&
      lines[index].trim() &&
      !isMarkdownBlockStart(lines[index], lines[index + 1])
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    html.push(`<p>${renderInlineMarkdown(paragraphLines.join(" "), fileId)}</p>`);
  }

  return `<article class="markdown-rendered">${html.join("")}</article>`;
}

async function checkSession() {
  try {
    const data = await apiFetch("/api/auth/me");
    state.user = data.username;
    els.sessionText.textContent = `当前账号: ${data.username}`;
    setView(true);
    await refreshAll();
  } catch {
    state.user = null;
    setView(false);
  }
}

async function login(event) {
  event.preventDefault();
  els.loginMessage.textContent = "";
  try {
    const data = await apiFetch("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: els.usernameInput.value.trim(),
        password: els.passwordInput.value,
      }),
    });
    state.user = data.username;
    els.passwordInput.value = "";
    els.sessionText.textContent = `当前账号: ${data.username}`;
    setView(true);
    await refreshAll();
  } catch (error) {
    els.loginMessage.textContent = error.message;
  }
}

async function logout() {
  await apiFetch("/api/auth/logout", { method: "POST" });
  stopPolling();
  closeModal();
  state.user = null;
  setView(false);
}

async function uploadFile(event) {
  event.preventDefault();
  const file = els.fileInput.files[0];
  if (!file) {
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  els.uploadMessage.textContent = "上传中";

  try {
    const task = await apiFetch("/api/tasks/convert", {
      method: "POST",
      body: formData,
    });
    els.uploadMessage.textContent = `任务已创建: ${task.task_id}`;
    state.selectedTaskId = task.task_id;
    els.fileInput.value = "";
    await refreshTasks({ resetPage: true });
    startPolling(task.task_id);
  } catch (error) {
    els.uploadMessage.textContent = error.message;
  }
}

async function refreshTasks(options = {}) {
  if (options.resetPage) {
    state.taskPagination.page = 1;
  }
  const pagination = state.taskPagination;
  const data = await apiFetch(
    `/api/tasks${buildQuery({
      status: els.taskStatusFilter.value,
      q: els.taskSearchInput.value.trim(),
      start_date: els.taskStartDateInput.value,
      end_date: els.taskEndDateInput.value,
      limit: pagination.pageSize,
      offset: pageOffset(pagination),
    })}`
  );
  pagination.total = Number(data.total) || 0;
  const pages = totalPages(pagination);
  if (pagination.page > pages) {
    pagination.page = pages;
    return refreshTasks();
  }
  state.tasks = data.items;
  els.taskCount.textContent = `共 ${pagination.total} 条`;
  updatePagination("task");
  renderTasks();
}

async function refreshDocuments(options = {}) {
  if (options.resetPage) {
    state.documentPagination.page = 1;
  }
  const pagination = state.documentPagination;
  const data = await apiFetch(
    `/api/documents${buildQuery({
      file_format: els.documentFormatFilter.value,
      q: els.documentSearchInput.value.trim(),
      start_date: els.documentStartDateInput.value,
      end_date: els.documentEndDateInput.value,
      limit: pagination.pageSize,
      offset: pageOffset(pagination),
    })}`
  );
  pagination.total = Number(data.total) || 0;
  const pages = totalPages(pagination);
  if (pagination.page > pages) {
    pagination.page = pages;
    return refreshDocuments();
  }
  state.documents = data.items;
  els.documentCount.textContent = `共 ${pagination.total} 条`;
  updatePagination("document");
  renderDocuments();
}

async function refreshAll(options = {}) {
  await Promise.all([refreshTasks(options), refreshDocuments(options)]);
}

function renderTasks() {
  els.taskTableBody.innerHTML = state.tasks
    .map((task) => {
      const selected = task.task_id === state.selectedTaskId ? "selected" : "";
      const canCancel = task.status === "queued";
      const canRetry = !["queued", "running"].includes(task.status);
      const canDelete = task.status !== "running";
      return `
        <tr class="${selected}">
          <td>
            <div class="task-name" title="${escapeHtml(task.original_filename)}">${escapeHtml(task.original_filename)}</div>
            <small>${escapeHtml(task.task_id)}</small>
          </td>
          <td><span class="status ${escapeHtml(task.status)}">${escapeHtml(translateStatus(task.status))}</span></td>
          <td>
            <div class="progress-track"><div class="progress-bar" style="width:${Number(task.progress) || 0}%"></div></div>
            <small>${Number(task.progress) || 0}% · ${escapeHtml(translateStage(task.stage))}</small>
          </td>
          <td>
            <div class="row-actions">
              <button type="button" data-action="view-task" data-id="${escapeHtml(task.task_id)}">详情</button>
              <button type="button" data-action="cancel-task" data-id="${escapeHtml(task.task_id)}" ${canCancel ? "" : "disabled"}>取消</button>
              <button type="button" data-action="retry-task" data-id="${escapeHtml(task.task_id)}" ${canRetry ? "" : "disabled"}>重试</button>
              <button class="danger" type="button" data-action="delete-task" data-id="${escapeHtml(task.task_id)}" ${canDelete ? "" : "disabled"}>删除</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function renderDocuments() {
  els.documentTableBody.innerHTML = state.documents
    .map((documentItem) => {
      const selected = documentItem.file_id === state.selectedFileId ? "selected" : "";
      return `
        <tr class="${selected}">
          <td>
            <div class="file-name" title="${escapeHtml(documentItem.original_filename)}">${escapeHtml(documentItem.original_filename)}</div>
            <small>${escapeHtml(documentItem.file_id)}</small>
          </td>
          <td>${escapeHtml(documentItem.file_format)}</td>
          <td>${escapeHtml(formatBytes(documentItem.file_size))}</td>
          <td>${Number(documentItem.asset_count) || 0}</td>
          <td><small>${escapeHtml(documentItem.updated_at || documentItem.created_at || "")}</small></td>
          <td>
            <div class="download-actions">
              ${linkButton(documentItem.original_url, "原始")}
              ${linkButton(documentItem.download_url, "Markdown包", documentItem.status === "success")}
            </div>
          </td>
          <td>
            <div class="row-actions">
              <button type="button" data-action="preview-document" data-id="${escapeHtml(documentItem.file_id)}" ${documentItem.status === "success" ? "" : "disabled"}>预览</button>
              <button type="button" data-action="detail-document" data-id="${escapeHtml(documentItem.file_id)}">详情</button>
              <button type="button" data-action="reconvert-document" data-id="${escapeHtml(documentItem.file_id)}">重转</button>
              <button type="button" data-action="delete-cache" data-id="${escapeHtml(documentItem.file_id)}">删缓存</button>
              <button class="danger" type="button" data-action="delete-document" data-id="${escapeHtml(documentItem.file_id)}">删文件</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

function detailRow(label, value) {
  return `<dt>${escapeHtml(label)}</dt><dd>${value || ""}</dd>`;
}

function taskDetailHtml(task) {
  const actions = task.file_id
    ? `<div class="modal-actions">
        ${linkButton(task.document_url, "文档信息")}
        ${linkButton(task.markdown_url, "Markdown", task.status === "success")}
        ${linkButton(task.download_url, "Markdown包", task.status === "success")}
      </div>`
    : "";
  return `
    ${actions}
    <dl class="detail-grid">
      ${detailRow("任务 ID", escapeHtml(task.task_id))}
      ${detailRow("文件 ID", escapeHtml(task.file_id || ""))}
      ${detailRow("文件名", escapeHtml(task.original_filename))}
      ${detailRow("格式", escapeHtml(task.file_format))}
      ${detailRow("状态", `<span class="status ${escapeHtml(task.status)}">${escapeHtml(translateStatus(task.status))}</span>`)}
      ${detailRow("进度", `${Number(task.progress) || 0}%`)}
      ${detailRow("阶段", escapeHtml(translateStage(task.stage)))}
      ${detailRow("信息", escapeHtml(translateMessage(task.message)))}
      ${detailRow("错误码", escapeHtml(task.error_code || ""))}
      ${detailRow("错误信息", escapeHtml(translateMessage(task.error_message)))}
      ${detailRow("缓存命中", task.cached ? "是" : "否")}
      ${detailRow("创建时间", escapeHtml(task.created_at || ""))}
      ${detailRow("开始时间", escapeHtml(task.started_at || ""))}
      ${detailRow("结束时间", escapeHtml(task.finished_at || ""))}
      ${detailRow("更新时间", escapeHtml(task.updated_at || ""))}
    </dl>
  `;
}

function documentDetailHtml(info) {
  const assetLinks = (info.assets || [])
    .map((asset) => `<a href="${escapeHtml(asset.url)}" target="_blank" rel="noreferrer">${escapeHtml(asset.name)}</a>`)
    .join("");
  const metadata = Object.keys(info.metadata || {}).length
    ? `<pre class="markdown-preview">${escapeHtml(JSON.stringify(info.metadata, null, 2))}</pre>`
    : "";
  return `
    <div class="modal-actions">
      ${linkButton(info.original_url, "下载原始文件")}
      ${linkButton(info.markdown_url, "打开 Markdown", info.status === "success")}
      ${linkButton(info.download_url, "下载 Markdown 压缩包", info.status === "success")}
    </div>
    <dl class="detail-grid">
      ${detailRow("文件 ID", escapeHtml(info.file_id))}
      ${detailRow("原始文件名", escapeHtml(info.original_filename))}
      ${detailRow("格式", escapeHtml(info.file_format))}
      ${detailRow("MIME", escapeHtml(info.mime_type || ""))}
      ${detailRow("大小", escapeHtml(formatBytes(info.file_size)))}
      ${detailRow("存储日期", escapeHtml(info.storage_date || ""))}
      ${detailRow("状态", `<span class="status ${escapeHtml(info.status)}">${escapeHtml(translateStatus(info.status))}</span>`)}
      ${detailRow("创建时间", escapeHtml(info.created_at || ""))}
      ${detailRow("更新时间", escapeHtml(info.updated_at || ""))}
      ${detailRow("解析引擎", escapeHtml(info.parse_record?.engine || ""))}
      ${detailRow("解析时间", escapeHtml(info.parse_record?.created_at || ""))}
      ${detailRow("错误码", escapeHtml(info.error_code || info.parse_record?.error_code || ""))}
      ${detailRow("错误信息", escapeHtml(translateMessage(info.message || info.parse_record?.error_message)))}
      ${detailRow("警告", escapeHtml((info.warnings || []).join("; ")))}
      ${detailRow("附件", `<div class="asset-list">${assetLinks || "无"}</div>`)}
    </dl>
    ${metadata}
  `;
}

async function showTaskDetails(taskId) {
  const task = await apiFetch(`/api/tasks/${taskId}`);
  state.selectedTaskId = task.task_id;
  if (task.file_id) {
    state.selectedFileId = task.file_id;
  }
  renderTasks();
  renderDocuments();
  openModal("任务详情", taskDetailHtml(task));
}

async function showDocumentDetails(fileId) {
  const info = await apiFetch(`/api/documents/${fileId}`);
  state.selectedFileId = fileId;
  renderDocuments();
  openModal("文件详情", documentDetailHtml(info));
}

async function previewDocument(fileId) {
  const info = await apiFetch(`/api/documents/${fileId}`);
  state.selectedFileId = fileId;
  renderDocuments();
  if (!info.markdown_url) {
    openModal("Markdown 预览", `<p>${escapeHtml(info.message || "暂无 Markdown")}</p>`);
    return;
  }

  const response = await fetch(info.markdown_url, { credentials: "include" });
  const markdown = response.ok ? await response.text() : "Markdown 不可用";
  openModal(
    "Markdown 预览",
    `
      <div class="modal-actions">
        ${linkButton(info.original_url, "下载原始文件")}
        ${linkButton(info.download_url, "下载 Markdown 压缩包")}
        ${linkButton(info.markdown_url, "新窗口打开")}
      </div>
      <dl class="detail-grid">
        ${detailRow("文件名", escapeHtml(info.original_filename))}
        ${detailRow("文件 ID", escapeHtml(info.file_id))}
        ${detailRow("格式", escapeHtml(info.file_format))}
        ${detailRow("大小", escapeHtml(formatBytes(info.file_size)))}
      </dl>
      <div class="markdown-preview">${renderMarkdown(markdown, info.file_id)}</div>
    `
  );
}

async function handleTaskAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const action = button.dataset.action;
  const id = button.dataset.id;

  try {
    if (action === "view-task") {
      await showTaskDetails(id);
    }
    if (action === "cancel-task") {
      await apiFetch(`/api/tasks/${id}/cancel`, { method: "POST" });
      showToast("任务已取消");
      await refreshTasks();
    }
    if (action === "retry-task") {
      const task = await apiFetch(`/api/tasks/${id}/retry`, { method: "POST" });
      showToast("重试任务已创建");
      state.selectedTaskId = task.task_id;
      startPolling(task.task_id);
      await refreshTasks({ resetPage: true });
    }
    if (action === "delete-task" && window.confirm("确认删除任务记录？")) {
      await apiFetch(`/api/tasks/${id}`, { method: "DELETE" });
      showToast("任务记录已删除");
      await refreshTasks();
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function handleDocumentAction(event) {
  const button = event.target.closest("button[data-action]");
  if (!button) {
    return;
  }
  const action = button.dataset.action;
  const id = button.dataset.id;

  try {
    if (action === "preview-document") {
      await previewDocument(id);
    }
    if (action === "detail-document") {
      await showDocumentDetails(id);
    }
    if (action === "reconvert-document") {
      const task = await apiFetch(`/api/documents/${id}/reconvert`, { method: "POST" });
      showToast("重新转换任务已创建");
      state.selectedTaskId = task.task_id;
      startPolling(task.task_id);
      await refreshTasks({ resetPage: true });
      await refreshDocuments();
    }
    if (action === "delete-cache" && window.confirm("确认删除转换缓存？")) {
      await apiFetch(`/api/documents/${id}/cache`, { method: "DELETE" });
      showToast("缓存已删除");
      await refreshDocuments();
    }
    if (action === "delete-document" && window.confirm("确认删除文件和转换结果？")) {
      await apiFetch(`/api/documents/${id}`, { method: "DELETE" });
      showToast("文件已删除");
      if (state.selectedFileId === id) {
        state.selectedFileId = null;
        closeModal();
      }
      await refreshAll();
    }
  } catch (error) {
    showToast(error.message);
  }
}

function startPolling(taskId) {
  stopPolling();
  state.pollTimer = window.setInterval(async () => {
    try {
      const task = await apiFetch(`/api/tasks/${taskId}`);
      state.selectedTaskId = task.task_id;
      await refreshTasks();
      if (terminalStatuses.has(task.status)) {
        stopPolling();
        if (task.status === "success") {
          await refreshDocuments();
          showToast("任务已完成");
        }
      }
    } catch (error) {
      stopPolling();
      showToast(error.message);
    }
  }, 1500);
}

function stopPolling() {
  if (state.pollTimer) {
    window.clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

let taskSearchTimer = null;
let documentSearchTimer = null;

els.loginForm.addEventListener("submit", login);
els.logoutButton.addEventListener("click", logout);
els.refreshButton.addEventListener("click", () => refreshAll().catch((error) => showToast(error.message)));
els.uploadForm.addEventListener("submit", uploadFile);
els.taskTableBody.addEventListener("click", handleTaskAction);
els.documentTableBody.addEventListener("click", handleDocumentAction);
els.taskStatusFilter.addEventListener("change", () =>
  refreshTasks({ resetPage: true }).catch((error) => showToast(error.message))
);
els.taskDateRangeButton.addEventListener("click", () => toggleRangeMenu("task"));
els.taskDateRangeApply.addEventListener("click", () => applyRange("task").catch((error) => showToast(error.message)));
els.taskDateRangeClear.addEventListener("click", () => clearRange("task").catch((error) => showToast(error.message)));
els.taskPageSizeSelect.addEventListener("change", () =>
  changePageSize("task").catch((error) => showToast(error.message))
);
els.taskPrevPageButton.addEventListener("click", () => changePage("task", -1).catch((error) => showToast(error.message)));
els.taskNextPageButton.addEventListener("click", () => changePage("task", 1).catch((error) => showToast(error.message)));
els.documentFormatFilter.addEventListener("change", () =>
  refreshDocuments({ resetPage: true }).catch((error) => showToast(error.message))
);
els.documentDateRangeButton.addEventListener("click", () => toggleRangeMenu("document"));
els.documentDateRangeApply.addEventListener("click", () => applyRange("document").catch((error) => showToast(error.message)));
els.documentDateRangeClear.addEventListener("click", () => clearRange("document").catch((error) => showToast(error.message)));
els.documentPageSizeSelect.addEventListener("change", () =>
  changePageSize("document").catch((error) => showToast(error.message))
);
els.documentPrevPageButton.addEventListener("click", () =>
  changePage("document", -1).catch((error) => showToast(error.message))
);
els.documentNextPageButton.addEventListener("click", () =>
  changePage("document", 1).catch((error) => showToast(error.message))
);
els.taskSearchInput.addEventListener("input", () => {
  window.clearTimeout(taskSearchTimer);
  taskSearchTimer = window.setTimeout(
    () => refreshTasks({ resetPage: true }).catch((error) => showToast(error.message)),
    300
  );
});
els.documentSearchInput.addEventListener("input", () => {
  window.clearTimeout(documentSearchTimer);
  documentSearchTimer = window.setTimeout(
    () => refreshDocuments({ resetPage: true }).catch((error) => showToast(error.message)),
    300
  );
});
els.modalCloseButton.addEventListener("click", closeModal);
els.modalOverlay.addEventListener("click", (event) => {
  if (event.target === els.modalOverlay) {
    closeModal();
  }
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".date-range")) {
    closeRangeMenus();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.modalOverlay.hidden) {
    closeModal();
  }
  if (event.key === "Escape") {
    closeRangeMenus();
  }
});

updateRangeButton("task");
updateRangeButton("document");
updatePagination("task");
updatePagination("document");
checkSession();
