"use strict";

// Erudax — пиксельный спрайт на <canvas> (DESIGN.md, раздел 3).
//
// Эволюции: каждая форма питомца — одна запись в FORMS. Чтобы добавить новую форму,
// допиши объект с minLevel, сеткой (grid), картой слотов (slots) и настроениями (moods).
// formForLevel(level) сам выберет самую «старшую» форму, доступную на этом уровне.
//
// Легенда сетки: "." прозрачный, K мех, W контур/белое, G тень, A акцент.
// Строчные буквы — слоты, которые зависят от настроения.

const ErudaxPet = (() => {
  const PALETTE = { K: "#141414", W: "#F4F4F0", G: "#5C5C5C" };

  const FORMS = [
    {
      id: "pup",
      name: "Волчонок",
      minLevel: 1,
      grid: [
        "...WW..........WW...",
        "...WKW........WKW...",
        "..WKKKW......WKKKW..",
        "..WKGKKWWWWWWKKGKW..",
        ".WKKKKKKKKKKKKKKKKW.",
        ".WKKKKKKKKKKKKKKKKW.",
        ".WKKeeKKKKKKKKeeKKW.",
        ".WKKffKKKKKKKKffKKW.",
        "WKKKKKKKWWWWKKKKKKKW",
        "WKGKKKKWWKKWWKKKKGKW",
        "WKGKKKKWmmmmWKKKKGKW",
        ".WKKKKKKWnnWKKKKKKW.",
        "..WKKKKKKWWKKKKKKW..",
        ".WKKKKKKWWWWKKKKKKW.",
        ".WKKGKKWWWWWWKKGKKW.",
        ".WKKKKKKWWWWKKKKKKW.",
        ".WKKWWKKKKKKKKWWKKW.",
        "..WWWW..WWWW..WWWW..",
      ],
      // Слот → группы столбцов. Значение настроения slot[i] ставится во все столбцы группы i.
      slots: {
        e: [[4, 14], [5, 15]],
        f: [[4, 14], [5, 15]],
        m: [[8], [9], [10], [11]],
        n: [[9], [10]],
      },
      // x — точечные замены [строка, столбец, цвет], счёт с 0
      moods: {
        happy:   { e: ["W", "W"], f: ["K", "K"], m: ["K", "W", "W", "K"], n: ["K", "K"], x: [] },
        worried: { e: ["W", "W"], f: ["W", "K"], m: ["W", "K", "K", "W"], n: ["W", "W"], x: [[3, 19, "G"], [4, 19, "W"]] },
        panic:   { e: ["A", "A"], f: ["A", "A"], m: ["K", "K", "K", "K"], n: ["A", "A"], x: [[5, 5, "W"], [5, 14, "W"]] },
        sad:     { e: ["K", "K"], f: ["W", "W"], m: ["W", "K", "K", "W"], n: ["W", "W"], x: [[11, 8, "K"], [11, 11, "K"], [8, 5, "G"], [9, 5, "G"]] },
        done:    { e: ["W", "W"], f: ["W", "W"], m: ["K", "K", "K", "K"], n: ["A", "A"], x: [[0, 1, "W"], [1, 0, "W"], [1, 2, "W"], [2, 1, "W"]] },
      },
    },
    // Пример будущей эволюции:
    // { id: "wolf", name: "Волк", minLevel: 10, grid: [...], slots: {...}, moods: {...} },
  ];

  const MOOD_LABELS = {
    happy: "спокоен", worried: "насторожился", panic: "паникует", sad: "грустит", done: "ликует",
  };

  function formForLevel(level) {
    return FORMS.filter((f) => f.minLevel <= level).sort((a, b) => b.minLevel - a.minLevel)[0] || FORMS[0];
  }

  function cells(form, mood) {
    const cfg = form.moods[mood] || form.moods.happy;
    const grid = form.grid.map((row) => row.split("").map((ch, c) => {
      const groups = form.slots[ch];
      if (!groups) return ch;
      const i = groups.findIndex((cols) => cols.includes(c));
      return (cfg[ch] && cfg[ch][i]) || "K";
    }));
    for (const [r, c, v] of cfg.x || []) grid[r][c] = v;
    return grid;
  }

  /** Рисует питомца в canvas. px — размер «пикселя» в CSS-пикселях. */
  function draw(canvas, { level = 1, mood = "happy", px = 10, accent = "#FF4A1C", name = "Erudax" } = {}) {
    const form = formForLevel(level);
    const grid = cells(form, mood);
    const rows = grid.length, cols = grid[0].length;
    const dpr = Math.max(1, Math.round(window.devicePixelRatio || 1));
    canvas.width = cols * px * dpr;
    canvas.height = rows * px * dpr;
    canvas.style.width = `${cols * px}px`;
    canvas.style.height = `${rows * px}px`;
    const ctx = canvas.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const s = px * dpr; // целые координаты — без размытия
    grid.forEach((row, r) => row.forEach((ch, c) => {
      const color = ch === "A" ? accent : PALETTE[ch];
      if (!color) return;
      ctx.fillStyle = color;
      ctx.fillRect(c * s, r * s, s, s);
    }));
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", `${name} ${MOOD_LABELS[mood] || MOOD_LABELS.happy}`);
    canvas.dataset.form = form.id;
    return form;
  }

  return { FORMS, formForLevel, draw, MOOD_LABELS };
})();
