/**
 * NOXTIUM · main.js
 * Interacciones mínimas del sitio: abrir/cerrar el menú móvil y
 * cerrarlo automáticamente cuando el usuario toca un enlace.
 */

document.addEventListener("DOMContentLoaded", () => {
  const navbar = document.querySelector(".navbar");
  const toggle = document.getElementById("navToggle");

  if (!navbar || !toggle) return;

  toggle.addEventListener("click", () => {
    const isOpen = navbar.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
  });

  // Cierra el menú móvil al elegir una opción
  document.querySelectorAll(".navbar__links a, .navbar__actions a").forEach((link) => {
    link.addEventListener("click", () => {
      navbar.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    });
  });
});
