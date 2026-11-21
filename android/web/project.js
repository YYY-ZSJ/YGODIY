export const MODES = {
  ocg: "OCG/TCG",
  rd: "超速决斗(Rush Duel)",
  field: "场地中心卡(Field Center)",
  back: "游戏王卡背",
  past: "游戏王旧版卡",
  manga: "游戏王漫画卡"
};
export const CALLS = [
  "通常",
  "效果",
  "融合",
  "仪式",
  "同调",
  "超量",
  "衍生物",
  "连接",
  "暗黑同调",
  "巨神兵",
  "天空龙",
  "翼神龙"
];
export const MT = ["通常", "永续", "装备", "仪式", "场地", "反击", "速攻"];
const makeId = () => Array.from(crypto.getRandomValues(new Uint32Array(3)), (n) => n.toString(16)).join("-");
export const copy = (value) => JSON.parse(JSON.stringify(value));
export const defaults = {
  name: "未命名卡片",
  card_type: 0,
  call_way: 1,
  race: 0,
  attribute: "光",
  level: 4,
  rank: 4,
  ATK: "1600",
  DEF: "1200",
  effect_text: "",
  lb_text: "",
  cardpass: "",
  cardpack: "",
  mt_type: 0,
  extra1: 0,
  extra2: 0,
  lb_level: "4",
  link_status: [false, false, false, true, true, false, false, false]
};
const styleDefaults = {
  mode: "ocg",
  template: "official",
  language: "0",
  align: "left",
  fit: "cover",
  series: "3",
  back: "普通",
  field: "古埃及黑",
  zoom: 1,
  x: 50,
  y: 50,
  size: 0,
  ink: "",
  copyright: "",
  raceText: "",
  demo: false,
  mono: true
};
export function newCard(name = "未命名卡片") {
  return {
    id: makeId(),
    data: { ...copy(defaults), name },
    style: { ...styleDefaults },
    art: "",
    effects: [],
    setcodes: []
  };
}
export function newPack(name = "卡包1") {
  return { id: makeId(), name, counters: {}, cards: [newCard()] };
}
export function initialProject() {
  const pack = newPack(),
    card = pack.cards[0];
  Object.assign(card.data, {
    name: "青眼白龙",
    call_way: 0,
    level: 8,
    ATK: "3000",
    DEF: "2500",
    cardpass: "89631139",
    effect_text: "以高攻击力著称的传说之龙。任何对手都能粉碎，其破坏力不可估量。"
  });
  card.style.demo = true;
  return {
    version: 1,
    packs: [pack],
    pack: pack.id,
    card: card.id,
    bleed: false,
    shortcuts: ["「」", "①", "②", "③", "④", "⑤", "●"]
  };
}
export function packOf(state) {
  return state.packs.find((p) => p.id === state.pack) || state.packs[0];
}
export function cardOf(state) {
  const p = packOf(state);
  return p.cards.find((c) => c.id === state.card) || p.cards[0];
}
export function frameName(d) {
  if (d.card_type === 1) return "魔法卡";
  if (d.card_type === 2) return "陷阱卡";
  return (CALLS[d.call_way] || "效果") + (d.extra1 === 9 || d.extra2 === 9 ? "灵摆" : "");
}
function readValues(template, source) {
  const result = copy(template);
  for (const [key, value] of Object.entries(template)) {
    const v = source?.[key];
    if (Array.isArray(value)) {
      if (Array.isArray(v)) result[key] = value.map((_, i) => Boolean(v[i]));
    } else if (typeof value === typeof v && (typeof v !== "number" || Number.isFinite(v))) result[key] = v;
  }
  return result;
}
function readTree(items, catalog, slot, report, depth = 0) {
  if (!Array.isArray(items)) return [];
  if (depth > 40 || report.count + items.length > 12000) throw Error("积木树过大，请分开导入。");
  const result = [];
  for (const item of items) {
    const def = Object.hasOwn(catalog, item?.block) && catalog[item.block];
    if (
      !def ||
      def.kind !== slot[2] ||
      (slot[4] && !slot[4].includes(item.block)) ||
      (slot[3] && result.length >= slot[3])
    ) {
      report.skipped++;
      continue;
    }
    report.count++;
    const node = copy(def.initial);
    for (const [key, , type, options] of def.fields) {
      const v = item[key];
      if (v == null) continue;
      if (type === "choice" || type === "multi") {
        const keys = options.map((o) => o[0]);
        if (
          keys.includes(v) ||
          (type === "multi" && typeof v === "string" && v.split("+").every((k) => keys.includes(k)))
        )
          node[key] = v;
      } else if (type === "int" && Number.isFinite(Number(v))) node[key] = Math.trunc(Number(v));
      else if (typeof v === "string" && type !== "int") node[key] = v;
    }
    for (const child of def.slots) node[child[0]] = readTree(item[child[0]], catalog, child, report, depth + 1);
    result.push(node);
  }
  return result;
}
export function fromManifest(m, catalog) {
  if (m.format !== "ygodiy-transfer/1" || !["pack", "card"].includes(m.kind) || !m.cards?.length)
    throw Error("工程格式不正确。");
  const p = newPack(String(m.title || "导入的卡包")),
    report = { count: 0, skipped: 0 };
  p.author = String(m.diy?.author || "");
  p.setnames = {};
  for (const [id, n] of Object.entries(m.diy?.setnames || {}))
    if (/^0x[0-9a-f]{1,4}$/i.test(id) && typeof n === "string") p.setnames[id] = n;
  for (const [key, name] of Object.entries(m.diy?.counters || {})) {
    if (/^0x[\da-f]{1,4}$/i.test(key) && typeof name === "string") p.counters[key.toLowerCase()] = name;
  }
  p.cards = m.cards.map((entry) => {
    const c = newCard();
    c.data = readValues(defaults, entry.data);
    c.data.name = entry.data?.name || String(entry.title || c.data.name);
    const desktop = entry.data || {};
    c.style = readValues(
      {
        ...styleDefaults,
        template: desktop.template === 1 ? "new" : "official",
        language: String(desktop.language === 1 ? 1 : 0)
      },
      desktop.android_style
    );
    c.setcodes = Array.isArray(entry.diy?.setcodes)
      ? entry.diy.setcodes.filter((k) => typeof k === "string" && /^0x[0-9a-f]{1,4}$/i.test(k))
      : [];
    if (!Object.hasOwn(MODES, c.style.mode)) c.style.mode = "ocg";
    c.art = /^[a-f0-9]{64}$/.test(entry.image || "") ? entry.image : "";
    c.effects = readTree(entry.diy?.blocks?.effects, catalog, ["", "", "hat", 0, null], report);
    return c;
  });
  return { pack: p, skipped: report.skipped };
}
export function manifest(pack, cards, single = false) {
  return {
    format: "ygodiy-transfer/1",
    kind: single ? "card" : "pack",
    title: single ? cards[0].data.name : pack.name,
    diy: { counters: pack.counters, setnames: pack.setnames || {}, author: pack.author || "" },
    cards: cards.map((c) => ({
      title: c.data.name,
      data: {
        ...c.data,
        template: c.style.template === "new" ? 1 : 0,
        language: Number(c.style.language) || 0,
        android_style: c.style
      },
      diy: { setcodes: c.setcodes || [], blocks: { schema: "ygodiy-blocks/0.3", effects: c.effects } },
      ...(c.art || c.style.demo ? { image: c.art || "builtin-demo" } : {})
    }))
  };
}
