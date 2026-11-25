// Preia tema aleasă în aplicații (cookie-ul securesync-theme: "light" sau "dark").
// Fără cookie rămâne tema sistemului. Cookie-urile nu țin cont de port, deci localhost:8080 îl primește.
(function () {
  var match = document.cookie.match(/(?:^|;\s*)securesync-theme=(light|dark)/);
  if (!match) return;
  var root = document.documentElement;
  root.setAttribute('data-ss-theme', match[1]);
  root.classList.toggle('pf-v5-theme-dark', match[1] === 'dark');
})();
