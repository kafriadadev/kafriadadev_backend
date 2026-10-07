/*
 * Layer 2, "delight": the hairline figures. Never needed, never in the way.
 *
 * Runs only on a capable device: a fine pointer that can hover (mostly a
 * laptop), no reduced motion, no Save-Data, and not a 2G or 3G connection.
 * Anywhere else it does nothing and the plain illustrations stay.
 *
 * When the browser is idle it swaps an illustration marked data-figure for its
 * fine-line version from /figures/, and fills a data-figure-slot (the landing
 * page's runner, which leans gently towards the pointer). A figure that fails
 * to load leaves the page exactly as it was.
 */
(function () {
  var KNOWN = { net: 1, bench: 1, rail: 1 };

  function capable() {
    try {
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) return false;
      if (!matchMedia("(hover: hover) and (pointer: fine)").matches) return false;
      var c = navigator.connection;
      if (c && (c.saveData || /2g|3g/.test(c.effectiveType || ""))) return false;
      return typeof fetch === "function" && typeof DOMParser === "function";
    } catch (e) {
      return false;
    }
  }
  if (!capable()) return;

  function load(name) {
    return fetch("/figures/" + name + ".svg").then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.text();
    }).then(function (text) {
      var doc = new DOMParser().parseFromString(text, "image/svg+xml");
      var svg = doc.documentElement;
      if (svg.nodeName !== "svg") throw new Error("not an svg");
      return document.importNode(svg, true);
    });
  }

  function lean(slot, svg) {
    var area = slot.closest("section") || slot.parentNode;
    svg.style.transition = "transform 200ms cubic-bezier(.2,.8,.2,1)";
    area.addEventListener("pointermove", function (e) {
      var r = area.getBoundingClientRect();
      var x = (e.clientX - r.left) / r.width - 0.5;
      var y = (e.clientY - r.top) / r.height - 0.5;
      svg.style.transform = "translate(" + (x * 10).toFixed(1) + "px," + (y * 8).toFixed(1) + "px) rotate(" + (x * 3).toFixed(2) + "deg)";
    });
    area.addEventListener("pointerleave", function () {
      svg.style.transform = "";
    });
  }

  function run() {
    var marked = document.querySelectorAll("svg[data-figure]");
    Array.prototype.forEach.call(marked, function (el) {
      var name = el.getAttribute("data-figure");
      if (!KNOWN[name]) return;
      load(name).then(function (svg) {
        svg.setAttribute("class", el.getAttribute("class") || "");
        el.parentNode.replaceChild(svg, el);
      }).catch(function () {});
    });
    var slots = document.querySelectorAll("[data-figure-slot]");
    Array.prototype.forEach.call(slots, function (slot) {
      load(slot.getAttribute("data-figure-slot")).then(function (svg) {
        svg.setAttribute("class", "block h-auto w-full");
        slot.appendChild(svg);
        lean(slot, svg);
      }).catch(function () {});
    });
  }

  var idle = window.requestIdleCallback || function (fn) { return setTimeout(fn, 1500); };
  if (document.readyState === "complete") idle(run);
  else addEventListener("load", function () { idle(run); });
})();
