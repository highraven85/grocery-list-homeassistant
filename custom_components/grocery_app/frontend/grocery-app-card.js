/* Grocery App card for Home Assistant. Bundled with the grocery_app integration.
 * Shopping list (todo entity) grouped by department + this week's dinners.
 * No external requests: data comes only through the Home Assistant connection. */
const CARD_VERSION = "1.2.0";

const DEPT_COLORS = {
  "Produce": "#1c6b45", "Meat & Seafood": "#8d3b36", "Dairy & Eggs": "#d7a13a", "Bakery": "#c47a45",
  "Frozen": "#3d7ea6", "Beverages": "#2f6f62", "Canned & Jarred": "#a15a32", "Baking": "#8a6232",
  "Spices": "#b4532a", "Household": "#5d6b73", "Other": "#8a8175",
};
const DAY_MS = 86400000;
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseDay = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d, 12); };
const mondayOf = (d) => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

const STYLE = `
:host { display:block; container-type:inline-size;
  --paper:#f6f1e6; --paper-2:#fffaf1; --ink:#241c14; --muted:#6f6458; --line:#e3d6c2;
  --green:#1c6b45; --green-deep:#123d28; --tomato:#d24b2e; --stamp:#f3ddb4;
  --font:"Figtree","Avenir Next","Segoe UI",Roboto,sans-serif; --display:"Fraunces","Iowan Old Style",Georgia,"Times New Roman",serif; }
* { box-sizing:border-box; }
ha-card, .card { display:block; background:var(--paper); color:var(--ink); font-family:var(--font); border-radius:22px; overflow:hidden; border:1px solid var(--line); box-shadow:0 10px 30px rgba(36,28,20,.10); }
.top { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; padding:22px 24px 6px; }
.eyebrow { letter-spacing:.14em; text-transform:uppercase; font-size:.72rem; font-weight:700; color:var(--green); }
h1 { font-family:var(--display); font-weight:560; font-size:2.1rem; line-height:1.02; margin:4px 0 0; letter-spacing:-.03em; }
h2 { font-family:var(--display); font-weight:560; font-size:1.35rem; margin:0; }
.count { color:var(--muted); font-size:.9rem; }
.cols { display:grid; grid-template-columns:minmax(0,1.15fr) minmax(0,1fr); gap:18px; padding:10px 18px 22px; }
@container (max-width: 820px) { .cols { grid-template-columns:1fr; } h1 { font-size:1.8rem; } }
.panel { background:var(--paper-2); border:1px solid var(--line); border-radius:18px; padding:14px 0 6px; min-width:0; }
.panel-head { display:flex; justify-content:space-between; align-items:baseline; padding:0 16px 8px; }
.add { display:flex; gap:8px; padding:0 16px 8px; }
.add input { flex:1; min-height:48px; border:1px solid var(--line); border-radius:12px; padding:0 14px; background:#fff; font:inherit; font-size:1rem; color:var(--ink); }
.add input:focus { outline:2px solid var(--green); outline-offset:1px; }
.add button { border-radius:12px; background:var(--ink); color:var(--paper); border:0; padding:0 18px; min-height:48px; font:inherit; font-weight:700; cursor:pointer; }
.add button:disabled { opacity:.45; }
.dept header { display:flex; align-items:center; gap:8px; padding:12px 16px 4px; font-family:var(--display); font-size:1.05rem; }
.dept header small { font-family:var(--font); color:var(--muted); font-size:.75rem; font-weight:700; letter-spacing:.04em; }
.mark { width:9px; height:9px; border-radius:99px; background:var(--green); display:inline-block; flex:none; }
.item { display:grid; grid-template-columns:28px minmax(0,1fr) auto; gap:12px; align-items:center; width:100%; padding:10px 16px; min-height:54px; background:transparent; border:0; border-bottom:1px solid var(--line); text-align:left; font:inherit; color:inherit; cursor:pointer; }
.item:last-child { border-bottom:0; }
.box { width:28px; height:28px; border:2px solid var(--green-deep); border-radius:8px; display:grid; place-items:center; color:#fff; font-size:.95rem; font-weight:700; }
.item.done .box { background:var(--green); border-color:var(--green); }
.item.done .name { color:var(--muted); text-decoration:line-through; }
.name { font-weight:560; font-size:1.02rem; }
.qty { color:var(--muted); font-size:.85rem; font-weight:700; text-align:right; max-width:12em; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.done-toggle { width:calc(100% - 32px); margin:10px 16px 8px; min-height:44px; border:1px dashed var(--line); background:transparent; border-radius:12px; color:var(--green-deep); font:inherit; font-weight:700; cursor:pointer; }
.empty { color:var(--muted); padding:8px 16px 14px; }
.week-nav { display:grid; grid-template-columns:44px 1fr 44px; align-items:center; gap:8px; padding:0 12px 10px; text-align:center; font-weight:700; }
.week-nav button { min-height:44px; border-radius:12px; border:1px solid var(--line); background:var(--paper); color:var(--green-deep); font-size:1.3rem; cursor:pointer; }
.week-nav .label small { display:block; color:var(--muted); font-weight:400; font-size:.8rem; }
.days { display:flex; flex-direction:column; gap:8px; padding:0 12px 8px; }
.day { background:#fff; border:1px solid var(--line); border-radius:16px; padding:10px 12px; cursor:pointer; text-align:left; font:inherit; color:inherit; width:100%; }
.day.today { border-color:var(--green); box-shadow:inset 4px 0 0 var(--green); background:#f3f8f1; }
.day.past { opacity:.62; }
.day header { display:flex; justify-content:space-between; align-items:baseline; gap:8px; }
.day header b { font-family:var(--display); font-weight:560; font-size:1.05rem; }
.day header > span { color:var(--muted); font-size:.82rem; white-space:nowrap; }
.day header .badge { background:var(--green); color:#fff; font-family:var(--font); border-radius:99px; padding:2px 8px; font-size:.68rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase; margin-left:6px; vertical-align:middle; }
.summary { display:flex; align-items:center; gap:10px; margin-top:8px; min-width:0; }
.summary .txt { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-weight:700; min-width:0; }
.summary .more { color:var(--muted); font-size:.82rem; white-space:nowrap; }
.none { color:var(--muted); font-style:italic; margin-top:6px; font-size:.92rem; }
.recipes { display:flex; flex-direction:column; gap:8px; margin-top:10px; }
.recipe { display:grid; grid-template-columns:52px minmax(0,1fr); gap:10px; align-items:center; }
.recipe span { font-weight:700; line-height:1.25; }
.thumb { width:52px; height:52px; border-radius:10px; object-fit:cover; background:var(--stamp); display:grid; place-items:center; font-family:var(--display); color:var(--green-deep); font-size:1.3rem; overflow:hidden; }
.thumb.small { width:40px; height:40px; border-radius:9px; font-size:1rem; flex:none; }
.err { color:var(--tomato); padding:4px 16px 10px; font-size:.9rem; }
`;

class GroceryAppCard extends HTMLElement {
  static getStubConfig() { return { title: "Grocery App", todo_entity: "todo.grocery_app", calendar_entity: "calendar.grocery_dinners" }; }
  static getConfigForm() {
    return { schema: [
      { name: "title", selector: { text: {} } },
      { name: "todo_entity", required: true, selector: { entity: { domain: "todo" } } },
      { name: "calendar_entity", required: true, selector: { entity: { domain: "calendar" } } },
    ] };
  }

  setConfig(config) {
    this._config = { title: "Grocery App", todo_entity: "todo.grocery_app", calendar_entity: "calendar.grocery_dinners", ...(config || {}) };
    this._items = this._items || null;
    this._week = this._week || mondayOf(new Date());
    this._expanded = this._expanded || new Set([iso(new Date())]);
    this._dinners = this._dinners || {};
    this._photos = this._photos || {};
    this._showDone = this._showDone || false;
    if (this.shadowRoot) this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    const prevTodo = this._hass?.states[this._config.todo_entity];
    this._hass = hass;
    if (!this.shadowRoot) this._build();
    if (first || !this._unsub) this._subscribe();
    if (first) this._loadWeek();
    if (!first && hass.states[this._config.todo_entity] !== prevTodo) this._renderList();
  }

  getCardSize() { return 12; }
  getGridOptions() { return { columns: "full", min_columns: 6 }; }

  connectedCallback() { if (this._hass && !this._unsub) this._subscribe(); }
  disconnectedCallback() { if (this._unsub) { this._unsub.then((u) => u && u()).catch(() => {}); this._unsub = null; } }

  _build() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${STYLE}</style><ha-card class="card">
      <div class="top"><div><div class="eyebrow">Shopping &amp; dinners</div><h1 id="title"></h1></div><div class="count" id="count"></div></div>
      <div class="cols">
        <section class="panel" aria-label="Shopping list">
          <div class="panel-head"><h2>Shopping list</h2><span class="count" id="left"></span></div>
          <form class="add" id="add"><input id="addInput" placeholder="Add an item, e.g. 2 lb apples" autocomplete="off" aria-label="Add item"><button id="addBtn">Add</button></form>
          <div id="err" class="err" hidden></div>
          <div id="list"></div>
        </section>
        <section class="panel" aria-label="Dinners">
          <div class="panel-head"><h2>What's for dinner</h2></div>
          <div class="week-nav"><button id="prev" aria-label="Previous week">‹</button><div class="label" id="weekLabel"></div><button id="next" aria-label="Next week">›</button></div>
          <div class="days" id="days"></div>
        </section>
      </div></ha-card>`;
    root.getElementById("add").addEventListener("submit", (e) => { e.preventDefault(); this._add(); });
    root.getElementById("list").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-uid]");
      if (btn) this._toggle(btn.dataset.uid);
      if (e.target.closest("#doneToggle")) { this._showDone = !this._showDone; this._renderList(); }
    });
    root.getElementById("days").addEventListener("click", (e) => {
      const day = e.target.closest("[data-day]");
      if (!day) return;
      const key = day.dataset.day;
      this._expanded.has(key) ? this._expanded.delete(key) : this._expanded.add(key);
      this._renderWeek();
    });
    root.getElementById("days").addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target.closest("[data-day]")) { e.preventDefault(); e.target.closest("[data-day]").click(); }
    });
    root.getElementById("prev").addEventListener("click", () => this._shiftWeek(-7));
    root.getElementById("next").addEventListener("click", () => this._shiftWeek(7));
    this._render();
  }

  _render() { if (!this.shadowRoot) return; this.shadowRoot.getElementById("title").textContent = this._config.title; this._renderList(); this._renderWeek(); }

  _subscribe() {
    if (!this._hass?.connection) return;
    this._unsub = this._hass.connection
      .subscribeMessage((msg) => { this._items = msg.items || []; this._renderList(); }, { type: "todo/item/subscribe", entity_id: this._config.todo_entity })
      .catch((err) => { this._showError("The shopping list could not be loaded."); console.warn("grocery-app-card", err); return null; });
  }

  _showError(text) { const el = this.shadowRoot?.getElementById("err"); if (!el) return; el.textContent = text; el.hidden = !text; }

  async _add() {
    const input = this.shadowRoot.getElementById("addInput");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    try { await this._hass.callService("todo", "add_item", { item: text }, { entity_id: this._config.todo_entity }); this._showError(""); }
    catch (err) { input.value = text; this._showError("Could not add that item. Try again."); }
  }

  async _toggle(uid) {
    const item = (this._items || []).find((i) => i.uid === uid);
    if (!item) return;
    const status = item.status === "completed" ? "needs_action" : "completed";
    item.status = status; this._renderList();
    try { await this._hass.callService("todo", "update_item", { item: uid, status }, { entity_id: this._config.todo_entity }); this._showError(""); }
    catch (err) { item.status = status === "completed" ? "needs_action" : "completed"; this._renderList(); this._showError("Could not update that item."); }
  }

  _groups(items) {
    const attrs = this._hass?.states[this._config.todo_entity]?.attributes || {};
    const byItem = attrs.item_departments || {};
    const order = attrs.department_order || [];
    const groups = new Map(order.map((d) => [d, []]));
    for (const item of items) {
      const dept = byItem[item.uid] || (Object.keys(byItem).length ? "Other" : "To buy");
      if (!groups.has(dept)) groups.set(dept, []);
      groups.get(dept).push(item);
    }
    const out = [...groups].filter(([, list]) => list.length);
    out.sort((a, b) => (a[0] === "Other") - (b[0] === "Other"));
    return out;
  }

  _itemHtml(item) {
    const done = item.status === "completed";
    return `<button class="item ${done ? "done" : ""}" data-uid="${esc(item.uid)}" aria-pressed="${done}">
      <span class="box">${done ? "✓" : ""}</span><span class="name">${esc(item.summary)}</span><span class="qty">${esc(item.description || "")}</span></button>`;
  }

  _renderList() {
    const list = this.shadowRoot?.getElementById("list");
    if (!list) return;
    if (this._items === null) { list.innerHTML = `<div class="empty">Loading…</div>`; return; }
    const open = this._items.filter((i) => i.status !== "completed");
    const done = this._items.filter((i) => i.status === "completed");
    this.shadowRoot.getElementById("left").textContent = `${open.length} to get`;
    this.shadowRoot.getElementById("count").textContent = done.length ? `${done.length} in the cart` : "";
    let html = open.length ? "" : `<div class="empty">Nothing left to buy.</div>`;
    for (const [dept, items] of this._groups(open)) {
      html += `<div class="dept"><header><span class="mark" style="background:${DEPT_COLORS[dept] || "#1c6b45"}"></span>${esc(dept)} <small>${items.length}</small></header>${items.map((i) => this._itemHtml(i)).join("")}</div>`;
    }
    if (done.length) {
      html += `<button class="done-toggle" id="doneToggle">${this._showDone ? "Hide" : "Show"} ${done.length} checked off</button>`;
      if (this._showDone) html += `<div class="dept">${done.map((i) => this._itemHtml(i)).join("")}</div>`;
    }
    list.innerHTML = html;
  }

  _shiftWeek(days) { this._week = addDays(this._week, days); this._renderWeek(); this._loadWeek(); }

  async _loadWeek() {
    const start = iso(this._week), end = iso(addDays(this._week, 6)), key = start;
    if (!this._hass || this._dinners[key]?.loading) return;
    this._dinners[key] = { ...(this._dinners[key] || {}), loading: true };
    let days = null;
    try {
      const res = await this._hass.callWS({ type: "grocery_app/dinners", start, end });
      days = res.dinners;
    } catch (err) {
      try { days = await this._fromCalendar(start, end); } catch (err2) { days = null; }
    }
    this._dinners[key] = { loading: false, days: days ? Object.fromEntries(days.map((d) => [d.date, d.recipes])) : null };
    this._renderWeek();
    await this._signPhotos(days || []);
  }

  /* Fallback for integration 1.1.0: calendar events, recipe names from the description. */
  async _fromCalendar(start, end) {
    const events = await this._hass.callApi("GET", `calendars/${this._config.calendar_entity}?start=${encodeURIComponent(parseDay(start).toISOString())}&end=${encodeURIComponent(addDays(parseDay(end), 1).toISOString())}`);
    return events.map((ev) => {
      const names = (ev.description || "").split("\n").map((l) => l.replace(/^•\s*/, "").trim()).filter(Boolean);
      return { date: ev.start.date || String(ev.start.dateTime || ev.start).slice(0, 10), recipes: (names.length ? names : [ev.summary]).map((name) => ({ id: name, name, photo: null })) };
    });
  }

  async _signPhotos(days) {
    const paths = [...new Set(days.flatMap((d) => d.recipes.map((r) => r.photo)).filter((p) => p && !this._photos[p]))];
    if (!paths.length) return;
    await Promise.all(paths.map(async (path) => {
      try { const res = await this._hass.callWS({ type: "auth/sign_path", path, expires: 6 * 3600 }); this._photos[path] = res.path; } catch (err) { this._photos[path] = ""; }
    }));
    this._renderWeek();
  }

  _thumb(recipe, small) {
    const src = recipe.photo && this._photos[recipe.photo];
    return src ? `<img class="thumb ${small ? "small" : ""}" src="${esc(src)}" alt="">` : `<span class="thumb ${small ? "small" : ""}">${esc((recipe.name || "?").trim().charAt(0).toUpperCase())}</span>`;
  }

  _renderWeek() {
    const daysEl = this.shadowRoot?.getElementById("days");
    if (!daysEl) return;
    const today = iso(new Date());
    const end = addDays(this._week, 6);
    const lang = this._hass?.locale?.language || this._hass?.language || "en-US";
    const fmt = (d, o) => d.toLocaleDateString(lang, o);
    const thisWeek = iso(mondayOf(new Date())) === iso(this._week);
    this.shadowRoot.getElementById("weekLabel").innerHTML = `${esc(fmt(this._week, { month: "short", day: "numeric" }))} – ${esc(fmt(end, { month: "short", day: "numeric" }))}<small>${thisWeek ? "This week" : iso(this._week) < today ? "Earlier week" : "Coming up"}</small>`;
    const week = this._dinners[iso(this._week)];
    if (!week || (week.loading && !week.days)) { daysEl.innerHTML = `<div class="empty">Loading dinners…</div>`; return; }
    if (week.days === null) { daysEl.innerHTML = `<div class="err">Dinners could not be loaded.</div>`; return; }
    let html = "";
    for (let i = 0; i < 7; i++) {
      const d = addDays(this._week, i), key = iso(d);
      const recipes = week.days[key] || [];
      const open = this._expanded.has(key) && recipes.length;
      const cls = ["day", key === today ? "today" : "", key < today ? "past" : ""].join(" ");
      html += `<div class="${cls}" data-day="${key}" role="button" tabindex="0" aria-expanded="${!!open}">
        <header><b>${esc(fmt(d, { weekday: "long" }))}${key === today ? `<span class="badge">Tonight</span>` : ""}</b><span>${esc(fmt(d, { month: "short", day: "numeric" }))}</span></header>`;
      if (!recipes.length) html += `<div class="none">Nothing planned</div>`;
      else if (open) html += `<div class="recipes">${recipes.map((r) => `<div class="recipe">${this._thumb(r)}<span>${esc(r.name)}</span></div>`).join("")}</div>`;
      else html += `<div class="summary">${this._thumb(recipes[0], true)}<span class="txt">${esc(recipes[0].name)}</span>${recipes.length > 1 ? `<span class="more">+${recipes.length - 1} more</span>` : ""}</div>`;
      html += `</div>`;
    }
    daysEl.innerHTML = html;
  }
}

if (!customElements.get("grocery-app-card")) {
  customElements.define("grocery-app-card", GroceryAppCard);
  window.customCards = window.customCards || [];
  window.customCards.push({ type: "grocery-app-card", name: "Grocery App", description: "Shopping list by department and this week's dinners.", preview: false, documentationURL: "https://github.com/highraven85/grocery-list-homeassistant" });
  console.info(`%c GROCERY-APP-CARD %c ${CARD_VERSION} `, "background:#1c6b45;color:#fff;border-radius:4px 0 0 4px", "background:#f6f1e6;color:#241c14;border-radius:0 4px 4px 0");
}
