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
