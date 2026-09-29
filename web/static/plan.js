// PLANFGEN — the plan, drawn from the bridge document (`to_gh_json` + solids).
//
// Walls are poché: the solids the server cut the openings out of, filled black.
// Rooms are filled on their NET outline, so a coloured area is the habitable
// area in its stamp. Everything is in metres; y is flipped so north is up.

const NS = "http://www.w3.org/2000/svg";
const INK = "#1d1d1b";
const RULE = "#8b8378";
const DIM = "#7a4a1e";

const EDGE_FR = { STREET: "RUE", COURT: "COUR", GARDEN: "JARDIN", MITOYEN: "MITOYEN", RETRAIT: "RETRAIT" };

function fmt(v, places = 2) {
  return v.toFixed(places).replace(".", ",");
}

function esc(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function bounds(points) {
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const [x, y] of points) {
    minx = Math.min(minx, x); miny = Math.min(miny, y);
    maxx = Math.max(maxx, x); maxy = Math.max(maxy, y);
  }
  return { minx, miny, maxx, maxy };
}

// Dimension chains on the wall axes, as the DXF does, but around the BUILDING:
// the ticks on a side are the walls that meet that facade.
export function chains(doc) {
  const walls = doc.walls;
  const all = walls.flatMap((w) => [w.p0, w.p1]);
  const b = bounds(all);
  const eps = 1e-6;
  const out = [];
  const sides = [
    { axis: "x", at: b.miny, out: -1 },
    { axis: "x", at: b.maxy, out: +1 },
    { axis: "y", at: b.minx, out: -1 },
    { axis: "y", at: b.maxx, out: +1 },
  ];
  for (const side of sides) {
    const ticks = side.axis === "x" ? [b.minx, b.maxx] : [b.miny, b.maxy];
    for (const w of walls) {
      const vertical = Math.abs(w.p0[0] - w.p1[0]) < eps;
      if (side.axis === "x" && vertical) {
        const lo = Math.min(w.p0[1], w.p1[1]), hi = Math.max(w.p0[1], w.p1[1]);
        if (lo - eps <= side.at && side.at <= hi + eps) ticks.push(w.p0[0]);
      } else if (side.axis === "y" && !vertical) {
        const lo = Math.min(w.p0[0], w.p1[0]), hi = Math.max(w.p0[0], w.p1[0]);
        if (lo - eps <= side.at && side.at <= hi + eps) ticks.push(w.p0[1]);
      }
    }
    ticks.sort((a, c) => a - c);
    const merged = ticks.filter((t, i) => i === 0 || t - ticks[i - 1] > 1e-4);
    out.push({ ...side, ticks: merged });
  }
  return { chains: out, bounds: b };
}

// Render the plan into an SVG string.
//   opts.detail   true for the large drawing: dimensions, edge names, dims in stamps
export function planSVG(doc, palette, opts = {}) {
  const detail = !!opts.detail;
  const parcel = doc.parcel.outline;
  const pb = bounds(parcel);
  const pad = detail ? 2.4 : 0.6;
  const W = pb.maxx - pb.minx + 2 * pad;
  const H = pb.maxy - pb.miny + 2 * pad;
  const X = (x) => x - pb.minx + pad;
  const Y = (y) => pb.maxy - y + pad;
  const pts = (ring) => ring.map(([x, y]) => `${X(x).toFixed(3)},${Y(y).toFixed(3)}`).join(" ");
  const path = (rings) => rings.map((r) => "M" + r.map(([x, y]) => `${X(x).toFixed(3)} ${Y(y).toFixed(3)}`).join("L") + "Z").join("");
  const hair = 'vector-effect="non-scaling-stroke"';

  const s = [];
  s.push(`<svg xmlns="${NS}" viewBox="0 0 ${W.toFixed(3)} ${H.toFixed(3)}" class="plan${detail ? " plan-detail" : ""}" preserveAspectRatio="xMidYMid meet">`);
  s.push(`<defs><pattern id="hatch${opts.id || ""}" width="0.35" height="0.35" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="0.35" stroke="${RULE}" stroke-width="0.02" opacity="0.45"/></pattern></defs>`);

  // The lot, with what is left unbuilt hatched: the footprint is sized to the programme.
  s.push(`<polygon points="${pts(parcel)}" fill="url(#hatch${opts.id || ""})" stroke="${RULE}" stroke-width="1" stroke-dasharray="6 4" ${hair}/>`);
  if (doc.footprint) {
    const [fx, fy, fw, fh] = doc.footprint;
    s.push(`<rect x="${X(fx)}" y="${Y(fy + fh)}" width="${fw}" height="${fh}" fill="#fbfaf7"/>`);
  }

  s.push(...unitBody(doc, palette, X, Y, detail));

  if (detail) {
    s.push(...dimensions(doc, X, Y));
    s.push(...edgeNames(doc, X, Y, pb));
  }
  s.push(...northArrow(doc.parcel.north, W, H, detail));
  if (detail) s.push(...scaleBar(pad, H));
  s.push("</svg>");
  return s.join("");
}

// One flat's rooms, walls, shafts, openings and stamps, through the caller's
// (X, Y) — so a storey can place several flats in one drawing.
function unitBody(doc, palette, X, Y, detail) {
  const pts = (ring) => ring.map(([x, y]) => `${X(x).toFixed(3)},${Y(y).toFixed(3)}`).join(" ");
  const path = (rings) => rings.map((r) => "M" + r.map(([x, y]) => `${X(x).toFixed(3)} ${Y(y).toFixed(3)}`).join("L") + "Z").join("");
  const hair = 'vector-effect="non-scaling-stroke"';
  const s = [];

  // Rooms, on their net outline.
  for (const sp of doc.spaces) {
    const colour = palette[sp.kind] || "#cbd5e1";
    s.push(`<polygon points="${pts(sp.net_outline)}" fill="${colour}" fill-opacity="${detail ? 0.16 : 0.22}"/>`);
  }

  // Walls: poché.
  s.push(`<path d="${(doc.solids || []).map(path).join("")}" fill="${INK}" fill-rule="evenodd"/>`);

  // Shafts: a box with a cross, as drawn on a plan. Drawn over the poché: the
  // engine may place a gaine in the thickness of a wall, and it must still show.
  for (const sh of doc.shafts || []) {
    const x = X(sh.x), y = Y(sh.y + sh.h);
    s.push(`<rect x="${x}" y="${y}" width="${sh.w}" height="${sh.h}" fill="#fff" stroke="${INK}" stroke-width="0.8" ${hair}/>`);
    s.push(`<path d="M${x} ${y}l${sh.w} ${sh.h}M${x + sh.w} ${y}l${-sh.w} ${sh.h}" stroke="${INK}" stroke-width="0.6" fill="none" ${hair}/>`);
  }

  // Windows: three lines across the gap (two faces and the glazing).
  for (const win of doc.openings.windows) {
    const w = doc.walls[win.wall];
    if (!w) continue;
    const g = frame(w, win.span);
    const half = w.thickness / 2;
    const lines = [-half, 0, half].map((o) => {
      const a = [g.ax + g.nx * o, g.ay + g.ny * o], b = [g.bx + g.nx * o, g.by + g.ny * o];
      return `M${X(a[0])} ${Y(a[1])}L${X(b[0])} ${Y(b[1])}`;
    });
    const caps = [[g.ax, g.ay], [g.bx, g.by]].map(([cx, cy]) =>
      `M${X(cx + g.nx * half)} ${Y(cy + g.ny * half)}L${X(cx - g.nx * half)} ${Y(cy - g.ny * half)}`);
    s.push(`<path d="${lines.join("")}${caps.join("")}" stroke="${INK}" stroke-width="${detail ? 0.9 : 0.6}" fill="none" ${hair}/>`);
  }

  // Doors: the leaf, open at 90 degrees, and its swing.
  for (const door of doc.openings.doors) {
    const w = doc.walls[door.wall];
    if (!w) continue;
    const g = frame(w, door.span);
    const high = door.hinge === "high";
    const [hx, hy] = high ? [g.bx, g.by] : [g.ax, g.ay];
    const [ex, ey] = high ? [g.ax, g.ay] : [g.bx, g.by];
    // Which side it swings to, as the DXF reads it: +y for a horizontal wall, +x for a vertical one.
    const sgn = door.swing_side >= 0 ? 1 : -1;
    const [px, py] = g.horizontal ? [0, sgn] : [sgn, 0];
    const leaf = door.leaf;
    const lx = hx + px * leaf, ly = hy + py * leaf;
    // The arc goes from the open leaf's end to the closed position; its sweep follows the handedness.
    const cross = (lx - hx) * (ey - hy) - (ly - hy) * (ex - hx);
    // Counter-clockwise in plan (y up) is clockwise on screen (y down), which is SVG's sweep 1.
    const sweep = cross > 0 ? 1 : 0;
    s.push(`<path d="M${X(hx)} ${Y(hy)}L${X(lx)} ${Y(ly)}" stroke="${INK}" stroke-width="${detail ? 1.4 : 0.9}" ${hair}/>`);
    s.push(`<path d="M${X(lx)} ${Y(ly)}A${leaf} ${leaf} 0 0 ${sweep} ${X(ex)} ${Y(ey)}" stroke="${INK}" stroke-width="0.6" stroke-dasharray="${detail ? "3 2" : "none"}" fill="none" ${hair}/>`);
  }

  // Stamps: name, net area, net dimensions — only what fits.
  for (const sp of doc.spaces) {
    const nb = bounds(sp.net_outline);
    const cx = X((nb.minx + nb.maxx) / 2), cy = Y((nb.miny + nb.maxy) / 2);
    const w = nb.maxx - nb.minx, h = nb.maxy - nb.miny;
    const rotate = h > w * 1.6 && w < 1.8;
    const across = rotate ? h : w, along = rotate ? w : h;
    const size = detail ? 0.30 : 0.42;
    const lines = [[esc(sp.nom), size, 600]];
    if (detail || along > 1.6) lines.push([`${fmt(sp.surface_utile)} m²`, size * 0.82, 400]);
    if (detail && along > 1.4) lines.push([`${fmt(sp.net_w)} × ${fmt(sp.net_h)}`, size * 0.7, 400]);
    const maxChars = Math.max(...lines.map((l) => l[0].length));
    if (across < maxChars * size * 0.5 || along < size * 1.2) {
      if (across < esc(sp.nom).length * size * 0.45) continue;
      lines.splice(1);
    }
    const lh = size * 1.25;
    const top = cy - ((lines.length - 1) * lh) / 2;
    const t = rotate ? ` transform="rotate(-90 ${cx} ${cy})"` : "";
    s.push(`<g text-anchor="middle" dominant-baseline="middle" fill="${INK}"${t}>`);
    lines.forEach(([text, fs, weight], i) => {
      s.push(`<text x="${cx}" y="${top + i * lh}" font-size="${fs}" font-weight="${weight}"${i ? ' opacity="0.75"' : ""}>${text}</text>`);
    });
    s.push("</g>");
  }
  return s;
}

// A storey, as far as it can be drawn before the engine composes a plate: the
// lot, each flat's slot along the street with its retained plan inside, and the
// frontage left over — where the core and landing will go — marked as such.
//   storey   one entry of /api/building/summary's `storeys`
//   docs     {unitId: document of the retained option, or null}
export function plateSVG(storey, lotDims, docs, palette, opts = {}) {
  const [LW, LD] = lotDims;
  const pad = opts.detail ? 1.6 : 0.5;
  const W = Math.max(LW, storey.frontage) + 2 * pad, H = LD + 2 * pad + (opts.detail ? 0.8 : 0);
  const X = (x) => x + pad, Y = (y) => LD - y + pad;
  const hair = 'vector-effect="non-scaling-stroke"';
  const id = opts.id || "plate";
  const s = [];
  s.push(`<svg xmlns="${NS}" viewBox="0 0 ${W.toFixed(3)} ${H.toFixed(3)}" class="plan plate" preserveAspectRatio="xMidYMid meet">`);
  s.push(`<defs><pattern id="core${id}" width="0.5" height="0.5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="0.5" stroke="#b5542c" stroke-width="0.05" opacity="0.5"/></pattern></defs>`);
  s.push(`<rect x="${X(0)}" y="${Y(LD)}" width="${LW}" height="${LD}" fill="#fff" stroke="${RULE}" stroke-width="1" stroke-dasharray="6 4" ${hair}/>`);

  // Slots left to right; the free frontage after the first flat, where a core usually sits.
  const units = storey.units;
  const free = storey.free;
  const layout = [];
  let x = 0;
  units.forEach((u, i) => {
    layout.push({ kind: "unit", u, x });
    x += u.slot[0];
    if (i === 0 && free > 0.05) { layout.push({ kind: "core", x, w: free }); x += free; }
  });
  if (!units.length && free > 0) layout.push({ kind: "core", x: 0, w: free });

  for (const item of layout) {
    if (item.kind === "core") {
      const size = Math.min(0.5, item.w / 6);
      s.push(`<rect x="${X(item.x)}" y="${Y(LD)}" width="${item.w}" height="${LD}" fill="url(#core${id})" stroke="#b5542c" stroke-width="1" ${hair}/>`);
      s.push(`<text x="${X(item.x + item.w / 2)}" y="${Y(LD / 2)}" font-size="${size}" fill="#b5542c" text-anchor="middle" transform="rotate(-90 ${X(item.x + item.w / 2)} ${Y(LD / 2)})">Noyau + palier — ${fmt(item.w)} m (S19)</text>`);
      continue;
    }
    const { u } = item;
    const [sw, sd] = u.slot;
    const doc = docs[u.unit];
    s.push(`<rect x="${X(item.x)}" y="${Y(sd)}" width="${sw}" height="${sd}" fill="${doc ? "#fbfaf7" : "#f3f1ec"}" stroke="${INK}" stroke-width="0.8" stroke-dasharray="${doc ? "none" : "4 3"}" ${hair}/>`);
    if (doc) {
      const ox = item.x;
      s.push(...unitBody(doc, palette, (px) => X(px + ox), Y, false));
    } else {
      s.push(`<text x="${X(item.x + sw / 2)}" y="${Y(sd / 2)}" font-size="${Math.min(0.9, sw / 8)}" text-anchor="middle" fill="${RULE}">${esc(u.label)} — à générer</text>`);
    }
    if (opts.detail) {
      s.push(`<text x="${X(item.x + sw / 2)}" y="${Y(0) + 0.6}" font-size="0.4" font-weight="700" text-anchor="middle" fill="${INK}">${esc(u.label)} · ${esc(u.typology)} · ${fmt(sw)} m</text>`);
    }
  }
  if (free < -0.05) {
    s.push(`<rect x="${X(LW)}" y="${Y(LD)}" width="${-free}" height="${LD}" fill="#b3261e" fill-opacity="0.12" stroke="#b3261e" stroke-width="1" ${hair}/>`);
  }
  s.push("</svg>");
  return s.join("");
}

// A wall's local frame at an opening: the two ends of the span and the wall's normal.
function frame(w, span) {
  const [x0, y0] = w.p0, [x1, y1] = w.p1;
  const len = Math.hypot(x1 - x0, y1 - y0) || 1;
  const ux = (x1 - x0) / len, uy = (y1 - y0) / len;
  return {
    ax: x0 + ux * span[0], ay: y0 + uy * span[0],
    bx: x0 + ux * span[1], by: y0 + uy * span[1],
    nx: -uy, ny: ux,
    horizontal: Math.abs(uy) < 1e-9,
  };
}

function dimensions(doc, X, Y) {
  const { chains: cs } = chains(doc);
  const out = [`<g class="dims" stroke="${DIM}" fill="${DIM}" font-size="0.24" text-anchor="middle">`];
  const OFF = 0.9;
  for (const c of cs) {
    const pos = c.at + c.out * OFF;
    const tick = 0.12;
    const segs = [];
    const labels = [];
    const ends = [c.ticks[0], c.ticks[c.ticks.length - 1]];
    const tiers = c.ticks.length > 2 ? [[c.ticks, pos], [ends, pos + c.out * 0.6]] : [[c.ticks, pos]];
    for (const [ticks, p] of tiers) {
      for (let i = 0; i < ticks.length; i++) {
        const t = ticks[i];
        if (c.axis === "x") {
          segs.push(`M${X(t) - tick} ${Y(p) + tick}L${X(t) + tick} ${Y(p) - tick}`);
          segs.push(`M${X(t)} ${Y(c.at)}L${X(t)} ${Y(p + c.out * 0.15)}`);
        } else {
          segs.push(`M${X(p) - tick} ${Y(t) + tick}L${X(p) + tick} ${Y(t) - tick}`);
          segs.push(`M${X(c.at)} ${Y(t)}L${X(p + c.out * 0.15)} ${Y(t)}`);
        }
        if (i === 0) continue;
        const a = ticks[i - 1], len = t - a, mid = (a + t) / 2;
        if (len < 0.05) continue;
        if (c.axis === "x") {
          segs.push(`M${X(a)} ${Y(p)}L${X(t)} ${Y(p)}`);
          labels.push(`<text x="${X(mid)}" y="${Y(p) - 0.1}" stroke="none">${fmt(len)}</text>`);
        } else {
          segs.push(`M${X(p)} ${Y(a)}L${X(p)} ${Y(t)}`);
          labels.push(`<text x="${X(p) - 0.1}" y="${Y(mid)}" stroke="none" transform="rotate(-90 ${X(p) - 0.1} ${Y(mid)})">${fmt(len)}</text>`);
        }
      }
    }
    out.push(`<path d="${segs.join("")}" stroke-width="0.7" vector-effect="non-scaling-stroke" fill="none"/>`);
    out.push(...labels);
  }
  out.push("</g>");
  return out;
}

function edgeNames(doc, X, Y, pb) {
  const ring = doc.parcel.outline;
  const out = [`<g font-size="0.26" fill="${RULE}" text-anchor="middle" letter-spacing="0.06">`];
  const n = ring.length;
  for (const e of doc.parcel.edges) {
    const [x0, y0] = ring[e.index], [x1, y1] = ring[(e.index + 1) % n];
    const mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
    const horizontal = Math.abs(y1 - y0) < 1e-9;
    const cxp = (pb.minx + pb.maxx) / 2, cyp = (pb.miny + pb.maxy) / 2;
    const ox = horizontal ? 0 : Math.sign(mx - cxp) * 2.05;
    const oy = horizontal ? Math.sign(my - cyp) * 2.05 : 0;
    const entry = e.index === doc.parcel.entry_edge ? " · ENTRÉE" : "";
    const label = (EDGE_FR[e.kind] || e.kind) + entry;
    const x = X(mx + ox), y = Y(my + oy);
    const t = horizontal ? "" : ` transform="rotate(-90 ${x} ${y})"`;
    const weight = entry ? ' font-weight="700" fill="#1d1d1b"' : "";
    out.push(`<text x="${x}" y="${y}" dominant-baseline="middle"${t}${weight}>${label}</text>`);
  }
  out.push("</g>");
  return out;
}

function northArrow(north, W, H, detail) {
  const r = detail ? 0.55 : 0.45;
  const cx = W - r - 0.25, cy = r + 0.25;
  const dx = Math.sin(north), dy = -Math.cos(north);
  const px = -dy, py = dx;
  const tip = [cx + dx * r, cy + dy * r], tail = [cx - dx * r * 0.7, cy - dy * r * 0.7];
  const mid = [cx - dx * r * 0.25, cy - dy * r * 0.25];
  const left = [tail[0] + px * r * 0.45, tail[1] + py * r * 0.45];
  const right = [tail[0] - px * r * 0.45, tail[1] - py * r * 0.45];
  const p = [tip, left, mid, right].map(([x, y]) => `${x.toFixed(3)},${y.toFixed(3)}`).join(" ");
  return [
    `<g class="north"><circle cx="${cx}" cy="${cy}" r="${r * 1.05}" fill="#fbfaf7" stroke="${RULE}" stroke-width="0.6" vector-effect="non-scaling-stroke"/>`,
    `<polygon points="${p}" fill="${INK}"/>`,
    `<text x="${cx}" y="${cy + r * 1.05 + 0.32}" font-size="0.3" font-weight="700" text-anchor="middle" fill="${INK}">N</text></g>`,
  ];
}

function scaleBar(pad, H) {
  const x = pad * 0.35, y = H - 0.35;
  const segs = [0, 1, 2, 3, 4].map((i) =>
    `<rect x="${x + i}" y="${y - 0.12}" width="1" height="0.12" fill="${i % 2 ? "#fff" : INK}" stroke="${INK}" stroke-width="0.5" vector-effect="non-scaling-stroke"/>`);
  return [
    `<g class="scale">${segs.join("")}`,
    `<text x="${x}" y="${y - 0.22}" font-size="0.22" fill="${RULE}">0</text>`,
    `<text x="${x + 5}" y="${y - 0.22}" font-size="0.22" fill="${RULE}" text-anchor="middle">5 m</text></g>`,
  ];
}
