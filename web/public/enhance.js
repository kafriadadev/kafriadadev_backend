/*
 * The only script on the registration page, which ships no framework.
 * Two things, both optional: group a phone number as it is typed (the same
 * rule as src/lib/phone.ts; keep them in step), and say what is happening once
 * the form is sent, refusing a second press. Without it the form still works.
 */
(function () {
  function format(raw) {
    var plus = raw.trim().charAt(0) === "+";
    var digits = raw.replace(/\D/g, "");
    if (!digits) return plus ? "+" : "";
    var prefix = "";
    var rest = digits;
    if (plus || digits.indexOf("234") === 0) {
      prefix = (plus ? "+" : "") + digits.slice(0, 3);
      rest = digits.slice(3);
      if (!rest) return prefix;
    }
    var sizes = !prefix && rest.charAt(0) === "0" ? [4, 3, 4] : [3, 3, 4];
    var groups = [];
    var i = 0;
    for (var s = 0; s < sizes.length && i < rest.length; s++) {
      groups.push(rest.slice(i, i + sizes[s]));
      i += sizes[s];
    }
    if (i < rest.length) groups[groups.length - 1] += rest.slice(i);
    return [prefix].concat(groups).filter(Boolean).join(" ");
  }
  function caret(formatted, before) {
    if (before <= 0) return formatted.charAt(0) === "+" ? 1 : 0;
    for (var i = 0, seen = 0; i < formatted.length; i++) {
      if (/\d/.test(formatted.charAt(i))) seen++;
      if (seen === before) return i + 1;
    }
    return formatted.length;
  }
  document.addEventListener("input", function (e) {
    var el = e.target;
    if (!el.hasAttribute || !el.hasAttribute("data-phone")) return;
    var end = el.selectionStart == null ? el.value.length : el.selectionStart;
    var before = el.value.slice(0, end).replace(/\D/g, "").length;
    var next = format(el.value);
    if (next === el.value) return;
    el.value = next;
    var at = caret(next, before);
    el.setSelectionRange(at, at);
  });
  document.addEventListener("submit", function (e) {
    var button = e.target.querySelector("button[data-pending]");
    if (!button) return;
    if (button.getAttribute("aria-busy")) return e.preventDefault();
    button.setAttribute("aria-busy", "true");
    var label = button.querySelector("span");
    if (label) label.textContent = button.getAttribute("data-pending");
  });
  // Coming back with the Back button shows the page as it was left: reset it.
  window.addEventListener("pageshow", function () {
    var busy = document.querySelectorAll("button[data-pending][aria-busy]");
    for (var i = 0; i < busy.length; i++) {
      busy[i].removeAttribute("aria-busy");
      var label = busy[i].querySelector("span");
      if (label) label.textContent = busy[i].getAttribute("data-label");
    }
  });
})();
