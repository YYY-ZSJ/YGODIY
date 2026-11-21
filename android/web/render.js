import { CALLS, MT, frameName } from "./project.js";
const WIDTH = 1626,
  HEIGHT = 2370,
  FIELD_WIDTH = 1696;
const cache = new Map();
function image(path) {
  if (!path) return Promise.resolve(null);
  if (!cache.has(path)) {
    const load = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(Error("卡面图片读取失败"));
      img.src = path;
    });
    cache.set(path, load);
    if (cache.size > 22) cache.delete(cache.keys().next().value);
    load.catch(() => cache.delete(path));
  }
  return cache.get(path);
}
function cover(ctx, img, box, s) {
  const [x, y, w, h] = box;
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();
  if (img) {
    const scale =
      (s.fit === "contain" ? Math.min : Math.max)(w / img.width, h / img.height) *
      Math.max(1, Number(s.zoom) || 1);
    const width = img.width * scale,
      height = img.height * scale;
    ctx.drawImage(img, x + ((w - width) * s.x) / 100, y + ((h - height) * s.y) / 100, width, height);
  } else {
    ctx.fillStyle = "#dce6dc";
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = "#b0c5b7";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(x + w * 0.22, y + h * 0.72);
    ctx.lineTo(x + w * 0.44, y + h * 0.43);
    ctx.lineTo(x + w * 0.59, y + h * 0.58);
    ctx.lineTo(x + w * 0.69, y + h * 0.49);
    ctx.lineTo(x + w * 0.83, y + h * 0.72);
    ctx.stroke();
  }
  ctx.restore();
}
function text(ctx, content, x, y, size, width, color = "#191814", align = "left", weight = "normal") {
  ctx.font = weight + " " + size + "px serif";
  ctx.fillStyle = color;
  ctx.textAlign = align;
  ctx.textBaseline = "top";
  ctx.fillText(String(content ?? ""), x, y, width);
}
function body(ctx, content, x, y, width, height, start = 51) {
  const chars = String(content || "")
    .replace(/\r/g, "")
    .split("\n");
  let lines,
    size = start;
  for (; size >= 16; size -= 2) {
    ctx.font = size + "px serif";
    lines = [];
    for (const p of chars) {
      let row = "",
        used = 0;
      for (const c of p) {
        const advance = ctx.measureText(c).width;
        if (row && used + advance > width) {
          lines.push(row);
          row = "";
          used = 0;
        }
        row += c;
        used += advance;
      }
      lines.push(row);
    }
    if (lines.length * size * 1.18 <= height) break;
  }
  size = Math.max(size, 16);
  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, width, height);
  ctx.clip();
  lines.forEach((line, i) => text(ctx, line, x, y + i * size * 1.18, size, width));
  ctx.restore();
}
function renderManga(ctx, c, art) {
  const d = c.data,
    s = c.style;
  ctx.fillStyle = "#f4efe2";
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
  ctx.strokeStyle = "#20201d";
  ctx.lineWidth = 23;
  ctx.strokeRect(52, 53, WIDTH - 104, HEIGHT - 106);
  text(ctx, d.name, 112, 125, 110, 1400, s.ink || "#161616");
  ctx.save();
  if (s.mono) ctx.filter = "grayscale(100%)";
  cover(ctx, art, [112, 306, 1400, 1350], s);
  ctx.restore();
  ctx.lineWidth = 10;
  ctx.strokeRect(112, 306, 1400, 1350);
  body(ctx, d.effect_text, 116, 1715, 1400, 385, 59 + s.size);
  text(
    ctx,
    d.card_type === 0 ? "ATK / " + d.ATK + "    DEF / " + d.DEF : frameName(d),
    1495,
    2152,
    70,
    1340,
    "#151515",
    "right",
    "bold"
  );
}
function arrows(ctx, c, box) {
  const [x, y, w, h] = box,
    directions = [
      [-1, -1],
      [0, -1],
      [1, -1],
      [-1, 0],
      [1, 0],
      [-1, 1],
      [0, 1],
      [1, 1]
    ];
  directions.forEach(([dx, dy], i) => {
    if (!c.data.link_status[i]) return;
    ctx.save();
    ctx.translate(x + (w * (dx + 1)) / 2, y + (h * (dy + 1)) / 2);
    ctx.rotate(Math.atan2(dy, dx));
    ctx.fillStyle = "#cc4134";
    ctx.strokeStyle = "#f7dfb2";
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.moveTo(42, 0);
    ctx.lineTo(-26, -34);
    ctx.lineTo(-26, 34);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    ctx.restore();
  });
}
export async function paint(canvas, c, assets) {
  const s = c.style,
    d = c.data,
    mode = s.mode,
    key = frameName(d),
    old = assets.past[s.series] || assets.past["3"];
  const frames =
    mode === "past" ? old.frames : mode === "rd" ? assets.rd : s.template === "new" ? assets.new : assets.ocg;
  const path =
    mode === "back"
      ? assets.back[s.back]
      : mode === "field"
        ? assets.field[s.field]
        : mode === "manga"
          ? null
          : frames[key] || frames[key.replace("灵摆", "")] || frames["效果"];
  const attr = d.card_type === 0 ? d.attribute : d.card_type === 1 ? "魔" : mode === "rd" ? "罠" : "陷";
  const [bg, art, attribute, star] = await Promise.all([
    image(path),
    image(c.art ? "art/" + c.art : s.demo ? assets.demo : null),
    image((mode === "rd" ? assets.rdAttr : assets.attr)[attr]),
    image(d.call_way === 5 ? assets.rank : assets.star)
  ]);
  const w = mode === "field" ? FIELD_WIDTH : WIDTH;
  canvas.width = w;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#f3eee2";
  ctx.fillRect(0, 0, w, HEIGHT);
  if (mode === "manga") renderManga(ctx, c, art);
  else if (mode === "field" || mode === "back") {
    if (bg) ctx.drawImage(bg, 0, 0, w, HEIGHT);
    if (art && (!s.demo || mode === "field"))
      cover(ctx, art, mode === "field" ? [117, 110, 1468, 2149] : [220, 420, 1186, 1530], s);
    if (mode === "field") {
      ctx.fillStyle = "#18302ac9";
      ctx.fillRect(117, 1990, 1468, 269);
      text(ctx, d.name, w / 2, 2070, 82, 1410, "#fff", "center");
    }
  } else {
    const rd = mode === "rd",
      past = mode === "past",
      pend = key.endsWith("灵摆");
    const box = rd
      ? [81, 234, 1463, 1468]
      : past
        ? [old.card_x, old.card_y, old.card_img_size_w, old.card_img_size_h]
        : pend
          ? [111, 426, 1403, 1790]
          : [199, 439, 1228, 1228];
    cover(ctx, art, box, s);
    if (bg) ctx.drawImage(bg, 0, 0, WIDTH, HEIGHT);
    const bright = rd || ["超量", "连接", "魔法卡", "陷阱卡", "暗黑同调"].includes(key);
    text(
      ctx,
      d.name,
      s.align === "right" ? 1400 : s.align === "center" ? 760 : rd ? 83 : 122,
      past && Number(s.series) < 4 ? 127 : 97,
      101,
      1284,
      s.ink || (bright ? "#fff9e8" : "#17150f"),
      s.align || "left"
    );
    if (attribute) ctx.drawImage(attribute, rd ? 1355 : 1371, 95, 145, 145);
    const level = d.call_way === 5 ? d.rank : d.level;
    if (d.card_type === 0 && d.call_way !== 7) {
      if (rd) text(ctx, "★ " + level, 1495, 265, 84, 295, "#fff", "right", "bold");
      else
        for (let n = 0; n < Math.min(13, Math.max(0, level)); n++) {
          const a = Math.min(96, 1280 / Math.max(1, level));
          if (star)
            ctx.drawImage(star, d.call_way === 5 ? 181 + n * a : 1353 - n * a, past ? old.level_y : 292, a, a);
        }
    }
    if (d.card_type === 0 && d.call_way === 7) arrows(ctx, c, box);
    const race = s.raceText || assets.races[d.race] || "";
    const type =
      d.card_type === 0
        ? "【" + race + "／" + key + "】"
        : "【" + (d.mt_type ? MT[d.mt_type] : "通常") + key + "】";
    const ty = rd ? 1708 : past ? (d.card_type === 0 ? old.rect_pos_monster_y : old.rect_pos_mt_y) - 65 : 1771;
    text(ctx, type, rd ? 88 : 126, ty, rd ? 55 : 54, 1350, "#211e1a", "left", "bold");
    const y = rd ? 1840 : ty + 66,
      bottom = rd ? 2194 : d.card_type === 0 ? 2154 : 2217;
    body(ctx, d.effect_text, rd ? 95 : 132, y, rd ? 1440 : 1362, bottom - y, 50 + s.size);
    if (pend) {
      body(ctx, d.lb_text, 265, 1496, 1090, 208, 41 + s.size);
      text(ctx, d.lb_level, 154, 1554, 72, 100);
      text(ctx, d.lb_level, 1393, 1554, 72, 100);
    }
    if (d.card_type === 0) {
      const stats =
        d.call_way === 7
          ? "ATK / " + d.ATK + "   LINK–" + d.link_status.filter(Boolean).length
          : "ATK / " + d.ATK + "    DEF / " + d.DEF;
      text(
        ctx,
        stats,
        rd ? 1500 : 1480,
        rd ? 1560 : 2163,
        rd ? 90 : 60,
        rd ? 1250 : 1090,
        rd ? "white" : "#161515",
        "right",
        "bold"
      );
    }
    text(ctx, d.cardpack, 1460, rd ? 2240 : 1698, 36, 800, rd ? "white" : "#191814", "right");
    text(ctx, d.cardpass, 115, 2256, 39, 400, rd ? "white" : "#191814");
  }
  if (s.copyright)
    text(ctx, s.copyright, w - 122, 2260, 36, 990, mode === "rd" || mode === "back" ? "#fff" : "#222", "right");
}
export function printBleed(src) {
  const bleed = Math.round((src.height * 3) / 86),
    w = src.width,
    h = src.height;
  const out = document.createElement("canvas");
  out.width = w + 2 * bleed;
  out.height = h + 2 * bleed;
  const ctx = out.getContext("2d");
  for (const dx of [-1, 0, 1])
    for (const dy of [-1, 0, 1]) {
      ctx.save();
      ctx.translate(bleed + (dx === 1 ? 2 * w : 0), bleed + (dy === 1 ? 2 * h : 0));
      ctx.scale(dx ? -1 : 1, dy ? -1 : 1);
      ctx.drawImage(src, 0, 0);
      ctx.restore();
    }
  for (const [color, line] of [
    ["white", 8],
    ["black", 3]
  ]) {
    ctx.strokeStyle = color;
    ctx.lineWidth = line;
    ctx.beginPath();
    for (const dx of [-1, 1])
      for (const dy of [-1, 1]) {
        const x = bleed + (dx === 1 ? w : 0),
          y = bleed + (dy === 1 ? h : 0);
        ctx.moveTo(x + dx * bleed, y);
        ctx.lineTo(x + (dx * bleed) / 3, y);
        ctx.moveTo(x, y + dy * bleed);
        ctx.lineTo(x, y + (dy * bleed) / 3);
      }
    ctx.stroke();
  }
  return out;
}
