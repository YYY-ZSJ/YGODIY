import { copy } from "./project.js";
export const kinds = {
  hat: "效果",
  stmt: "动作与控制",
  target: "取对象",
  option: "分支选项",
  cards: "卡片",
  filter: "卡片条件",
  number: "数值",
  cond: "发动条件"
};
export const colors = {
  hat: "#8973bd",
  stmt: "#328972",
  target: "#bc5961",
  option: "#978157",
  cards: "#c57b48",
  filter: "#bb6c93",
  number: "#ae8439",
  cond: "#5487bc"
};
let worker,
  sequence = 0;
const pending = new Map();
export function reader(model) {
  if (!worker) {
    worker = new Worker("reader-worker.js");
    worker.onmessage = ({ data }) => {
      const fn = pending.get(data.id);
      if (fn) fn(data);
      pending.delete(data.id);
    };
    worker.onerror = () => {
      for (const fn of pending.values()) fn({ error: "积木文字组件加载失败，请重新打开积木页。" });
      pending.clear();
      worker.terminate();
      worker = null;
    };
  }
  return new Promise((resolve) => {
    const id = ++sequence;
    pending.set(id, resolve);
    worker.postMessage({ id, model });
  });
}
export function starter(blocks) {
  const effect = copy(blocks.effect.initial);
  effect.type = "ignition";
  effect.limit = "card";
  effect.operation = [copy(blocks.draw.initial)];
  return effect;
}
export function summary(node, def, counters) {
  const parts = [];
  for (const [key, , type, opt] of def.fields) {
    const value = node[key];
    if (type === "choice" || type === "multi") {
      const names = new Map(opt);
      if (value !== "")
        parts.push(
          String(value)
            .split("+")
            .map((k) => names.get(k) || k)
            .join("·")
        );
    } else if (value !== "" && (type !== "int" || value > 0))
      parts.push(type === "counter" ? counters[value] || value : String(value));
    if (parts.length === 2) break;
  }
  return def.label + (parts.length ? " · " + parts.join(" / ") : "");
}
