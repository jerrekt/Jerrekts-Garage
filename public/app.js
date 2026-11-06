// Jerrekt's Garage, public page. Reads /api/public (same origin, nginx proxies it to the bot).
// Nothing here is secret. The API only ever returns cars switched to public, with no owner.
(function () {
  "use strict";
  const DISCORD_INVITE = ""; // server invite link, once there is one; empty hides the button
  const API = document.body.dataset.api || "api/public";
  const $cars = document.getElementById("cars");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const k = m => m == null ? "" : m.toLocaleString("en-US");
  const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const when = s => { if (!s) return ""; const p = s.slice(0, 10).split("-"); return p[1] ? `${MON[+p[1] - 1]} ${p[0]}` : p[0]; };

  function drum(m) {
    if (m == null) return '<span class="small">no mileage yet</span>';
    return `<span class="drum num" aria-label="${k(m)} miles">${String(m).padStart(6, "0").split("").map(x => `<span>${x}</span>`).join("")}<span class="u">mi</span></span>`;
  }
  function dueRows(due) {
    if (!due || !due.length) return "";
    return `<div class="rows">${due.map(d => `<div class="row ${esc(d.status)}"><div class="bar"></div><div><b>${esc(d.job)}</b> <span class="s">${esc(d.text)}</span></div><span class="st">${esc(d.label)}</span></div>`).join("")}</div>`;
  }
  function history(visits) {
    if (!visits || !visits.length) return '<p class="small gap empty">Nothing logged yet.</p>';
    const rows = visits.map(v => `<div class="visit"><div class="when num">${esc(when(v.date))}<br>${v.miles != null ? k(v.miles) + " mi" : ""}</div><div class="jobs">${(v.jobs || []).map(j => `<span>${esc(j.name)}${j.system ? `<i class="sys">${esc(j.system)}</i>` : ""}</span>`).join("")}</div></div>`).join("");
    return `<details class="hist"><summary><span>History</span><span class="small">${visits.length} visit${visits.length === 1 ? "" : "s"}</span></summary>${rows}</details>`;
  }
  function card(c) {
    const sub = [c.year, c.chassis ? c.chassis.toUpperCase() : ""].filter(Boolean).join(" · ");
    return `<article class="card"><div class="head"><div><b>${esc(c.name)}</b><div class="small">${esc(sub)}${c.odometer && c.odometer.date ? ` · odometer ${esc(when(c.odometer.date))}` : ""}</div></div>${drum(c.odometer && c.odometer.miles)}</div>${dueRows(c.due)}${history(c.visits)}</article>`;
  }
  function ask() {
    const el = document.getElementById("ask");
    if (!el) return;
    el.innerHTML = DISCORD_INVITE
      ? `<a class="big disc" href="${esc(DISCORD_INVITE)}" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.3 4.4A19.8 19.8 0 0 0 15.4 3l-.2.4a18 18 0 0 1 4.4 2.2 15.6 15.6 0 0 0-15.2 0A18 18 0 0 1 8.8 3.4L8.6 3a19.8 19.8 0 0 0-4.9 1.4C.6 9 .1 13.5.3 17.9a19.9 19.9 0 0 0 6 3l1.3-2a12.3 12.3 0 0 1-2-1l.5-.4a14.1 14.1 0 0 0 11.8 0l.5.4-2 1 1.3 2a19.9 19.9 0 0 0 6-3c.3-5-.9-9.4-3.4-13.5ZM8.4 15.2c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.1 2.4c0 1.3-.9 2.4-2.1 2.4Zm7.2 0c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.1 2.4c0 1.3-.9 2.4-2.1 2.4Z"/></svg> Join the garage on Discord</a>`
      : `<p class="small">You know how to reach Jerrekt. Message him on Discord and say which car.</p>`;
  }

  async function load() {
    try {
      const r = await fetch(API, { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      const data = await r.json();
      const cars = (data.cars || []).slice().sort((a, b) => (a.year || 0) - (b.year || 0));
      $cars.innerHTML = cars.length ? cars.map(card).join("") : '<div class="card empty">No car is switched to public right now. The bays are full, the doors are just closed.</div>';
    } catch (e) {
      $cars.innerHTML = '<div class="card empty">The garage bot isn\'t answering right now. Try again in a minute.</div>';
    }
  }
  ask();
  load();
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) document.getElementById("logo").classList.add("f1");
})();
