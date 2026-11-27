// Preia tema aleasă în aplicații (cookie-ul securesync-theme: "light" sau "dark").
// Fără cookie rămâne tema sistemului. Cookie-urile nu țin cont de port, deci localhost:8080 îl primește.
// Template-ul Keycloak adaugă/scoate singur clasa pf-v5-theme-dark după tema sistemului, după ce acest
// script a rulat. Un MutationObserver o aduce înapoi la alegerea din aplicații, ca textul să rămână
// lizibil (cookie "light" pe un sistem întunecat ar da altfel text deschis pe fond deschis).
(function () {
  var match = document.cookie.match(/(?:^|;\s*)securesync-theme=(light|dark)/);
  if (!match) return;
  var choice = match[1];
  var root = document.documentElement;
  function apply() {
    if (root.getAttribute('data-ss-theme') !== choice) root.setAttribute('data-ss-theme', choice);
    var wantDark = choice === 'dark';
    if (root.classList.contains('pf-v5-theme-dark') !== wantDark) root.classList.toggle('pf-v5-theme-dark', wantDark);
  }
  apply();
  new MutationObserver(apply).observe(root, { attributes: true, attributeFilter: ['class'] });
})();
