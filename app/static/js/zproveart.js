document.addEventListener("submit", async function (e) {
  const form = e.target;

  // Solo nuestros forms de envío
  if (!form.classList.contains("js-send")) return;

  e.preventDefault(); //  evita navegación

  const button = form.querySelector("button[type='submit']");
  const originalText = button.textContent;

  button.disabled = true;
  button.textContent = "Guardando...";

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
    });

    if (response.ok) {
      button.textContent = "Guardado";
    } else {
      button.textContent = "Error";
      button.disabled = false;
    }
  } catch (err) {
    console.error(err);
    button.textContent = "Error";
    button.disabled = false;
  }

  // Opcional: volver al estado original tras 2s
  setTimeout(() => {
    button.textContent = originalText;
    button.disabled = false;
  }, 2000);
});
