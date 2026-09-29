// PLANFGEN — studio web. No framework, no build step: one module, the DOM, fetch.
//
// The page edits a PROJECT — a building of storeys, each storey a plate of flats,
// each flat a type designed once — and keeps it, with every generated option, in
// localStorage on every change: a download, a reload, a new brief lose nothing.
//
//   Immeuble (building)  ─ lot, profile, storeys, unit types; summary + stack
//     └─ Niveau (storey) ─ the plate: the unit slots along the street, the core
//          └─ Logement type (unit) ─ rooms; the gallery of generated options
//
// Only the unit level generates today; the other two are drawn from what the
// units asked for and what was retained, and say so.

import { planSVG, plateSVG } from "./plan.js";

const STORE = "planfgen.web.v2";
const $ = (id) => document.getElementById(id);
const SIDES_FR = { bas: "Bas", droite: "Droite", haut: "Haut", gauche: "Gauche" };
const COMPASS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"];
const SCORE_FR = { adjacences: "Adjacences", orientation: "Orientation", circulation: "Circulation", compacite: "Compacité" };

let meta = null;
let state = {
  project: null,       // the brief: planfgen.project/1
  galleries: {},       // unitId -> [{id, seed, iterations, spec, status, payload, error}]
  selected: {},        // unitId -> entry id retained for that unit type
  view: { level: "building", storey: null, unit: null },
  summary: null,       // last /api/building/summary
  count: 6,
  iterations: 200,
  sort: false,
};
const batches = {};    // unitId -> AbortController
let checkTimer = null;
let summaryTimer = null;

// --- persistence -------------------------------------------------------------------

function save() {
  try {
    localStorage.setItem(STORE, JSON.stringify(state));
  } catch {
    // Over quota: keep the project and the seeds; plans come back on load (same seed, same plan).
    const galleries = Object.fromEntries(Object.entries(state.galleries).map(([k, g]) =>
      [k, g.map((e) => ({ ...e, payload: null, status: "pending" }))]));
    try { localStorage.setItem(STORE, JSON.stringify({ ...state, galleries })); } catch { /* nothing more */ }
  }
}

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) || "null");
    if (saved && saved.project && saved.project.schema === "planfgen.project/1") state = { ...state, ...saved };
  } catch { /* a corrupt store is an empty one */ }
}

// --- api ---------------------------------------------------------------------------

async function api(path, body, signal) {
  const res = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!res.ok) {
    let message = `Erreur ${res.status}`;
    try { message = (await res.json()).error || message; } catch { /* keep the status */ }
    throw new Error(message);
  }
  return res;
}

// --- helpers -----------------------------------------------------------------------

function fmt(v, p = 2) { return Number(v).toFixed(p).replace(".", ","); }
function pct(v) { return `${(v * 100).toFixed(1).replace(".", ",")} %`; }
function esc(t) { return String(t ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
function opts(entries, value) {
  return entries.map(([k, label]) => `<option value="${esc(k)}"${String(k) === String(value) ? " selected" : ""}>${esc(label)}</option>`).join("");
}
function facing(sideIndex, northDeg) {
  // Outward normal of each side of the lot, as a bearing clockwise from north.
  const [nx, ny] = [[0, -1], [1, 0], [0, 1], [-1, 0]][sideIndex];
  const bearing = (Math.atan2(nx, ny) - (northDeg * Math.PI) / 180 + 4 * Math.PI) % (2 * Math.PI);
  return COMPASS[Math.round(bearing / (Math.PI / 4)) % 8];
}

const P = () => state.project;
const unitOf = (uid) => P().units.find((u) => u.id === uid);
const storeyOf = (sid) => P().storeys.find((s) => s.id === sid);
const gallery = (uid) => (state.galleries[uid] ||= []);

// The brief one flat is generated from. Mirrors `web.project.unit_spec`.
function unitSpec(uid) {
  const p = P(), u = unitOf(uid), lot = p.lot;
  const entry = [0, 2].includes(lot.entry_edge) ? lot.entry_edge : 0;
  return {
    typology: u.typology,
    profile: p.profile,
    width: u.slot.width,
    depth: u.slot.depth,
    north: lot.north,
    edges: [lot.edges[0], "MITOYEN", lot.edges[2], "MITOYEN"],
    entry_edge: entry,
    rooms: u.rooms,
    relations: u.relations,
  };
}

function retained(uid) {
  const id = state.selected[uid];
  return gallery(uid).find((g) => g.id === id && g.status === "done" && g.payload.ok) || null;
}

// --- navigation --------------------------------------------------------------------

function go(level, ids = {}) {
  state.view = { level, storey: ids.storey ?? state.view.storey, unit: ids.unit ?? state.view.unit };
  if (level === "storey" && !storeyOf(state.view.storey)) state.view.storey = P().storeys[0]?.id ?? null;
  if (level === "unit" && !unitOf(state.view.unit)) state.view.unit = P().units[0]?.id ?? null;
  save();
  render();
  window.scrollTo(0, 0);
}

function render() {
  const level = state.view.level;
  for (const el of document.querySelectorAll("[data-level]")) el.hidden = el.dataset.level !== level;
  renderCrumbs();
  renderTree();
  if (level === "building") { renderBuildingForm(); renderBuildingView(); }
  if (level === "storey") { renderStoreyForm(); renderStoreyView(); }
  if (level === "unit") { renderUnitForm(); renderGallery(); renderDetail(); renderStale(); runCheck(); }
}

function renderCrumbs() {
  const v = state.view;
  const parts = [`<a data-go="building">${esc(P().name || "Immeuble")}</a>`];
  if (v.level === "storey" && storeyOf(v.storey)) parts.push(`<a data-go="storey">${esc(storeyLabel(storeyOf(v.storey)))}</a>`);
  if (v.level === "unit" && unitOf(v.unit)) {
    const u = unitOf(v.unit);
    parts.push(`<a data-go="unit">${esc(u.label)} — ${esc(u.typology)}</a>`);
  }
  $("crumbs").innerHTML = parts.join('<span class="sep">›</span>');
}

function storeyLabel(s) { return s.repeat > 1 ? `${s.label} ×${s.repeat}` : s.label; }

function renderTree() {
  const v = state.view;
  const units = P().units.map((u) => {
    const done = retained(u.id) ? "●" : "○";
    return `<li class="${v.level === "unit" && v.unit === u.id ? "on" : ""}"><a data-go="unit" data-unit="${u.id}">${done} ${esc(u.label)} <em>${esc(u.typology)}</em></a></li>`;
  }).join("");
  const storeys = [...P().storeys].reverse().map((s) =>
    `<li class="${v.level === "storey" && v.storey === s.id ? "on" : ""}"><a data-go="storey" data-storey="${s.id}">${esc(storeyLabel(s))} <em>${s.slots.length} logt</em></a></li>`).join("");
  $("tree").innerHTML = `
    <a class="root${v.level === "building" ? " on" : ""}" data-go="building">▣ ${esc(P().name || "Immeuble")}</a>
    <div class="tree-cols">
      <div><h3>Niveaux</h3><ul>${storeys}</ul></div>
      <div><h3>Logements types</h3><ul>${units}</ul></div>
    </div>`;
}

document.addEventListener("click", (e) => {
  const a = e.target.closest("[data-go]");
  if (!a) return;
  e.preventDefault();
  go(a.dataset.go, { storey: a.dataset.storey, unit: a.dataset.unit });
});

// --- building level ----------------------------------------------------------------

function renderBuildingForm() {
  const p = P();
  $("p-name").value = p.name;
  $("p-profile").innerHTML = opts(Object.entries(meta.profiles), p.profile);
  $("p-width").value = p.lot.width;
  $("p-depth").value = p.lot.depth;
  $("p-north").value = p.lot.north;
  renderEdges();
  $("p-storeys").innerHTML = `<tr><th>Nom</th><th>Type</th><th>×</th><th></th><th></th></tr>` + p.storeys.map((s, i) => `
    <tr><td><input data-storey-row="${i}" data-field="label" value="${esc(s.label)}"></td>
    <td><select data-storey-row="${i}" data-field="kind">${opts(Object.entries(meta.storey_kinds), s.kind)}</select></td>
    <td><input data-storey-row="${i}" data-field="repeat" type="number" min="1" max="40" value="${s.repeat}"></td>
    <td><a class="open" data-go="storey" data-storey="${s.id}">ouvrir ›</a></td>
    <td><button class="icon" data-remove-storey="${i}" type="button" title="Retirer">×</button></td></tr>`).join("");
  $("p-units").innerHTML = `<tr><th>Nom</th><th>Typo.</th><th>Trame</th><th></th><th></th></tr>` + p.units.map((u, i) => `
    <tr><td><input data-unit-row="${i}" data-field="label" value="${esc(u.label)}"></td>
    <td>${esc(u.typology)}</td>
    <td class="fine">${fmt(u.slot.width, 1)} × ${fmt(u.slot.depth, 1)}</td>
    <td><a class="open" data-go="unit" data-unit="${u.id}">ouvrir ›</a></td>
    <td><button class="icon" data-remove-unit="${i}" type="button" title="Retirer">×</button></td></tr>`).join("");
  $("new-unit-typology").innerHTML = opts(Object.entries(meta.presets).map(([k, pr]) => [k, pr.label]), "F3");
}

function renderEdges() {
  const lot = P().lot;
  $("p-edges").innerHTML = meta.sides.map((side, i) => `
    <div class="edge">
      <span class="side">${SIDES_FR[side]} <em>${facing(i, lot.north)}</em></span>
      <select data-edge="${i}">${opts(Object.entries(meta.edges), lot.edges[i])}</select>
      <label class="entry"><input type="radio" name="entry" value="${i}"${lot.entry_edge === i ? " checked" : ""}> entrée</label>
    </div>`).join("");
}

function projectChanged({ form = false } = {}) {
  save();
  renderCrumbs();
  renderTree();
  if (form) renderBuildingForm();
  clearTimeout(summaryTimer);
  summaryTimer = setTimeout(refreshSummary, 200);
}

async function refreshSummary() {
  try {
    state.summary = await (await api("/api/building/summary", { project: P() })).json();
    save();
    if (state.view.level === "building") renderBuildingView();
    if (state.view.level === "storey") renderStoreyView();
  } catch (e) {
    $("status").textContent = e.message;
  }
}

function renderBuildingView() {
  const s = state.summary;
  if (!s) return;
  $("b-title").textContent = `${s.name || "Immeuble"} — ${s.height}`;
  const mix = Object.entries(s.mix).map(([t, n]) => `${n} × ${t}`).join(" · ") || "aucun";
  const retainedCount = P().units.filter((u) => retained(u.id)).length;
  $("b-figures").innerHTML = `
    <div><b>${s.height}</b><span>${s.levels} niveau${s.levels > 1 ? "x" : ""}</span></div>
    <div><b>${s.logements}</b><span>logements — ${esc(mix)}</span></div>
    <div><b>${fmt(s.utile, 0)} m²</b><span>surface utile demandée</span></div>
    <div><b>${fmt(s.lot_dims[0], 1)} × ${fmt(s.lot_dims[1], 1)}</b><span>parcelle, ${fmt(s.lot, 0)} m²</span></div>
    <div><b>${retainedCount} / ${P().units.length}</b><span>logements types retenus</span></div>`;
  // The stack: a section through the building, top storey first.
  const rows = [];
  let level = s.levels;
  for (const st of [...s.storeys].reverse()) {
    const top = level - 1, bottom = level - st.repeat;
    level -= st.repeat;
    const name = (n) => (n === 0 ? "RDC" : `R+${n}`);
    const range = st.repeat > 1 ? `${name(bottom)} → ${name(top)}` : name(top);
    // Same order as the plate drawing: the first flat, the core, the others.
    const core = `<span class="chip core" style="flex:${st.free}">noyau ${fmt(st.free, 1)} m</span>`;
    const items = [];
    st.units.forEach((u, i) => {
      items.push(`<span class="chip${retained(u.unit) ? " done" : ""}" style="flex:${u.slot[0]}">${esc(u.label)} · ${esc(u.typology)}</span>`);
      if (i === 0 && st.free > 0.05) items.push(core);
    });
    if (!st.units.length && st.free > 0.05) items.push(core);
    if (!st.fits) items.push(`<span class="chip over">dépasse ${fmt(Math.max(0, -st.free), 1)} m${st.too_deep.length ? " · trop profond" : ""}</span>`);
    rows.push(`<div class="storey-row" style="--rep:${st.repeat}" data-go="storey" data-storey="${st.id}">
      <div class="lvl"><b>${esc(st.label)}</b><span>${range}</span></div>
      <div class="band">${items.join("")}</div></div>`);
  }
  $("b-stack").innerHTML = rows.join("") + `<div class="ground">${esc(P().lot.edges[P().lot.entry_edge] === "STREET" ? "RUE" : "")}</div>`;
  $("b-plate-note").textContent = s.plate;
  $("b-gallery").innerHTML = s.storeys.map((st) => storeyCard(st, s)).join("");
}

function docsOf(st) {
  return Object.fromEntries(st.units.map((u) => [u.unit, retained(u.unit)?.payload.document || null]));
}

function storeyCard(st, s) {
  const flag = st.fits
    ? `<span class="tag ok">façade ${fmt(st.frontage, 1)} / ${fmt(s.lot_dims[0], 1)} m</span>`
    : `<span class="tag bad">ne tient pas : ${fmt(st.frontage, 1)} m pour ${fmt(s.lot_dims[0], 1)} m</span>`;
  return `<div class="card" data-go="storey" data-storey="${st.id}">
    <div class="card-head"><b>${esc(st.label)}${st.repeat > 1 ? ` <em class="fine">×${st.repeat}</em>` : ""}</b><span class="fine">${st.units.length} logement${st.units.length > 1 ? "s" : ""}</span></div>
    <div class="thumb wide">${plateSVG(st, s.lot_dims, docsOf(st), meta.palette, { id: `c${st.id}` })}</div>
    <div class="facts"><span>${fmt(st.utile, 1)} m² utiles</span>${flag}</div></div>`;
}

function bindBuildingForm() {
  $("p-name").addEventListener("input", (e) => { P().name = e.target.value; projectChanged(); });
  $("p-profile").addEventListener("change", (e) => { P().profile = e.target.value; projectChanged(); });
  for (const [id, key] of [["p-width", "width"], ["p-depth", "depth"], ["p-north", "north"]]) {
    $(id).addEventListener("input", (e) => {
      const v = parseFloat(e.target.value);
      if (Number.isFinite(v)) { P().lot[key] = v; if (key === "north") renderEdges(); projectChanged(); }
    });
  }
  $("p-edges").addEventListener("change", (e) => {
    if (e.target.dataset.edge !== undefined) P().lot.edges[Number(e.target.dataset.edge)] = e.target.value;
    if (e.target.name === "entry") P().lot.entry_edge = Number(e.target.value);
    projectChanged();
  });
  $("p-storeys").addEventListener("input", (e) => {
    const i = e.target.dataset.storeyRow;
    if (i === undefined) return;
    const s = P().storeys[Number(i)], f = e.target.dataset.field;
    s[f] = f === "repeat" ? Math.max(1, parseInt(e.target.value) || 1) : e.target.value;
    projectChanged();
  });
  $("p-storeys").addEventListener("click", (e) => {
    const i = e.target.dataset.removeStorey;
    if (i === undefined) return;
    P().storeys.splice(Number(i), 1);
    projectChanged({ form: true });
  });
  $("add-storey").addEventListener("click", () => {
    const top = P().storeys[P().storeys.length - 1];
    P().storeys.push({ id: `s${Date.now()}`, kind: "COURANT", label: "Étage courant", repeat: 1, slots: top ? top.slots.map((x) => ({ ...x })) : [] });
    projectChanged({ form: true });
  });
  $("p-units").addEventListener("input", (e) => {
    const i = e.target.dataset.unitRow;
    if (i === undefined) return;
    P().units[Number(i)].label = e.target.value;
    projectChanged();
  });
  $("p-units").addEventListener("click", (e) => {
    const i = e.target.dataset.removeUnit;
    if (i === undefined) return;
    const [u] = P().units.splice(Number(i), 1);
    for (const s of P().storeys) s.slots = s.slots.filter((x) => x.unit !== u.id);
    delete state.galleries[u.id];
    delete state.selected[u.id];
    projectChanged({ form: true });
  });
  $("add-unit").addEventListener("click", () => {
    const key = $("new-unit-typology").value;
    const used = new Set(P().units.map((u) => u.id));
    const id = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").find((c) => !used.has(c)) || `U${Date.now()}`;
    P().units.push(newUnit(id, `Type ${id}`, key));
    projectChanged({ form: true });
  });
}

function newUnit(id, label, key) {
  const pr = meta.presets[key];
  return {
    id, label, typology: key,
    slot: { width: pr.width, depth: pr.depth },
    rooms: JSON.parse(JSON.stringify(pr.rooms)),
    relations: JSON.parse(JSON.stringify(pr.relations)),
    chosen: null,
  };
}

// --- storey level ------------------------------------------------------------------

function renderStoreyForm() {
  const s = storeyOf(state.view.storey);
  if (!s) return;
  $("s-label").value = s.label;
  $("s-kind").innerHTML = opts(Object.entries(meta.storey_kinds), s.kind);
  $("s-repeat").value = s.repeat;
  $("s-slots").innerHTML = s.slots.map((slot, i) => {
    const u = unitOf(slot.unit);
    return `<tr><td>${i + 1}</td><td>${esc(u?.label)} <em class="fine">${esc(u?.typology)}</em></td>
      <td class="fine">${u ? `${fmt(u.slot.width, 1)} m` : ""}</td>
      <td><a class="open" data-go="unit" data-unit="${slot.unit}">ouvrir ›</a></td>
      <td><button class="icon" data-remove-slot="${i}" type="button" title="Retirer">×</button></td></tr>`;
  }).join("");
  $("new-slot-unit").innerHTML = opts(P().units.map((u) => [u.id, `${u.label} — ${u.typology}`]), P().units[0]?.id);
  $("s-pending").textContent = state.summary?.plate || "";
}

function renderStoreyView() {
  const s = storeyOf(state.view.storey);
  const st = state.summary?.storeys.find((x) => x.id === s?.id);
  if (!s || !st) return;
  const sum = state.summary;
  $("s-title").textContent = `${storeyLabel(s)} — ${st.units.length} logement${st.units.length > 1 ? "s" : ""}, façade ${fmt(st.frontage, 1)} m sur ${fmt(sum.lot_dims[0], 1)} m`;
  $("s-sheet").innerHTML = plateSVG(st, sum.lot_dims, docsOf(st), meta.palette, { detail: true, id: "sheet" })
    + `<p class="hint">${esc(sum.plate)}${st.fits ? ` Il reste ${fmt(st.free, 2)} m de façade pour le noyau et le palier.` : " Le plateau ne tient pas sur la parcelle."}</p>`;
  $("s-gallery").innerHTML = st.units.map((u, i) => {
    const r = retained(u.unit);
    const body = r
      ? `<div class="thumb">${planSVG(r.payload.document, meta.palette, { id: `sl${i}` })}</div>
         <div class="facts"><span>graine ${r.seed}</span><span>note ${Math.round(r.payload.scores.globale * 100)}</span><span>${fmt(r.payload.surface_utile, 1)} m²</span></div>`
      : `<div class="thumb none">Aucune option retenue<br><span class="fine">ouvrir pour générer</span></div>`;
    return `<div class="card" data-go="unit" data-unit="${u.unit}"><div class="card-head"><b>${esc(u.label)}</b><span class="fine">${esc(u.typology)} · trame ${fmt(u.slot[0], 1)} × ${fmt(u.slot[1], 1)}</span></div>${body}</div>`;
  }).join("") || `<div class="empty">Aucun logement placé sur ce niveau.</div>`;
}

function bindStoreyForm() {
  const s = () => storeyOf(state.view.storey);
  $("s-label").addEventListener("input", (e) => { s().label = e.target.value; projectChanged(); });
  $("s-kind").addEventListener("change", (e) => { s().kind = e.target.value; projectChanged(); });
  $("s-repeat").addEventListener("input", (e) => { s().repeat = Math.max(1, parseInt(e.target.value) || 1); projectChanged(); });
  $("s-slots").addEventListener("click", (e) => {
    const i = e.target.dataset.removeSlot;
    if (i === undefined) return;
    s().slots.splice(Number(i), 1);
    renderStoreyForm();
    projectChanged();
  });
  $("add-slot").addEventListener("click", () => {
    const uid = $("new-slot-unit").value;
    if (!uid) return;
    s().slots.push({ unit: uid });
    renderStoreyForm();
    projectChanged();
  });
}

// --- unit level --------------------------------------------------------------------

function U() { return unitOf(state.view.unit); }

function renderUnitForm() {
  const u = U();
  if (!u) return;
  $("u-label").value = u.label;
  $("u-typology").innerHTML = opts(Object.entries(meta.presets).map(([k, pr]) => [k, pr.label]), u.typology);
  $("u-width").value = u.slot.width;
  $("u-depth").value = u.slot.depth;
  const lot = P().lot;
  $("u-frame").textContent = `Généré dans sa trame, entre deux murs aveugles (voisins ou mitoyens) ; façade ${meta.edges[lot.edges[0]]}, arrière ${meta.edges[lot.edges[2]]}, profil « ${meta.profiles[P().profile]} ». Parcelle et profil se règlent au niveau immeuble.`;
  $("count").value = state.count;
  $("iterations").value = String(state.iterations);
  $("sort").checked = state.sort;
  renderRooms();
}

function renderRooms() {
  const u = U();
  const kinds = Object.entries(meta.rooms);
  const orient = [["", "—"], ...meta.orientations.map((o) => [o, o])];
  $("rooms").innerHTML = u.rooms.map((r, i) => `
    <tr>
      <td><input data-room="${i}" data-field="nom" value="${esc(r.nom)}"></td>
      <td><select data-room="${i}" data-field="kind">${opts(kinds, r.kind)}</select></td>
      <td><input data-room="${i}" data-field="surface" type="number" step="0.5" min="0.5" value="${r.surface}"></td>
      <td><select data-room="${i}" data-field="orientation">${opts(orient, r.orientation || "")}</select></td>
      <td><button class="icon" data-remove="${i}" title="Retirer" type="button">×</button></td>
    </tr>`).join("");
  renderTotal();
  const names = new Set(u.rooms.map((r) => r.nom));
  const kept = u.relations.filter((r) => names.has(r.a) && names.has(r.b)).length;
  $("relations").textContent = `${kept} relations de la typologie (liaisons, voisinages, séparations) s'appliquent.`;
}

function renderTotal() {
  const total = U().rooms.reduce((a, r) => a + (Number(r.surface) || 0), 0);
  $("total").textContent = `${fmt(total, 1)} m² utiles`;
}

function unitChanged() {
  save();
  renderStale();
  renderTree();
  clearTimeout(checkTimer);
  checkTimer = setTimeout(runCheck, 250);
  clearTimeout(summaryTimer);
  summaryTimer = setTimeout(refreshSummary, 400);
}

async function runCheck() {
  const box = $("check");
  if (!U()) return;
  try {
    const c = await (await api("/api/unit/check", { spec: unitSpec(U().id) })).json();
    const slack = c.slack >= 0 ? `marge ${fmt(c.slack, 1)} m²` : `déficit ${fmt(-c.slack, 1)} m²`;
    box.className = "check " + (c.ok ? "ok" : "bad");
    box.innerHTML = `
      <div class="budget"><span>Trame ${fmt(c.gross, 1)}</span><span>Habitable ≈ ${fmt(c.habitable, 1)}</span><span>Demandé ${fmt(c.required, 1)}</span><b>${slack}</b></div>
      <p>${esc(c.spine)}</p>`;
    $("generate").disabled = !c.ok;
  } catch (e) {
    box.className = "check bad";
    box.textContent = e.message;
    $("generate").disabled = true;
  }
}

function bindUnitForm() {
  $("u-label").addEventListener("input", (e) => { U().label = e.target.value; renderCrumbs(); unitChanged(); });
  $("u-typology").addEventListener("change", (e) => {
    const u = U(), fresh = newUnit(u.id, u.label, e.target.value);
    Object.assign(u, { typology: fresh.typology, slot: fresh.slot, rooms: fresh.rooms, relations: fresh.relations });
    renderUnitForm();
    renderCrumbs();
    unitChanged();
  });
  for (const [id, key] of [["u-width", "width"], ["u-depth", "depth"]]) {
    $(id).addEventListener("input", (e) => {
      const v = parseFloat(e.target.value);
      if (Number.isFinite(v)) { U().slot[key] = v; unitChanged(); }
    });
  }
  $("rooms").addEventListener("input", (e) => {
    const i = e.target.dataset.room;
    if (i === undefined) return;
    const field = e.target.dataset.field;
    const room = U().rooms[Number(i)];
    const old = room.nom;
    room[field] = field === "surface" ? parseFloat(e.target.value) : e.target.value;
    if (field === "nom") {
      // A renamed room keeps its relations.
      for (const r of U().relations) { if (r.a === old) r.a = room.nom; if (r.b === old) r.b = room.nom; }
    }
    renderTotal();
    unitChanged();
  });
  $("rooms").addEventListener("click", (e) => {
    const i = e.target.dataset.remove;
    if (i === undefined) return;
    U().rooms.splice(Number(i), 1);
    renderRooms();
    unitChanged();
  });
  $("add-room").addEventListener("click", () => {
    let n = U().rooms.length + 1;
    while (U().rooms.some((r) => r.nom === `Piece${n}`)) n++;
    U().rooms.push({ nom: `Piece${n}`, kind: "CHAMBRE", surface: 10, orientation: "" });
    renderRooms();
    unitChanged();
  });
  $("count").addEventListener("input", (e) => { state.count = Math.max(1, Math.min(meta.max_options, parseInt(e.target.value) || 1)); save(); });
  $("iterations").addEventListener("change", (e) => { state.iterations = Number(e.target.value); save(); });
  $("sort").addEventListener("change", (e) => { state.sort = e.target.checked; save(); renderGallery(); });
  $("generate").addEventListener("click", () => generate(false));
  $("more").addEventListener("click", () => generate(true));
  $("dl-dxf").addEventListener("click", () => download("dxf"));
  $("dl-gh").addEventListener("click", () => download("gh"));
  document.addEventListener("keydown", (e) => {
    if (state.view.level !== "unit" || e.target.matches("input, select, textarea")) return;
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const shown = ordered().filter((g) => g.status === "done" && g.payload.ok);
    const at = shown.findIndex((g) => g.id === state.selected[U().id]);
    const next = shown[(at + (e.key === "ArrowRight" ? 1 : -1) + shown.length) % shown.length];
    if (next) select(next.id);
  });
}

// --- generation --------------------------------------------------------------------

function generate(more) {
  const uid = U().id;
  const list = gallery(uid);
  const append = more && list.length;
  if (!append) {
    batches[uid]?.abort();
    batches[uid] = new AbortController();
    state.galleries[uid] = [];
    delete state.selected[uid];
  }
  batches[uid] ||= new AbortController();
  const spec = append ? list[0].spec : unitSpec(uid);
  const iterations = append ? list[0].iterations : state.iterations;
  const base = append ? Math.max(0, ...list.map((g) => g.seed)) : 0;
  const fresh = [];
  for (let i = 1; i <= state.count; i++) {
    const seed = base + i;
    fresh.push({ id: `${uid}-s${seed}-${Date.now()}`, seed, iterations, spec: JSON.parse(JSON.stringify(spec)), status: "pending", payload: null, error: null });
  }
  gallery(uid).push(...fresh);
  save();
  renderGallery();
  renderStale();
  renderDetail();
  fresh.forEach((entry) => request(uid, entry, batches[uid].signal));
}

async function request(uid, entry, signal) {
  try {
    const res = await api("/api/unit/generate", { spec: entry.spec, seed: entry.seed, iterations: entry.iterations }, signal);
    entry.payload = await res.json();
    entry.status = "done";
  } catch (e) {
    if (e.name === "AbortError") return;
    entry.status = "error";
    entry.error = e.message;
  }
  // The first valid option is retained as it arrives, unless one already was.
  if (!state.selected[uid] && entry.status === "done" && entry.payload.ok) retain(uid, entry);
  save();
  if (state.view.level === "unit" && U()?.id === uid) {
    renderGallery();
    if (state.selected[uid] === entry.id) renderDetail();
  }
  renderTree();
  if (state.view.level !== "unit") render();
}

function retain(uid, entry) {
  state.selected[uid] = entry.id;
  unitOf(uid).chosen = { seed: entry.seed, iterations: entry.iterations };
}

// --- unit gallery ------------------------------------------------------------------

function ordered() {
  const list = [...gallery(U().id)];
  if (state.sort) {
    const score = (g) => (g.status === "done" && g.payload.ok ? g.payload.scores.globale : -1);
    list.sort((a, b) => score(b) - score(a));
  }
  return list;
}

function renderGallery() {
  if (!U()) return;
  const all = gallery(U().id);
  const list = ordered();
  const done = all.filter((g) => g.status === "done");
  const valid = done.filter((g) => g.payload.ok);
  const pending = all.filter((g) => g.status === "pending").length;
  $("gallery-title").textContent = all.length
    ? `${U().label} — ${valid.length} plan${valid.length > 1 ? "s" : ""} valide${valid.length > 1 ? "s" : ""} sur ${done.length}${pending ? ` · ${pending} en cours` : ""}`
    : `${U().label} — options`;
  const running = Object.values(state.galleries).flat().filter((g) => g.status === "pending").length;
  $("status").textContent = running ? `Génération… ${running} en cours` : "";
  $("gallery").innerHTML = list.length
    ? list.map(card).join("")
    : `<div class="empty">Réglez le programme de ce logement type, puis <b>Générer</b>. Chaque option est un plan complet : murs, portes, fenêtres, gaines. L'option retenue est celle que le niveau et l'immeuble affichent.</div>`;
  for (const el of $("gallery").querySelectorAll(".card[data-id]")) el.addEventListener("click", () => select(el.dataset.id));
}

function card(g) {
  const head = `<div class="card-head"><b>Graine ${g.seed}</b>`;
  if (g.status === "pending") {
    return `<div class="card pending">${head}<span class="tag">en cours</span></div><div class="thumb"><div class="spinner"></div></div></div>`;
  }
  if (g.status === "error") {
    return `<div class="card refused">${head}<span class="tag bad">erreur</span></div><p class="why">${esc(g.error)}</p></div>`;
  }
  const p = g.payload;
  if (!p.ok) {
    return `<div class="card refused">${head}<span class="tag bad">refusé</span></div><div class="thumb none">Aucun plan valide</div><p class="why">${esc(p.refusal)}</p><p class="fine">${esc(p.stats.explain)} · ${fmt(p.elapsed, 1)} s</p></div>`;
  }
  const warn = p.openings.errors.length;
  const sel = g.id === state.selected[U().id] ? " selected" : "";
  return `<div class="card${sel}" data-id="${g.id}">${head}<span class="score">${Math.round(p.scores.globale * 100)}</span></div>
    <div class="thumb">${planSVG(p.document, meta.palette, { id: g.id })}</div>
    ${bars(p.scores, true)}
    <div class="facts"><span>${fmt(p.emprise[0])} × ${fmt(p.emprise[1])} m</span><span>${fmt(p.surface_utile, 1)} m²</span><span>écart ≤ ${pct(p.area_error)}</span></div>
    <div class="flags">${sel ? '<span class="tag sel">retenue</span>' : ""}${p.shrunk ? '<span class="tag bad">pièces réduites</span>' : ""}${warn ? `<span class="tag warn">${warn} réserve${warn > 1 ? "s" : ""}</span>` : '<span class="tag ok">ouvertures OK</span>'}<span class="fine">${fmt(p.elapsed, 1)} s</span></div>
  </div>`;
}

function bars(scores, compact) {
  return `<div class="bars${compact ? " compact" : ""}">${Object.entries(SCORE_FR).map(([k, l]) =>
    `<div class="bar"><span>${l}</span><i><em style="width:${Math.round(scores[k] * 100)}%"></em></i><b>${Math.round(scores[k] * 100)}</b></div>`).join("")}</div>`;
}

function select(id) {
  const uid = U().id;
  const entry = gallery(uid).find((g) => g.id === id);
  if (!entry) return;
  retain(uid, entry);
  save();
  renderGallery();
  renderDetail();
  renderTree();
  clearTimeout(summaryTimer);
  summaryTimer = setTimeout(refreshSummary, 100);
}

function renderDetail() {
  const g = U() ? retained(U().id) : null;
  $("detail").hidden = !g;
  if (!g) return;
  const p = g.payload;
  $("sheet").innerHTML = planSVG(p.document, meta.palette, { detail: true, id: "detail" });
  $("detail-title").textContent = `${U().label} · graine ${g.seed} — note ${Math.round(p.scores.globale * 100)}/100`;
  $("detail-scores").innerHTML = bars(p.scores, false);
  $("detail-note").textContent = p.note;
  $("detail-warnings").innerHTML = p.openings.errors.map((e) => `<li>${esc(e)}</li>`).join("")
    || `<li class="ok">${p.openings.doors} portes et ${p.openings.windows} fenêtres placées, aucune réserve.</li>`;
  const rows = p.rooms.map((r) => `
    <tr><td><i class="swatch" style="background:${meta.palette[r.kind] || "#ccc"}"></i>${esc(r.nom)}</td>
    <td>${esc(meta.rooms[r.kind] || r.kind)}</td>
    <td class="num">${r.asked != null ? fmt(r.asked) : "—"}</td>
    <td class="num"><b>${fmt(r.net)}</b></td>
    <td class="num">${fmt(r.net_w)} × ${fmt(r.net_h)}</td>
    <td class="num">${r.error == null ? "<span class='fine'>résultat</span>" : pct(r.error)}</td></tr>`).join("");
  $("detail-rooms").innerHTML = `<thead><tr><th>Pièce</th><th>Type</th><th>Demandé m²</th><th>Net m²</th><th>Dim. nettes</th><th>Écart</th></tr></thead>
    <tbody>${rows}</tbody>
    <tfoot><tr><td colspan="3">Surface utile totale</td><td class="num"><b>${fmt(p.surface_utile)}</b></td><td class="num">${fmt(p.emprise[0])} × ${fmt(p.emprise[1])}</td><td></td></tr></tfoot>`;
  $("detail-stats").textContent = `Recherche : ${p.stats.explain} — ${fmt(p.elapsed, 1)} s, ${p.iterations} itérations.`;
}

function renderStale() {
  const first = U() && gallery(U().id)[0];
  $("stale").hidden = !first || JSON.stringify(first.spec) === JSON.stringify(unitSpec(U().id));
}

async function download(format) {
  const g = retained(U().id);
  if (!g) return;
  const button = $(format === "dxf" ? "dl-dxf" : "dl-gh");
  button.disabled = true;
  try {
    const res = await api("/api/unit/export", { spec: g.spec, seed: g.seed, iterations: g.iterations, format });
    const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || `plan.${format}`;
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) {
    $("status").textContent = e.message;
  } finally {
    button.disabled = false;
  }
}

// --- start -------------------------------------------------------------------------

async function start() {
  meta = await (await api("/api/meta")).json();
  load();
  if (!state.project) state.project = await (await api("/api/project/default")).json();
  bindBuildingForm();
  bindStoreyForm();
  bindUnitForm();
  await refreshSummary();
  render();
  // Options still pending when the page was left are asked for again: same seed, same plan.
  for (const [uid, list] of Object.entries(state.galleries)) {
    if (!unitOf(uid)) continue;
    batches[uid] = new AbortController();
    for (const g of list) if (g.status === "pending") request(uid, g, batches[uid].signal);
  }
}

start().catch((e) => { $("status").textContent = `Démarrage impossible : ${e.message}`; });
