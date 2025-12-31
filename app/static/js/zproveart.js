document.addEventListener("submit", async function (e) {
  const form = e.target;
  if (!(form instanceof HTMLFormElement)) return;

  // Solo nuestros forms de envío
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
      if (response.ok) {
        button.textContent = "Guardado";
      } else {
        button.textContent = "Error";
        button.disabled = false;
      }
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

// Desplegable tarjetas (clase en .card)
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

  const isOpen = page.classList.toggle("is-filters-open");

  // Accesibilidad (esto SÍ se queda)
  btn.setAttribute("aria-expanded", isOpen ? "true" : "false");
  btn.setAttribute("aria-label", isOpen ? "Ocultar filtros" : "Mostrar filtros");
});