// Compact Memory showcase: entity autocomplete, journal table filter and sort. Plain JavaScript, no libraries.
(() => {
  "use strict";
  const BASE = (document.querySelector('link[href*="/static/cm.css"]') || { getAttribute: () => "" })
    .getAttribute("href").replace(/\/static\/cm\.css.*$/, "");
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const KIND = { person: "Person", place: "Place", subject: "Subject" };

  // ---------- entity autocomplete: data-ac (container), data-ac-input, data-ac-list; data-ac-go="entity|filter"
  document.querySelectorAll("[data-ac]").forEach(box => {
    const input = box.querySelector("[data-ac-input]"), list = box.querySelector("[data-ac-list]");
    const go = input.dataset.acGo || "entity";
    let items = [], sel = -1, timer = null, last = "";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    list.setAttribute("role", "listbox");
    list.id = list.id || "ac-" + Math.random().toString(36).slice(2);
    input.setAttribute("aria-controls", list.id);
    const close = () => { list.hidden = true; input.setAttribute("aria-expanded", "false"); sel = -1; };
    const choose = it => {
      if (go === "filter") {
        const form = input.closest("form");
        const h = document.createElement("input");
        h.type = "hidden"; h.name = it.cls === "place" && form.dataset.placeAsPl ? "pl" : "e"; h.value = it.ep;
        form.appendChild(h);
        input.value = "";
        form.submit();
      } else {
        location.href = BASE + "/entity/" + it.ep;
      }
    };
    const render = () => {
      list.innerHTML = items.map((it, i) => `<li role="option" id="${list.id}-${i}" aria-selected="${i === sel}" data-i="${i}">
        <span class="lab">${esc(it.label)}</span>
        <span class="sub">${esc([KIND[it.cls] || it.cls, it.dates, (it.occ || []).join(", "), it.match ? "“" + it.match + "”" : ""].filter(Boolean).join(" · "))}</span>
        <span class="cnt">${it.pages.toLocaleString("en-US")} p.</span></li>`).join("");
      list.hidden = !items.length;
      input.setAttribute("aria-expanded", String(!!items.length));
      if (sel >= 0) input.setAttribute("aria-activedescendant", `${list.id}-${sel}`);
      else input.removeAttribute("aria-activedescendant");
    };
    const fetchItems = async q => {
      if (q === last) return;
      last = q;
      if (q.trim().length < 2) { items = []; render(); return; }
      try {
        const r = await fetch(BASE + "/api/entities?q=" + encodeURIComponent(q));
        if (q !== last) return;
        items = await r.json(); sel = items.length ? 0 : -1; render();
      } catch (e) { items = []; render(); }
    };
    input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => fetchItems(input.value), 120); });
    input.addEventListener("keydown", e => {
      if (e.key === "ArrowDown" && items.length) { sel = (sel + 1) % items.length; render(); e.preventDefault(); }
      else if (e.key === "ArrowUp" && items.length) { sel = (sel - 1 + items.length) % items.length; render(); e.preventDefault(); }
      else if (e.key === "Enter") {
        if (items.length && !list.hidden) { e.preventDefault(); choose(items[Math.max(0, sel)]); }
        else if (go === "filter") e.preventDefault();
      }
      else if (e.key === "Escape") close();
    });
    list.addEventListener("mousedown", e => { const li = e.target.closest("li"); if (li) { e.preventDefault(); choose(items[+li.dataset.i]); } });
    input.addEventListener("blur", () => setTimeout(close, 150));
    input.addEventListener("focus", () => { if (items.length) render(); });
  });

  // ---------- the filters of the search are open on wide screens, closed on phones
  if (matchMedia("(min-width: 861px)").matches) document.querySelectorAll("[data-open-wide]").forEach(d => { d.open = true; });

  // ---------- table filter: <input data-filter="#table">, rows carry data-s (search text)
  document.querySelectorAll("[data-filter]").forEach(inp => {
    const rows = [...document.querySelectorAll(inp.dataset.filter + " tbody tr")];
    inp.addEventListener("input", () => {
      const q = inp.value.trim().toLowerCase();
      rows.forEach(r => { r.hidden = q && !(r.dataset.s || r.textContent.toLowerCase()).includes(q); });
    });
  });

  // ---------- sortable tables: click a header
  document.querySelectorAll("table.cm-sortable").forEach(t => {
    const ths = [...t.tHead.rows[0].cells];
    ths.forEach((th, i) => {
      th.tabIndex = 0;
      const sort = () => {
        const dir = th.getAttribute("aria-sort") === "descending" ? 1 : th.getAttribute("aria-sort") === "ascending" ? -1
          : (th.classList.contains("num") ? -1 : 1);
        ths.forEach(x => x.removeAttribute("aria-sort"));
        th.setAttribute("aria-sort", dir > 0 ? "ascending" : "descending");
        const val = r => {
          const s = r.cells[i].textContent.trim();
          if (th.classList.contains("num")) { const n = parseFloat(s.replace(/[,%]/g, "")); return isNaN(n) ? -1 : n; }
          return s.toLowerCase();
        };
        const rows = [...t.tBodies[0].rows];
        rows.sort((a, b) => { const x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * dir; });
        rows.forEach(r => t.tBodies[0].appendChild(r));
      };
      th.addEventListener("click", sort);
      th.addEventListener("keydown", e => { if (e.key === "Enter") sort(); });
    });
  });
})();
