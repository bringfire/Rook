export const APP_TITLE = "Rook Three.js Rhino Stress Harness";
if (typeof document !== "undefined") {
  document.title = APP_TITLE;
  document.querySelector("#app").innerHTML =
    '<main class="shell"><h1>' + APP_TITLE + '</h1><p>Scaffold ready.</p></main>';
}
