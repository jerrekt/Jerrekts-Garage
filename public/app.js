// Jerrekt's Garage. One page: the public bays for everyone, "Your garage" after Discord sign-in.
// Same origin for everything: nginx proxies /api and /auth to the bot. Nothing here is secret.
(function () {
  "use strict";
  const $cars = document.getElementById("cars"), $me = document.getElementById("me");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const k = m => m == null ? "" : Number(m).toLocaleString("en-US");
  const MON = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const when = s => { if (!s) return ""; const p = s.slice(0, 10).split("-"); return p[1] ? `${MON[+p[1] - 1]} ${p[0]}` : p[0]; };
  const DISC = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.3 4.4A19.8 19.8 0 0 0 15.4 3l-.2.4a18 18 0 0 1 4.4 2.2 15.6 15.6 0 0 0-15.2 0A18 18 0 0 1 8.8 3.4L8.6 3a19.8 19.8 0 0 0-4.9 1.4C.6 9 .1 13.5.3 17.9a19.9 19.9 0 0 0 6 3l1.3-2a12.3 12.3 0 0 1-2-1l.5-.4a14.1 14.1 0 0 0 11.8 0l.5.4-2 1 1.3 2a19.9 19.9 0 0 0 6-3c.3-5-.9-9.4-3.4-13.5ZM8.4 15.2c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.1 2.4c0 1.3-.9 2.4-2.1 2.4Zm7.2 0c-1.2 0-2.1-1.1-2.1-2.4s.9-2.4 2.1-2.4 2.2 1.1 2.1 2.4c0 1.3-.9 2.4-2.1 2.4Z"/></svg>';
  let ME = null, open = {}; // open: car id -> which form is open

  // ---- shared pieces ----
  function drum(m) {
    if (m == null) return '<span class="small">no mileage yet</span>';
    return `<span class="drum num" aria-label="${k(m)} miles">${String(m).padStart(6, "0").split("").map(x => `<span>${x}</span>`).join("")}<span class="u">mi</span></span>`;
  }
  function dueRows(due) {
    if (!due || !due.length) return "";
    return `<div class="rows">${due.map(d => `<div class="row ${esc(d.status)}"><div class="bar"></div><div><b>${d.safety && d.status !== "ok" ? "⚠️ " : ""}${esc(d.job)}</b> <span class="s">${esc(d.text)}</span></div><span class="st">${esc(d.label)}</span></div>`).join("")}</div>`;
  }
  function history(visits) {
    if (!visits || !visits.length) return '<p class="small gap empty">Nothing logged yet.</p>';
    const rows = visits.map(v => `<div class="visit"><div class="when num">${esc(when(v.date))}<br>${v.miles != null ? k(v.miles) + " mi" : ""}</div><div class="jobs">${(v.jobs || []).map(j => `<span>${esc(j.name)}${j.system ? `<i class="sys">${esc(j.system)}</i>` : ""}${j.parts ? `<i class="small"> · ${esc(j.parts)}</i>` : ""}</span>`).join("")}</div></div>`).join("");
    return `<details class="hist"><summary><span>History</span><span class="small">${visits.length} visit${visits.length === 1 ? "" : "s"}</span></summary>${rows}</details>`;
  }
  function head(c, extra) {
    const sub = [c.year, c.chassis ? c.chassis.toUpperCase() : ""].filter(Boolean).join(" · ");
    return `<div class="head"><div><b>${esc(c.name)}</b>${extra || ""}<div class="small">${esc(sub)}${c.odometer && c.odometer.date ? ` · odometer ${esc(when(c.odometer.date))}` : ""}</div></div>${drum(c.odometer && c.odometer.miles)}</div>`;
  }

  // ---- public bays ----
  async function loadPublic() {
    try {
      const r = await fetch("api/public", { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      const cars = ((await r.json()).cars || []).slice().sort((a, b) => (a.year || 0) - (b.year || 0));
      $cars.innerHTML = cars.length ? cars.map(c => `<article class="card">${head(c)}${dueRows(c.due)}${history(c.visits)}</article>`).join("")
        : '<div class="card empty">No car is switched to public right now. The bays are full, the doors are just closed.</div>';
    } catch (e) {
      $cars.innerHTML = '<div class="card empty">The garage bot isn\'t answering right now. Try again in a minute.</div>';
    }
  }

  // ---- your garage ----
  const field = (name, label, attrs = "", wide = false) => `<label${wide ? ' class="wide"' : ""}>${label}<input name="${name}" ${attrs}></label>`;
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  function formLog(c) {
    return `<form class="f" data-act="log" data-car="${esc(c.id)}">
      ${field("job", "What you did", 'required maxlength="120" placeholder="Oil change 5W-40"', true)}
      ${field("miles", "Miles", `inputmode="numeric" placeholder="${c.odometer && c.odometer.miles != null ? k(c.odometer.miles) : ""}"`)}
      ${field("date", "Date", `type="date" value="${today()}"`)}
      <label>Type<select name="type"><option value="">—</option><option>preventive</option><option>corrective</option><option>diagnostic</option><option>upgrade</option></select></label>
      <label>System<select name="system"><option value="">guess</option>${["engine","cooling","drivetrain","suspension","steering","brakes","tires","body","electrical","other"].map(s => `<option>${s}</option>`).join("")}</select></label>
      ${field("parts", "Parts (optional)", 'maxlength="300" placeholder="FCP order #, part numbers"', true)}
      <button class="btn gold wide" type="submit">Log it</button></form>`;
  }
  function formOdo(c) {
    return `<form class="f" data-act="odo" data-car="${esc(c.id)}">${field("miles", "Odometer now", 'required inputmode="numeric"')}${field("date", "Date", `type="date" value="${today()}"`)}<button class="btn gold wide" type="submit">Save reading</button></form>`;
  }
  function formAdd() {
    return `<form class="f" data-act="addcar">
      ${field("name", "Car", 'required maxlength="60" placeholder="2008 Civic Si"', true)}
      ${field("chassis", "Short id", 'maxlength="20" placeholder="civic"')}
      ${field("year", "Year", 'inputmode="numeric" maxlength="4"')}
      ${field("miles", "Miles now", 'inputmode="numeric"', true)}
      <button class="btn gold wide" type="submit">Add my car</button></form>`;
  }
  function kits(list) {
    if (!list || !list.length) return "";
    return `<article class="card"><div class="head"><b>Parts kits</b><span class="small">FCP Euro, lifetime warranty</span></div>${list.map(j => `<div class="kit"><b>${esc(j.name)}</b>${j.kit ? `<a href="${esc(j.kit.url)}" rel="noopener">Whole kit ${esc(j.kit.sku)} · $${Number(j.kit.price || 0).toFixed(2)}</a>` : ""}${(j.parts || []).map(p => p.url ? `<a href="${esc(p.url)}" rel="noopener">${esc(p.name)} ×${p.qty || 1} · ${esc(p.pn)}</a>` : `<span class="small">${esc(p.name)} ×${p.qty || 1} · ${esc(p.pn)} (in kit)</span>`).join("")}${(j.extras || []).map(e => `<a href="${esc(e.url)}" rel="noopener">+ ${esc(e.name)} ×${e.qty || 1} · ${esc(e.pn)}</a>`).join("")}</div>`).join("")}</article>`;
  }
  function myCar(c) {
    const mine = !ME.admin || c.owner === ME.user.name;
    const pills = (c.status !== "active" ? `<span class="pill ${esc(c.status)}">${esc(c.status)}</span>` : "") + (c.public ? '<span class="pill pub">public</span>' : "");
    const owner = ME.admin && c.owner && !mine ? `<span class="small"> · ${esc(c.owner)}</span>` : "";
    const o = open[c.id];
    let acts = `<button class="btn" data-open="log" data-car="${esc(c.id)}" aria-pressed="${o === "log"}">Log work</button><button class="btn" data-open="odo" data-car="${esc(c.id)}" aria-pressed="${o === "odo"}">Odometer</button>`;
    if (ME.admin && c.status === "pending") acts += `<button class="btn ok" data-act="approve" data-car="${esc(c.id)}">Approve</button><button class="btn bad" data-act="reject" data-car="${esc(c.id)}">Reject</button>`;
    if (ME.admin && c.status === "active") acts += `<button class="btn" data-act="public" data-car="${esc(c.id)}" data-show="${c.public ? 0 : 1}">${c.public ? "Hide from public" : "Show on public"}</button>`;
    acts += `<button class="link rm" data-open="remove" data-car="${esc(c.id)}">${o === "remove" || o === "remove2" ? "cancel" : "remove car"}</button>`;
    const od = c.odometer || {}, stale = od.miles == null ? null : od.date ? Math.round((Date.now() - new Date(od.date.length > 7 ? od.date : od.date + "-01")) / 864e5) : null;
    const nudge = od.miles == null ? "No odometer reading yet. Add one (with the date) and the due list comes alive."
      : stale == null ? "The last odometer reading has no date. Save a fresh one with today's date so the estimates work."
      : stale > 45 ? `Last odometer reading is from ${esc(when(od.date))}. Save a fresh one and the dates update.` : "";
    const paceLine = c.pace ? `<span class="small">Your pace: about ${k(Math.round(c.pace.miles_per_day * 30.44))} mi a month.</span>` : "";
    let form = nudge ? `<p class="msg" style="color:var(--soon)">${nudge} ${paceLine}</p>` : (paceLine ? `<p class="msg">${paceLine}</p>` : "");
    if (o === "log") form += formLog(c);
    if (o === "odo") form += formOdo(c);
    if (o === "remove") form += `<div class="f"><p class="wide small">Remove ${esc(c.name)}? That deletes the car and every job logged on it (${(c.visits || []).length} visit${(c.visits || []).length === 1 ? "" : "s"}). No undo.</p><button class="btn bad wide" data-open="remove2" data-car="${esc(c.id)}">Yes, I want to remove it</button></div>`;
    if (o === "remove2") form += `<form class="f" data-act="remove" data-car="${esc(c.id)}" data-confirm="${esc(c.id)}">${field("sure", `Last check: type ${esc(c.id)} to confirm`, 'required autocomplete="off"', true)}<button class="btn bad wide" type="submit">Delete ${esc(c.name)} for good</button></form>`;
    return `<article class="card" id="car-${esc(c.id)}">${head(c, pills + owner)}${dueRows(c.due)}${history(c.visits)}<div class="acts">${acts}</div>${form}<div class="msg" data-msg="${esc(c.id)}"></div></article>`;
  }
  function renderMe() {
    const failed = new URLSearchParams(location.search).get("signin") === "failed";
    if (!ME || !ME.signed_in) {
      $me.innerHTML = `<div class="card"><p class="small" style="margin-bottom:12px">Your cars, your due list, your friends' cars kept to themselves. Sign in to see yours.</p>${ME && ME.login === false ? '<p class="empty">Sign-in isn\'t switched on yet.</p>' : `<a class="big disc" href="auth/login">${DISC} Sign in with Discord</a>`}${failed ? '<p class="msg err">That sign-in didn\'t go through. Try again.</p>' : ""}</div>`;
      return;
    }
    const bar = `<div class="me-head"><b>Hi ${esc(ME.user.name)}${ME.admin ? " · owner" : ""}</b><button class="link" id="logout">Sign out</button></div>`;
    if (!ME.known) {
      $me.innerHTML = `<div class="card">${bar}<p class="small" style="margin-top:8px">You're not on the garage list yet. Add your car and ${esc(ME.admin_name)} will approve it; until then it's a request.</p>${formAdd()}<div class="msg" data-msg="new"></div></div>`;
      return wire();
    }
    const cars = (ME.cars || []).slice().sort((a, b) => (a.status === "pending" ? -1 : 0) - (b.status === "pending" ? -1 : 0));
    const pending = ME.admin ? cars.filter(c => c.status === "pending").length : 0;
    $me.innerHTML = `<div class="card">${bar}${pending ? `<p class="msg" style="color:var(--soon)">${pending} car${pending === 1 ? "" : "s"} waiting for your approval.</p>` : ""}</div>`
      + (cars.length ? cars.map(myCar).join("") : '<div class="card empty">No cars yet. Add one below.</div>')
      + `<article class="card"><div class="head"><b>Add a car</b></div>${formAdd()}<div class="msg" data-msg="new"></div></article>`
      + kits(ME.kits);
    wire();
  }
  function say(id, text, ok) { const el = $me.querySelector(`[data-msg="${CSS.escape(id)}"]`); if (el) { el.textContent = text; el.className = "msg " + (ok ? "ok" : "err"); } }
  async function act(body, msgId) {
    try {
      const r = await fetch("api/act", { method: "POST", headers: { "content-type": "application/json", "x-garage-web": "1" }, body: JSON.stringify(body) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) { say(msgId, j.detail || `Didn't work (${r.status}).`, false); return false; }
      return j;
    } catch (e) { say(msgId, "The garage bot isn't answering.", false); return false; }
  }
  async function refresh() {
    try { const r = await fetch("api/me", { cache: "no-store" }); ME = r.ok ? await r.json() : null; } catch (e) { ME = null; }
    renderMe();
  }
  function wire() {
    $me.querySelectorAll("[data-open]").forEach(b => b.onclick = () => { const id = b.dataset.car; open[id] = open[id] === b.dataset.open ? null : b.dataset.open; renderMe(); });
    $me.querySelectorAll("button[data-act]").forEach(b => b.onclick = async () => {
      b.disabled = true;
      const body = { action: b.dataset.act, car: b.dataset.car };
      if (b.dataset.act === "public") body.show = b.dataset.show === "1";
      const r = await act(body, b.dataset.car);
      if (r) { open[b.dataset.car] = null; await refresh(); loadPublic(); } else b.disabled = false;
    });
    $me.querySelectorAll("form[data-act]").forEach(f => f.onsubmit = async ev => {
      ev.preventDefault();
      const body = { action: f.dataset.act, car: f.dataset.car };
      new FormData(f).forEach((v, n) => { if (String(v).trim() !== "") body[n] = String(v).trim(); });
      if (f.dataset.confirm && body.sure !== f.dataset.confirm) { say(f.dataset.car, `That's not "${f.dataset.confirm}". Nothing removed.`, false); return; }
      const btn = f.querySelector("button[type=submit]"); btn.disabled = true;
      const r = await act(body, f.dataset.car || "new");
      if (r) { if (f.dataset.car) open[f.dataset.car] = null; await refresh(); if (r.warning) say(f.dataset.car, r.warning, false); if (!f.dataset.car && r.car) say("new", r.car.status === "pending" ? `Added ${r.car.name}. Waiting for approval.` : `Added ${r.car.name}.`, true); loadPublic(); }
      else btn.disabled = false;
    });
    const lo = document.getElementById("logout");
    if (lo) lo.onclick = async () => { await fetch("auth/logout", { method: "POST", headers: { "x-garage-web": "1" } }); refresh(); };
  }

  loadPublic();
  refresh();
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches) document.getElementById("logo").classList.add("f1");
})();
