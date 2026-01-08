// =========================
// Submit AJAX (solo forms .js-send)
// =========================
document.addEventListener("submit", async function (e) {
  const form = e.target;
  if (!(form instanceof HTMLFormElement)) return;
  if (!form.classList.contains("js-send")) return;

  e.preventDefault();

  const button = form.querySelector("button[type='submit']");
  const originalText = button ? button.textContent : "";

  if (button) {
    button.disabled = true;
    button.textContent = "Guardando...";
  }

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
    });

    if (button) {
      button.textContent = response.ok ? "Guardado" : "Error";
      if (!response.ok) button.disabled = false;
    }
  } catch (err) {
    console.error(err);
    if (button) {
      button.textContent = "Error";
      button.disabled = false;
    }
  }

  setTimeout(() => {
    if (button) {
      button.textContent = originalText;
      button.disabled = false;
    }
  }, 2000);
});

// =========================
// Desplegable acciones en tarjetas (.card)
// =========================
document.addEventListener("click", function (e) {
  const toggle = e.target.closest(".actions-toggle");
  if (!toggle) return;

  const card = toggle.closest(".card");
  if (!card) return;

  const isOpen = card.classList.toggle("is-actions-open");
  toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
});

// =========================
// Toggle panel de filtros (cabecera)
// =========================
document.addEventListener("click", function (e) {
  const btn = e.target.closest(".js-filters-toggle");
  if (!btn) return;

  const page = btn.closest(".page");
  if (!page) return;

  const panel = page.querySelector("#filtersPanel");
  if (!panel) return;

  const isOpen = page.classList.toggle("is-filters-open");
  panel.style.display = isOpen ? "block" : "none";

  btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  btn.setAttribute("aria-label", isOpen ? "Ocultar filtros" : "Mostrar filtros");
});

// =========================
// Subfamilias por familia (checkboxes + tooltip)
// =========================
document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("subfamContainer");
  if (!container) return;

  function selectedFamilies() {
    return Array.from(document.querySelectorAll('input[name="family"]:checked'))
      .map(cb => cb.value.trim())
      .filter(Boolean);
  }

  function getCheckedByFamily() {
    const map = new Map();
    container.querySelectorAll("input[data-family][data-subfam]").forEach(cb => {
      const fam = cb.dataset.family;
      const sf = cb.dataset.subfam;
      if (!map.has(fam)) map.set(fam, new Set());
      if (cb.checked) map.get(fam).add(sf);
    });
    return map;
  }

  function getSelectedSubfamsFromURL() {
    const params = new URLSearchParams(window.location.search);
    const map = new Map();

    for (const [k, v] of params.entries()) {
      if (!k.startsWith("subfam_")) continue;
      const fam = k.replace("subfam_", "");
      if (!map.has(fam)) map.set(fam, new Set());
      map.get(fam).add(v);
    }
    return map;
  }

  async function fetchSubfamilies(fam) {
    const res = await fetch(`/api/zproveart/subfamilies?family=${encodeURIComponent(fam)}`);
    if (!res.ok) throw new Error("Error cargando subfamilias");
    const data = await res.json();
    return Array.isArray(data.subfamilies) ? data.subfamilies : [];
  }

  function renderFamilyBlock(fam, rows, prevSet) {
    const block = document.createElement("div");
    block.className = "subfam-block";

    block.innerHTML = `
      <div class="subfam-block__header">
        <div class="subfam-block__title">Familia ${fam}</div>
        <button type="button" class="btn btn-secondary subfam-block__toggle">Marcar todas</button>
      </div>
      <div class="subfam-block__list"></div>
      <div class="muted subfam-hint">
        Si no marcas ninguna subfamilia, se aplican todas las de esta familia.
      </div>
    `;

    const list = block.querySelector(".subfam-block__list");
    const btn = block.querySelector(".subfam-block__toggle");
    const checkboxes = [];

    rows.forEach(r => {
      const sf = String(r.COD_SUBFAM || "").trim();
      if (!sf) return;

      const desc = String(r.DES_SUBFAM || "").trim();

      const label = document.createElement("label");
      label.className = "subfam-item";

      if (desc) {
        label.dataset.tooltip = desc;   
        label.title = desc;             
      }

      label.innerHTML = `
        <input type="checkbox"
               name="subfam_${fam}"
               value="${sf}"
               data-family="${fam}"
               data-subfam="${sf}">
        <span class="subfam-item__text">${sf}</span>
      `;

      const cb = label.querySelector("input");
      if (prevSet && prevSet.has(sf)) cb.checked = true;

      checkboxes.push(cb);
      list.appendChild(label);
    });

    btn.addEventListener("click", () => {
      const anyUnchecked = checkboxes.some(c => !c.checked);
      checkboxes.forEach(c => (c.checked = anyUnchecked));
      btn.textContent = anyUnchecked ? "Desmarcar todas" : "Marcar todas";
    });

    btn.textContent = checkboxes.some(c => !c.checked)
      ? "Marcar todas"
      : "Desmarcar todas";

    return block;
  }

  async function refreshPanels() {
    const fams = selectedFamilies();
    const prevMap = getCheckedByFamily();
    const urlMap = getSelectedSubfamsFromURL();
    const useMap = prevMap.size ? prevMap : urlMap;

    container.innerHTML = "";

    if (!fams.length) {
      container.innerHTML = `<div class="muted">Selecciona una o varias familias para ver sus subfamilias.</div>`;
      return;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "subfam-wrapper";
    container.appendChild(wrapper);

    for (const fam of fams) {
      const rows = await fetchSubfamilies(fam);
      wrapper.appendChild(renderFamilyBlock(fam, rows, useMap.get(fam)));
    }
  }

  document.addEventListener("change", e => {
    if (e.target.matches('input[name="family"]')) refreshPanels();
  });

  refreshPanels();
});

// =========================
// Generar PDF (mismos filtros que el form)
// =========================
document.addEventListener("click", function (e) {
  const btn = e.target.closest("#btnPdf");
  if (!btn) return;

  const form = btn.closest("form");
  if (!form) return;

  // UI: loading
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Generando PDF...";

  const fd = new FormData(form);
  const params = new URLSearchParams();

  for (const [key, value] of fd.entries()) {
    const v = String(value ?? "").trim();
    if (!v) continue;
    params.append(key, v);
  }

  params.delete("page");
  params.delete("page_size");

  const url = "/zproveart/pdf" + (params.toString() ? "?" + params.toString() : "");

  // Navega al endpoint (descarga/abre PDF)
  window.open(url, "_blank", "noopener");

  // Si por algún motivo el navegador bloquea o tarda, re-habilita tras X segundos
  setTimeout(() => {
    btn.disabled = false;
    btn.textContent = originalText;
  }, 15000);
});

// =========================
// Popup lookup (proveedor/comprador)
// =========================
window.openLookupPopup = function(type, targetId) {
  const w = 780;
  const h = 520;
  const left = Math.max(0, Math.floor((window.screen.width - w) / 2));
  const top  = Math.max(0, Math.floor((window.screen.height - h) / 2));

  const url = `/zproveart/lookup/${encodeURIComponent(type)}?target=${encodeURIComponent(targetId)}`;

  const win = window.open(
    url,
    `lookup_${type}`,
    `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`
  );

  if (!win) {
    alert("El navegador ha bloqueado el popup. Permite popups para este sitio.");
  }
};

window.setLookupValue = function(targetId, value) {
  const input = document.getElementById(targetId);
  if (input) {
    input.value = value;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }
};

// =========================
// Lógica del popup lookup (solo se ejecuta en la ventana popup)
// Requiere que el HTML del popup defina window.LOOKUP_CFG
// =========================
(() => {
  if (!window.LOOKUP_CFG) return;

  const cfg = window.LOOKUP_CFG;

  const qEl = document.getElementById("q");
  const listEl = document.getElementById("list");
  const statusEl = document.getElementById("status");
  const btnSearch = document.getElementById("btnSearch");
  const btnClose = document.getElementById("btnClose");

  if (!qEl || !listEl || !statusEl) return;

  btnClose?.addEventListener("click", () => window.close());

  function esc(s){
    return String(s ?? "")
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;")
      .replaceAll('"',"&quot;")
      .replaceAll("'","&#039;");
  }

  function renderSupplier(it){
    return `
      <div class="item" data-value="${esc(it.BPSNUM_0)}">
        <div class="main">${esc(it.BPSNUM_0)} - ${esc(it.BPSNAM_0 || "")}</div>
        <div class="sub">Proveedor</div>
      </div>`;
  }

  function renderBuyer(it){
    return `
      <div class="item" data-value="${esc(it.COD_COM_0)}">
        <div class="main">${esc(it.COD_COM_0)}</div>
        <div class="sub">Comprador</div>
      </div>`;
  }

  // ===== typeahead helpers =====
  let debounceTimer = null;
  let aborter = null;

  function debounce(fn, ms) {
    return (...args) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => fn(...args), ms);
    };
  }

  async function load() {
    listEl.innerHTML = "";
    const q = (qEl.value || "").trim();

    // ✅ Supplier: evita buscar si está vacío / demasiado corto
    if (cfg.kind === "supplier") {
      const MIN_CHARS = 1; // pon 2 si quieres que empiece en "24" en vez de "2"
      if (q.length < MIN_CHARS) {
        statusEl.textContent = "Escribe para buscar…";
        return;
      }
    }

    statusEl.textContent = "Cargando…";

    try {
      // ✅ cancelar request anterior si estás tecleando
      if (aborter) aborter.abort();
      aborter = new AbortController();

      let url = "";
      if (cfg.kind === "supplier") {
        url = `/api/lookup/suppliers?q=${encodeURIComponent(q)}&limit=80`;
      } else {
        url = `/api/lookup/buyers`;
      }

      const res = await fetch(url, {
        headers: { "Accept":"application/json" },
        signal: aborter.signal
      });
      if (!res.ok) throw new Error("HTTP " + res.status);

      const data = await res.json();
      let items = data.items || [];

      // filtro local para buyer (opc)
      if (cfg.kind === "buyer" && q) {
        items = items.filter(x => String(x.COD_COM_0 || "").includes(q));
      }

      if (!items.length) {
        statusEl.textContent = "Sin resultados.";
        return;
      }

      statusEl.textContent = `${items.length} resultado(s).`;
      listEl.innerHTML = items.map(cfg.kind === "supplier" ? renderSupplier : renderBuyer).join("");

    } catch (e) {
      if (e && e.name === "AbortError") return; // cancelado por nueva tecla
      console.error(e);
      statusEl.textContent = "Error cargando datos.";
    }
  }

  const loadDebounced = debounce(load, 250);

  listEl.addEventListener("click", (e) => {
    const item = e.target.closest(".item");
    if (!item) return;

    const value = item.dataset.value;

    if (window.opener && typeof window.opener.setLookupValue === "function") {
      window.opener.setLookupValue(cfg.target, value);
    }
    window.close();
  });

  // Botón buscar sigue funcionando
  btnSearch?.addEventListener("click", load);

  // Enter busca
  qEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      load();
    }
  });

  // ✅ Autocomplete SOLO para supplier
  if (cfg.kind === "supplier") {
    qEl.addEventListener("input", () => loadDebounced());
  }

  // Autocarga compradores
  if (cfg.kind === "buyer") load();
})();
