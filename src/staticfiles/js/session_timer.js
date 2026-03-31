(function () {
  const el = document.getElementById("session-timer");
  if (!el) return;

  let seconds = parseInt(el.dataset.seconds || "0", 10);

  function formatMMSS(s) {
    const m = Math.floor(s / 60);
    const r = s % 60;
    return String(m).padStart(2, "0") + ":" + String(r).padStart(2, "0");
  }

  function tick() {
    if (seconds <= 0) {
      el.textContent = "Sessão: 00:00";
      // Quando zerar, só avisa visualmente.
      // (Logout automático por inatividade é outra camada — via middleware)
      return;
    }
    el.textContent = "Sessão: " + formatMMSS(seconds);
    seconds -= 1;
    setTimeout(tick, 1000);
  }

  tick();
})();
