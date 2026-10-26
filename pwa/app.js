"use strict";

// Erudax — главный экран (DESIGN.md, разделы 4–6).
// Данные: deadlines.json рядом с приложением, его каждые 30 минут обновляет GitHub Actions.
// Отметки «Готово», опыт, имя питомца и кэш хранятся в localStorage этого устройства.

const ls = {
  get(key, fallback) {
    try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* приватный режим */ }
  },
};

const CONFIG = window.APP_CONFIG || {};
const ACCENT = "#FF4A1C";
const XP_PER_DONE = 10;
const XP_PER_LEVEL = 50;
const CELEBRATE_MS = 2400;
const H = 3600000;

const cached = ls.get("cache", null);
let storedName = ls.get("petName", "Erudax");
if (storedName === "Пиксель") storedName = "Erudax"; // старое имя по умолчанию

const state = {
  petName: storedName,
  xp: ls.get("xp", 0),
  done: ls.get("done", {}),
  all: cached ? cached.deadlines : [],
  updatedAt: cached ? cached.updated_at : null,
  keepDays: cached ? cached.keep_days || 2 : 2,
  loadedOnce: !!cached,
  lastRun: ls.get("lastRun", null), // { at, failed }
  celebrateUntil: 0,
};

const $ = (id) => document.getElementById(id);

// ---------- время ----------

const hoursLeft = (d) => (new Date(d.due).getTime() - Date.now()) / H;

/** «18 ч», «2 д 2 ч», «6 д», «просрочено» */
function fmtLeft(h) {
  if (h < 0) return "просрочено";
  if (h < 1) return "< 1 ч";
  if (h < 24) return `${Math.floor(h)} ч`;
  const d = Math.floor(h / 24), r = Math.floor(h % 24);
  return r ? `${d} д ${r} ч` : `${d} д`;
}

const hhmm = (date) => date.toTimeString().slice(0, 5);

// ---------- данные ----------

function visible() {
  const now = Date.now();
  return state.all
    .filter((d) => !state.done[d.id])
    .filter((d) => now <= new Date(d.due).getTime() + state.keepDays * 24 * H)
    .sort((a, b) => new Date(a.due) - new Date(b.due));
}

async function load({ manual = false } = {}) {
  try {
    const res = await fetch(`deadlines.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const before = JSON.stringify(state.all);
    state.all = data.deadlines || [];
    state.updatedAt = data.updated_at || null;
    state.keepDays = data.keep_days || 2;
    state.loadedOnce = true;
    ls.set("cache", { deadlines: state.all, updated_at: state.updatedAt, keep_days: state.keepDays });

    const ids = new Set(state.all.map((d) => d.id));
    for (const id of Object.keys(state.done)) if (!ids.has(id)) delete state.done[id];
    ls.set("done", state.done);

    $("notice").hidden = true;
    if (manual) toast(JSON.stringify(state.all) === before ? "Новых изменений нет" : "Список обновлён");
  } catch {
    if (state.loadedOnce) {
      if (manual) toast("Нет связи — показан сохранённый список");
    } else {
      showNotice("Список дедлайнов ещё не готов. Он появится после первой проверки на GitHub.");
    }
  }
  render();
}

/** Репозиторий: из config.js или из адреса GitHub Pages (owner.github.io/repo). */
function repoSlug() {
  if (CONFIG.repo) return CONFIG.repo;
  const m = location.hostname.match(/^([^.]+)\.github\.io$/i);
  const repo = location.pathname.split("/").filter(Boolean)[0];
  return m && repo ? `${m[1]}/${repo}` : null;
}

/** Время последнего прогона GitHub Actions — публичный API, без токена. */
async function loadLastRun() {
  const slug = repoSlug();
  if (!slug) return;
  try {
    const res = await fetch(`https://api.github.com/repos/${slug}/actions/workflows/update.yml/runs?status=completed&per_page=1`,
      { headers: { Accept: "application/vnd.github+json" } });
    if (!res.ok) return;
    const run = (await res.json()).workflow_runs?.[0];
    if (!run) return;
    state.lastRun = { at: run.updated_at, failed: run.conclusion === "failure" };
    ls.set("lastRun", state.lastRun);
    renderSync();
  } catch { /* офлайн — покажем время изменения списка */ }
}

async function refresh() {
  const btn = $("syncBtn");
  if (btn.classList.contains("loading")) return;
  btn.classList.add("loading");
  await Promise.all([load({ manual: true }), loadLastRun()]);
  btn.classList.remove("loading");
}

function markDone(id, li) {
  const item = state.all.find((d) => d.id === id);
  li.classList.add("leaving");
  const levelBefore = level();
  state.done[id] = new Date().toISOString(); ls.set("done", state.done);
  state.xp += XP_PER_DONE; ls.set("xp", state.xp);
  state.celebrateUntil = Date.now() + CELEBRATE_MS;
  setTimeout(render, 250);
  clearTimeout(markDone.timer);
  markDone.timer = setTimeout(render, CELEBRATE_MS + 50);
  const up = level() > levelBefore ? ` · уровень ${level()}!` : "";
  toast(`«${item ? item.title : "Задание"}» — готово${up}`, "Вернуть", () => {
    delete state.done[id]; ls.set("done", state.done);
    state.xp = Math.max(0, state.xp - XP_PER_DONE); ls.set("xp", state.xp);
    state.celebrateUntil = 0;
    render();
  });
}

// ---------- питомец ----------

const level = () => Math.floor(state.xp / XP_PER_LEVEL) + 1;

const MOODS = {
  happy:   { label: "СПОКОЕН",   rule: "> 3 дней",   scene: "tone",  anim: "a-bob" },
  worried: { label: "НАСТОРОЖЕ", rule: "1–3 дня",    scene: "tone",  anim: "a-tremble" },
  panic:   { label: "ПАНИКА",    rule: "< 24 ч",     scene: "speed", anim: "a-shake", hot: true },
  sad:     { label: "ГРУСТИТ",   rule: "просрочено", scene: "tone",  anim: "a-droop" },
  done:    { label: "ЛИКУЕТ",    rule: "сдано!",     scene: "tone",  anim: "a-jump", hot: true },
};

/** Самый ранний несданный дедлайн определяет настроение. */
function currentMood(items) {
  if (Date.now() < state.celebrateUntil) return { mood: "done", first: items[0] };
  const first = items[0];
  if (!first) return { mood: "happy", first: null };
  const h = hoursLeft(first);
  if (h < 0) return { mood: "sad", first };
  if (h < 24) return { mood: "panic", first };
  if (h <= 72) return { mood: "worried", first };
  return { mood: "happy", first };
}

function bubbleText(mood, first) {
  const t = first ? first.title : "";
  const left = first ? fmtLeft(hoursLeft(first)) : "";
  switch (mood) {
    case "worried": return `«${t}» через ${left}. Начнём сегодня или опять ночью?`;
    case "panic":   return `ОСТАЛОСЬ ${left.toUpperCase()}! «${t}». Я грызу провода!!`;
    case "sad":     return `«${t}» просрочено… Сдай хоть поздно, я подожду.`;
    case "done":    return "ГОТОВО?! Виляю хвостом на максималку!";
    default:        return "Горизонт чистый. Отдыхай — я посторожу.";
  }
}

function renderPet(items) {
  const { mood, first } = currentMood(items);
  const m = MOODS[mood];
  $("scene").className = `scene ${m.scene}`;
  const pill = $("moodPill");
  pill.textContent = m.label;
  pill.classList.toggle("hot", !!m.hot);
  $("moodRule").textContent = m.rule;
  $("bubble").textContent = bubbleText(mood, first);
  $("petWrap").className = `pet-wrap ${m.anim}`;
  const px = window.innerWidth < 360 ? 8 : 10;
  ErudaxPet.draw($("pet"), { level: level(), mood, px, accent: ACCENT, name: state.petName });

  $("petName").textContent = state.petName;
  $("level").textContent = level();
  $("xpBar").style.width = `${((state.xp % XP_PER_LEVEL) / XP_PER_LEVEL) * 100}%`;
}

// ---------- список ----------

function renderList(items) {
  const ul = $("list");
  ul.replaceChildren();
  for (const d of items) {
    const h = hoursLeft(d);
    const li = document.createElement("li");
    li.className = "card";

    const info = document.createElement("div");
    info.className = "card-info";
    const safeUrl = d.url && /^https:\/\//.test(d.url);
    const title = document.createElement(safeUrl ? "a" : "span");
    title.className = "card-title"; title.textContent = d.title;
    if (safeUrl) { title.href = d.url; title.target = "_blank"; title.rel = "noopener"; }
    const sub = document.createElement("span");
    sub.className = "card-sub"; sub.textContent = d.course;
    info.append(title, sub);

    const timer = document.createElement("span");
    timer.className = `timer${h < 24 ? " hot" : ""}`;
    timer.textContent = fmtLeft(h);
    timer.title = new Date(d.due).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "btn"; btn.textContent = "Готово";
    btn.setAttribute("aria-label", `Готово: ${d.title}`);
    btn.addEventListener("click", () => markDone(d.id, li));

    li.append(info, timer, btn);
    ul.append(li);
  }
  $("count").textContent = items.length ? `осталось: ${items.length}` : "";
  const empty = $("empty");
  empty.textContent = `Всё сдано. ${state.petName} спит спокойно.`;
  empty.hidden = items.length > 0 || !state.loadedOnce;
}

function renderSync() {
  const btn = $("syncBtn");
  const at = state.lastRun?.at || state.updatedAt;
  $("syncText").textContent = `Академо · ${at ? hhmm(new Date(at)) : "—"}`;
  btn.classList.toggle("failed", !!state.lastRun?.failed);
  btn.title = state.lastRun?.failed
    ? "Последняя проверка Академо не удалась. Нажми, чтобы обновить."
    : "Время последней проверки Академо. Нажми, чтобы обновить.";
}

function render() {
  const items = visible();
  renderList(items);
  renderPet(items);
  renderSync();
}

// ---------- уведомления (Web Push) ----------

function b64ToUint8(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

async function pushSupport() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    const ios = /iPhone|iPad/.test(navigator.userAgent);
    return { ok: false, text: ios
      ? "На iPhone уведомления работают, только если добавить приложение на экран «Домой» (Поделиться → На экран «Домой») и открыть его оттуда."
      : "Этот браузер не поддерживает уведомления." };
  }
  if (!CONFIG.vapidPublicKey) return { ok: false, text: "Уведомления ещё не настроены: на GitHub не задан секрет VAPID_PUBLIC_KEY." };
  if (Notification.permission === "denied") return { ok: false, text: "Уведомления запрещены в настройках браузера для этого сайта." };
  return { ok: true };
}

async function renderPushBox() {
  const s = await pushSupport();
  const status = $("pushStatus"), btn = $("pushBtn"), box = $("subBox");
  btn.hidden = true; box.hidden = true;
  if (!s.ok) { status.textContent = s.text; return; }
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (sub) {
    status.textContent = "Уведомления включены на этом устройстве. Проверь, что подписка добавлена в секрет на GitHub:";
    $("subText").value = JSON.stringify(sub.toJSON());
    box.hidden = false;
  } else {
    status.textContent = `${state.petName} напишет о новых дедлайнах, за 24 часа до срока и если что-то просрочено.`;
    btn.hidden = false;
  }
}

async function enablePush() {
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { toast("Без разрешения уведомления не придут"); return renderPushBox(); }
    const reg = await navigator.serviceWorker.ready;
    await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(CONFIG.vapidPublicKey) });
    toast("Готово! Теперь скопируй подписку в GitHub");
  } catch (e) {
    toast(`Не получилось включить: ${e.message}`);
  }
  renderPushBox();
}

async function copySub() {
  const text = $("subText").value;
  try { await navigator.clipboard.writeText(text); }
  catch { $("subText").select(); document.execCommand("copy"); }
  toast("Скопировано");
}

// ---------- UI-мелочи ----------

function showNotice(text) { const n = $("notice"); n.textContent = text; n.hidden = false; }

let toastTimer;
function toast(text, actionLabel, action) {
  const t = $("toast"), btn = $("toastAction");
  $("toastText").textContent = text;
  btn.hidden = !actionLabel;
  btn.textContent = actionLabel || "";
  btn.onclick = action ? () => { action(); t.classList.remove("show"); } : null;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), actionLabel ? 5000 : 2800);
}

function openSettings() {
  $("petNameInput").value = state.petName;
  $("settings").showModal();
  renderPushBox();
}

$("settings").addEventListener("close", () => {
  if ($("settings").returnValue !== "save") return;
  state.petName = $("petNameInput").value.trim() || "Erudax";
  ls.set("petName", state.petName);
  render();
});

$("syncBtn").addEventListener("click", refresh);
$("settingsBtn").addEventListener("click", openSettings);
$("pushBtn").addEventListener("click", enablePush);
$("copySub").addEventListener("click", copySub);
window.addEventListener("online", () => { load(); loadLastRun(); });
window.addEventListener("resize", () => renderPet(visible()));
document.addEventListener("visibilitychange", () => { if (!document.hidden) { load(); loadLastRun(); } });
setInterval(() => { load(); loadLastRun(); }, 10 * 60 * 1000);
setInterval(render, 60 * 1000); // таймеры «18 ч» идут сами

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});

render();
load();
loadLastRun();
