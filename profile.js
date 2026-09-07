// Six-axis "profile" radar. Pure rendering, no app state: shared later with facilitator/.
// assets: [{ name, color }], levels: [0..1] in the same order.
window.IdentityProfile = (function () {
  const N = 6, CX = 150, CY = 150, R = 110;
  const angle = i => -Math.PI / 2 + (i * 2 * Math.PI) / N;
  const point = (r, i) => `${CX + r * Math.cos(angle(i))},${CY + r * Math.sin(angle(i))}`;

  function radar(assets, levels) {
    const rings = [0.25, 0.5, 0.75, 1]
      .map(k => `<polygon points="${assets.map((_, i) => point(R * k, i)).join(" ")}" fill="none" stroke="var(--line)" stroke-width="1"/>`)
      .join("");
    const spokes = assets
      .map((_, i) => `<line x1="${CX}" y1="${CY}" x2="${CX + R * Math.cos(angle(i))}" y2="${CY + R * Math.sin(angle(i))}" stroke="var(--line)"/>`)
      .join("");
    const shape = assets.map((_, i) => point(R * levels[i], i)).join(" ");
    const dots = assets
      .map((a, i) => `<circle cx="${CX + R * levels[i] * Math.cos(angle(i))}" cy="${CY + R * levels[i] * Math.sin(angle(i))}" r="4" fill="${a.color}"/>`)
      .join("");
    const labels = assets
      .map((a, i) => `<text x="${CX + (R + 26) * Math.cos(angle(i))}" y="${CY + (R + 26) * Math.sin(angle(i))}" fill="var(--ink-dim)" font-size="11" text-anchor="middle" dominant-baseline="middle">${a.name}</text>`)
      .join("");
    return `<svg viewBox="0 0 300 300" width="300" height="300" role="img" aria-label="הפרופיל שלי">${rings}${spokes}<polygon points="${shape}" fill="rgba(242,193,78,.25)" stroke="var(--c1)" stroke-width="2"/>${dots}${labels}</svg>`;
  }

  function text(assets, levels) {
    return assets.map((a, i) => `${a.name}: ${Math.round(levels[i] * 100)}`).join(" · ");
  }

  return { radar, text };
})();
