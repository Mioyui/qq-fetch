(function () {
  "use strict";

  const boot = window.QQFETCH_BOOT || {};
  const state = {
    source: boot.defaultSource || "local",
    friends: [],
    targetQq: null,
    page: 1,
    pageSize: Number(boot.defaultPageSize || 20),
    sort: "desc",
    preset: "all",
    startDate: "",
    endDate: "",
    shuoshuo: null,
    commentPageSize: Number(boot.defaultCommentPageSize || 10),
    commentState: {}
  };

  const dom = {
    sourceButtons: Array.from(document.querySelectorAll("#source-switch [data-source]")),
    presetButtons: Array.from(document.querySelectorAll("#preset-grid [data-preset]")),
    sortButtons: Array.from(document.querySelectorAll("#sort-switch [data-sort]")),
    friendSelect: document.getElementById("friend-select"),
    friendEmpty: document.getElementById("friend-empty"),
    startDate: document.getElementById("start-date"),
    endDate: document.getElementById("end-date"),
    applyFilters: document.getElementById("apply-filters"),
    filterSummary: document.getElementById("filter-summary"),
    resultMeta: document.getElementById("result-meta"),
    errorBox: document.getElementById("error-box"),
    loadingBox: document.getElementById("loading-box"),
    list: document.getElementById("shuoshuo-list"),
    pager: document.getElementById("main-pager"),
    prevPage: document.getElementById("prev-page"),
    nextPage: document.getElementById("next-page"),
    pageIndicator: document.getElementById("page-indicator")
  };

  async function requestJson(url) {
    const response = await fetch(url);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "请求失败");
    }
    return payload;
  }

  function setLoading(loading) {
    dom.loadingBox.hidden = !loading;
  }

  function showError(message) {
    dom.errorBox.hidden = !message;
    dom.errorBox.textContent = message || "";
  }

  function activateButtonGroup(buttons, key, value) {
    buttons.forEach((button) => {
      button.classList.toggle("is-active", button.dataset[key] === value);
    });
  }

  function resetComments() {
    state.commentState = {};
  }

  async function loadFriends() {
    showError("");
    setLoading(true);
    try {
      const payload = await requestJson(`/api/friends?source=${encodeURIComponent(state.source)}`);
      state.friends = payload.items || [];
      renderFriends();
      if (!state.targetQq || !state.friends.some((item) => Number(item.target_qq) === Number(state.targetQq))) {
        state.targetQq = state.friends.length ? Number(state.friends[0].target_qq) : null;
      }
      state.page = 1;
      resetComments();
      await loadShuoshuo();
    } catch (error) {
      state.friends = [];
      state.targetQq = null;
      renderFriends();
      renderShuoshuo(null);
      showError(error.message);
    } finally {
      setLoading(false);
    }
  }

  function renderFriends() {
    dom.friendSelect.innerHTML = "";
    state.friends.forEach((item) => {
      const option = document.createElement("option");
      option.value = item.target_qq;
      option.textContent = `${item.target_qq} (${item.count})`;
      dom.friendSelect.appendChild(option);
    });
    if (state.targetQq) {
      dom.friendSelect.value = String(state.targetQq);
    }
    const isEmpty = state.friends.length === 0;
    dom.friendSelect.hidden = isEmpty;
    dom.friendEmpty.hidden = !isEmpty;
  }

  async function loadShuoshuo() {
    if (!state.targetQq) {
      renderShuoshuo(null);
      return;
    }
    showError("");
    setLoading(true);
    try {
      const params = new URLSearchParams({
        source: state.source,
        target_qq: String(state.targetQq),
        page: String(state.page),
        page_size: String(state.pageSize),
        sort: state.sort,
        preset: state.preset
      });
      if (state.startDate) {
        params.set("start_date", state.startDate);
      }
      if (state.endDate) {
        params.set("end_date", state.endDate);
      }
      state.shuoshuo = await requestJson(`/api/shuoshuo?${params.toString()}`);
      renderShuoshuo(state.shuoshuo);
    } catch (error) {
      renderShuoshuo(null);
      showError(error.message);
    } finally {
      setLoading(false);
    }
  }

  function renderShuoshuo(payload) {
    dom.list.innerHTML = "";
    if (!payload || !payload.items || payload.items.length === 0) {
      dom.filterSummary.textContent = state.targetQq ? "当前筛选条件下没有说说数据。" : "等待选择好友 QQ。";
      dom.resultMeta.textContent = "";
      dom.pager.hidden = true;
      return;
    }
    dom.filterSummary.textContent = buildSummary(payload.filter_summary || {});
    dom.resultMeta.textContent = `共 ${payload.total} 条`;
    payload.items.forEach((item) => {
      dom.list.appendChild(renderCard(item));
    });
    dom.pageIndicator.textContent = `${payload.page} / ${payload.total_pages}`;
    dom.pager.hidden = false;
    dom.prevPage.disabled = payload.page <= 1;
    dom.nextPage.disabled = payload.page >= payload.total_pages;
  }

  function renderCard(item) {
    const card = document.createElement("article");
    card.className = "feed-item";
    const pictures = (item.pictures || []).map((pic) => `
      <a href="${escapeHtml(pic.url)}" target="_blank" rel="noreferrer">
        <img src="${escapeHtml(pic.url)}" alt="说说图片">
      </a>
    `).join("");
    card.innerHTML = `
      <div class="feed-main">
        <div class="meta-line">
          <span>发布时间 ${escapeHtml(item.created_time_text)}</span>
          <span>点赞 ${item.like_count}</span>
          <span>评论 ${item.comment_count}</span>
        </div>
        <p class="content-text">${escapeMultiline(item.content || "")}</p>
        ${pictures ? `<div class="picture-grid">${pictures}</div>` : ""}
        <div class="feed-footer">
          <span class="meta-line">TID: ${escapeHtml(item.tid)}</span>
          ${item.has_comments ? `<button class="comment-toggle" type="button" data-tid="${escapeHtml(item.tid)}">查看评论</button>` : ""}
        </div>
      </div>
      <div class="comments-box" id="comments-${escapeHtml(item.tid)}" hidden></div>
    `;
    const toggle = card.querySelector(".comment-toggle");
    if (toggle) {
      toggle.addEventListener("click", async () => {
        await toggleComments(item.tid);
      });
    }
    return card;
  }

  function buildSummary(summary) {
    const timeText = summary.start_date || summary.end_date
      ? `${summary.start_date || "最早"} 至 ${summary.end_date || "最新"}`
      : presetLabel(summary.preset || "all");
    const sourceText = summary.source === "postgres" ? "数据库" : "本地";
    return `数据源: ${sourceText} · 时间: ${timeText} · 排序: ${state.sort === "desc" ? "降序" : "升序"}`;
  }

  function presetLabel(value) {
    return {
      all: "全部",
      "7d": "近7天",
      "30d": "近30天",
      "90d": "近90天",
      "1y": "近1年"
    }[value] || "全部";
  }

  async function toggleComments(tid) {
    const box = document.getElementById(`comments-${tid}`);
    if (!box) {
      return;
    }
    const current = state.commentState[tid];
    if (current && !box.hidden) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    await loadComments(tid, 1);
  }

  async function loadComments(tid, page) {
    const box = document.getElementById(`comments-${tid}`);
    if (!box) {
      return;
    }
    box.innerHTML = `<div class="comments-list">正在加载评论…</div>`;
    try {
      const params = new URLSearchParams({
        source: state.source,
        target_qq: String(state.targetQq),
        tid,
        page: String(page),
        page_size: String(state.commentPageSize)
      });
      const payload = await requestJson(`/api/comments?${params.toString()}`);
      state.commentState[tid] = payload;
      renderComments(box, tid, payload);
    } catch (error) {
      box.innerHTML = `<div class="comments-list">加载评论失败: ${escapeHtml(error.message)}</div>`;
    }
  }

  function renderComments(box, tid, payload) {
    const items = payload.items || [];
    const html = items.length
      ? items.map((item) => `
          <div class="comment-item">
            <div class="comment-meta">
              <span class="comment-author">${escapeHtml(item.author_name || item.author_uin || "匿名")}</span>
              <span> · ${escapeHtml(item.created_time_text)}</span>
            </div>
            <div class="comment-content">${escapeMultiline(item.content || "")}</div>
          </div>
        `).join("")
      : `<div class="comment-item">暂无评论。</div>`;
    box.innerHTML = `
      <div class="comments-list">${html}</div>
      <div class="comment-pager">
        <button type="button" data-role="prev">上一页</button>
        <span>${payload.page} / ${payload.total_pages}</span>
        <button type="button" data-role="next">下一页</button>
      </div>
    `;
    const prev = box.querySelector('[data-role="prev"]');
    const next = box.querySelector('[data-role="next"]');
    prev.disabled = payload.page <= 1;
    next.disabled = payload.page >= payload.total_pages;
    prev.addEventListener("click", () => loadComments(tid, payload.page - 1));
    next.addEventListener("click", () => loadComments(tid, payload.page + 1));
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeMultiline(value) {
    return escapeHtml(value).replaceAll("\n", "<br>");
  }

  function syncControls() {
    activateButtonGroup(dom.sourceButtons, "source", state.source);
    activateButtonGroup(dom.presetButtons, "preset", state.preset);
    activateButtonGroup(dom.sortButtons, "sort", state.sort);
    dom.startDate.value = state.startDate;
    dom.endDate.value = state.endDate;
  }

  function bindEvents() {
    dom.sourceButtons.forEach((button) => {
      button.addEventListener("click", async () => {
        state.source = button.dataset.source;
        syncControls();
        await loadFriends();
      });
    });
    dom.sortButtons.forEach((button) => {
      button.addEventListener("click", () => {
        state.sort = button.dataset.sort;
        syncControls();
      });
    });
    dom.presetButtons.forEach((button) => {
      button.addEventListener("click", () => {
        state.preset = button.dataset.preset;
        if (state.preset !== "all") {
          state.startDate = "";
          state.endDate = "";
          dom.startDate.value = "";
          dom.endDate.value = "";
        }
        syncControls();
      });
    });
    dom.startDate.addEventListener("change", () => {
      state.startDate = dom.startDate.value;
      if (state.startDate) {
        state.preset = "all";
        syncControls();
      }
    });
    dom.endDate.addEventListener("change", () => {
      state.endDate = dom.endDate.value;
      if (state.endDate) {
        state.preset = "all";
        syncControls();
      }
    });
    dom.friendSelect.addEventListener("change", async () => {
      state.targetQq = Number(dom.friendSelect.value);
      state.page = 1;
      resetComments();
      await loadShuoshuo();
    });
    dom.applyFilters.addEventListener("click", async () => {
      state.page = 1;
      resetComments();
      await loadShuoshuo();
    });
    dom.prevPage.addEventListener("click", async () => {
      state.page -= 1;
      resetComments();
      await loadShuoshuo();
    });
    dom.nextPage.addEventListener("click", async () => {
      state.page += 1;
      resetComments();
      await loadShuoshuo();
    });
  }

  syncControls();
  bindEvents();
  loadFriends();
})();
