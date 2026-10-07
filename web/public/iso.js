/*
 * The isometric figures' small amount of behaviour. Never needed: every
 * figure is complete without it.
 *
 * 1. A figure's motion plays on arrival. One that starts below the fold is
 *    replayed when it first scrolls into view, so it is not missed.
 * 2. Tapping a figure replays its motion.
 * 3. A list item marked data-iso-key="photo" lights the figure part marked
 *    data-key="photo" while it is hovered or focused, and dims the others.
 *
 * Nothing moves for reduced motion.
 */
(function () {
  var still = false;
  try { still = matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

  function replay(svg) {
    svg.classList.remove("is-play");
    void svg.getBoundingClientRect();
    svg.classList.add("is-play");
  }

  function wire(svg) {
    if (svg.__iso) return;
    svg.__iso = 1;
    if (!still) {
      var box = svg.getBoundingClientRect();
      if (box.top > innerHeight && "IntersectionObserver" in window) {
        svg.classList.remove("is-play");
        var io = new IntersectionObserver(function (entries) {
          if (entries[0].isIntersecting) { svg.classList.add("is-play"); io.disconnect(); }
        }, { threshold: 0.35 });
        io.observe(svg);
      }
      svg.addEventListener("click", function () { replay(svg); });
      svg.style.cursor = "pointer";
    }
    var scope = svg.closest("[data-iso-scope]");
    if (!scope) return;
    var items = scope.querySelectorAll("[data-iso-key]");
    Array.prototype.forEach.call(items, function (item) {
      var key = item.getAttribute("data-iso-key");
      function show() {
        svg.classList.add("is-focus");
        Array.prototype.forEach.call(svg.querySelectorAll("[data-key]"), function (p) {
          p.classList.toggle("is-key", p.getAttribute("data-key") === key);
        });
      }
      function hide() { svg.classList.remove("is-focus"); }
      item.addEventListener("pointerenter", show);
      item.addEventListener("pointerleave", hide);
      item.addEventListener("focusin", show);
      item.addEventListener("focusout", hide);
    });
  }

  function run() {
    Array.prototype.forEach.call(document.querySelectorAll("svg.iso"), wire);
  }
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", run);
  else run();
  // Client-side navigation brings new figures without a page load.
  var later;
  if ("MutationObserver" in window) new MutationObserver(function () { clearTimeout(later); later = setTimeout(run, 120); }).observe(document.documentElement, { childList: true, subtree: true });
})();
