"use strict";

// Данные: deadlines.json рядом с приложением. Его каждые 30 минут обновляет GitHub Actions.
// Отметки «Готово», опыт питомца и кэш списка хранятся в localStorage этого устройства.

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
const cached = ls.get("cache", null);
const state = {
  petName: ls.get("petName", "Пиксель"),
  xp: ls.get("xp", 0),
  done: ls.get("done", {}),             // id → когда отмечено
  all: cached ? cached.deadlines : [],  // всё из deadlines.json
  updatedAt: cached ? cached.updated_at : null,
  keepDays: cached ? cached.keep_days || 2 : 2,
  loadedOnce: !!cached,
};

const $ = (id) => document.getElementById(id);
const MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
  "августа", "сентября", "октября", "ноября", "декабря"];

// ---------- данные ----------

function visible() {
  const now = Date.now();
  return state.all
    .filter((d) => !state.done[d.id])
    .filter((d) => now <= new Date(d.due).getTime() + state.keepDays * 86400000)
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

    // Отметки для дедлайнов, которых больше нет в списке, не нужны
    const ids = new Set(state.all.map((d) => d.id));
    for (const id of Object.keys(state.done)) if (!ids.has(id)) delete state.done[id];
    ls.set("done", state.done);

    $("notice").hidden = true;
    if (manual) toast(JSON.stringify(state.all) === before ? "Новых изменений нет" : "Список обновлён");
  } catch (e) {
    if (state.loadedOnce) {
      if (manual) toast("Нет связи — показан сохранённый список");
    } else {
      showNotice("Список дедлайнов ещё не готов. Он появится после первого запуска проверки на GitHub.");
    }
  }
  render();
}

async function refresh() {
  const btn = $("refreshBtn");
  btn.disabled = true; btn.classList.add("loading");
  await load({ manual: true });
  btn.disabled = false; btn.classList.remove("loading");
}

function markDone(id, li) {
  const item = state.all.find((d) => d.id === id);
  li.classList.add("leaving");
  state.done[id] = new Date().toISOString(); ls.set("done", state.done);
  state.xp += 10; ls.set("xp", state.xp);
  celebrate(item);
  setTimeout(renderList, 300);
  toast(`«${item ? item.title : "Задание"}» — готово`, "Вернуть", () => {
    delete state.done[id]; ls.set("done", state.done);
    state.xp = Math.max(0, state.xp - 10); ls.set("xp", state.xp);
    render();
  });
}

// ---------- питомец ----------

const MOUTHS = {
  happy: "M86 122 Q100 138 114 122",
  sleep: "M94 126 Q100 130 106 126",
  worried: "M88 129 Q100 122 112 129",
  panic: "M90 132 Q100 112 110 132 Z",
  sick: "M84 130 Q92 122 100 130 Q108 138 116 130",
};

function daysLeft(d) {
  const due = new Date(d.due); const today = new Date();
  due.setHours(0, 0, 0, 0); today.setHours(0, 0, 0, 0);
  return Math.round((due - today) / 86400000);
}
const isOverdue = (d) => new Date(d.due) < new Date();

function levelOf(d) {
  if (isOverdue(d)) return "over";
  const n = daysLeft(d);
  return n <= 1 ? "hot" : n <= 3 ? "warn" : "ok";
}

function petMood() {
  const list = visible();
  const over = list.filter(isOverdue).length;
  const hot = list.filter((d) => levelOf(d) === "hot").length;
  const warn = list.filter((d) => levelOf(d) === "warn").length;
  const score = Math.max(5, Math.min(100, 100 - over * 35 - hot * 18 - warn * 8));
  let mood = "happy";
  if (!list.length) mood = "sleep";
  else if (over) mood = "sick";
  else if (hot) mood = "panic";
  else if (warn) mood = "worried";
  return { mood, score, over, hot };
}

function plural(n, one, few, many) {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few;
  return many;
}

function phrase({ mood, hot, over }) {
  const name = state.petName;
  const p = {
    sleep: ["Zzz… всё сдано, я сплю 😴", "Дедлайнов нет. Можно поспать."],
    happy: ["Всё под контролем! 😊", "Время есть, но не расслабляйся 😉", `${name} доволен тобой!`],
    worried: ["Через пару дней что-то сдавать… 😟", "Может, начнём сегодня?"],
    panic: [hot === 1 ? "Скоро дедлайн! Спасай! 😱" : `Горит ${hot} ${plural(hot, "дедлайн", "дедлайна", "дедлайнов")}! 😱`, "Срочно за работу!"],
    sick: [over === 1 ? "Один дедлайн просрочен… мне плохо 🤢" : `Просрочено: ${over}. Мне плохо 🤢`, "Сдай и нажми «Готово», пожалуйста…"],
  }[mood];
  return p[Math.floor(Date.now() / 60000) % p.length];
}

function renderPet() {
  const m = petMood();
  $("pet").dataset.mood = m.mood;
  $("mouth").setAttribute("d", MOUTHS[m.mood]);
  $("bubble").textContent = phrase(m);
  $("petName").textContent = state.petName;
  renderXp();
  const bar = $("moodBar");
  bar.style.width = `${m.score}%`;
  bar.style.background = m.score > 60 ? "var(--ok)" : m.score > 30 ? "var(--warn)" : "var(--hot)";
}

function renderXp() {
  $("level").textContent = Math.floor(state.xp / 50) + 1;
  $("xpBar").style.width = `${(state.xp % 50) * 2}%`;
}

function celebrate(item) {
  const pet = $("pet");
  pet.classList.remove("celebrate"); void pet.offsetWidth; pet.classList.add("celebrate");
  pet.dataset.mood = "happy";
  $("mouth").setAttribute("d", MOUTHS.happy);
  $("bubble").textContent = item ? `Ура, «${item.title}» сдано! +10 XP 🎉` : "Ура! +10 XP 🎉";
  renderXp();
  clearTimeout(celebrate.timer);
  celebrate.timer = setTimeout(() => { pet.classList.remove("celebrate"); renderPet(); }, 2200);
}

// ---------- список ----------

function dueText(d) {
  const dt = new Date(d.due);
  const n = daysLeft(d);
  const time = `, ${dt.toTimeString().slice(0, 5)}`;
  if (isOverdue(d)) return n === 0 ? `Сегодня${time} — время вышло` : `Просрочено ${-n} дн. назад`;
  if (n === 0) return `Сегодня${time}`;
  if (n === 1) return `Завтра${time}`;
  return `${dt.getDate()} ${MONTHS[dt.getMonth()]}${time} · через ${n} дн.`;
}

function renderList() {
  const ul = $("list");
  ul.replaceChildren();
  const items = visible();
  for (const d of items) {
    const li = document.createElement("li");
    li.className = "deadline";
    li.dataset.level = levelOf(d);

    const stripe = document.createElement("span"); stripe.className = "stripe";
    const info = document.createElement("div");
    const safeUrl = d.url && /^https:\/\//.test(d.url);
    const title = document.createElement(safeUrl ? "a" : "div");
    title.className = "title"; title.textContent = d.title;
    if (safeUrl) { title.href = d.url; title.target = "_blank"; title.rel = "noopener"; }
    const course = document.createElement("div"); course.className = "course"; course.textContent = d.course;
    const due = document.createElement("div"); due.className = "due"; due.textContent = dueText(d);
    info.append(title, course, due);

    const btn = document.createElement("button");
    btn.type = "button"; btn.className = "btn done-btn"; btn.textContent = "✓ Готово";
    btn.setAttribute("aria-label", `Отметить «${d.title}» как сделанное`);
    btn.addEventListener("click", () => markDone(d.id, li));

    li.append(stripe, info, btn);
    ul.append(li);
  }
  $("empty").hidden = items.length > 0 || !state.loadedOnce;

  if (state.updatedAt) {
    const t = new Date(state.updatedAt);
    $("meta").textContent = `изменён ${t.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} в ${t.toTimeString().slice(0, 5)}`;
  } else {
    $("meta").textContent = "";
  }
}

function render() { renderList(); renderPet(); }

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
  if (!CONFIG.vapidPublicKey) {
    return { ok: false, text: "Уведомления ещё не настроены: на GitHub не задан секрет VAPID_PUBLIC_KEY." };
  }
  if (Notification.permission === "denied") {
    return { ok: false, text: "Уведомления запрещены в настройках браузера для этого сайта." };
  }
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
    status.textContent = "Уведомления включены на этом устройстве. Убедись, что подписка добавлена в секрет на GitHub:";
    $("subText").value = JSON.stringify(sub.toJSON());
    box.hidden = false;
  } else {
    status.textContent = "Придут уведомления о новых дедлайнах и за 24 часа до срока.";
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
  try { await navigator.clipboard.writeText(text); toast("Скопировано"); }
  catch { $("subText").select(); document.execCommand("copy"); toast("Скопировано"); }
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
  state.petName = $("petNameInput").value.trim() || "Пиксель";
  ls.set("petName", state.petName);
  renderPet();
});

$("refreshBtn").addEventListener("click", refresh);
$("settingsBtn").addEventListener("click", openSettings);
$("pushBtn").addEventListener("click", enablePush);
$("copySub").addEventListener("click", copySub);
window.addEventListener("online", () => load());
document.addEventListener("visibilitychange", () => { if (!document.hidden) load(); });
setInterval(() => load(), 10 * 60 * 1000);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

render();
load();
