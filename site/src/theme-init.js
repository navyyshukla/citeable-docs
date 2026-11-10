// Classic script (no import/export), loaded in <head> so the saved theme applies before first paint.
try {
  var t = localStorage.getItem("theme");
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
} catch (e) {
  // storage blocked: fall back to the device setting
}
