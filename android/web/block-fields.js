import { el, button, group, field, input, select, sheet, closeSheet, message } from "./dom.js";
import { pickName } from "./names.js";
export function fieldControl(node, [key, label, type, opt], ctx, setValue, redraw) {
  const { library, pack } = ctx;
  const set = (value) => setValue(node, key, value);
  if (type === "choice" || type === "code")
    return field(label, select(type === "code" ? library.codes : opt, node[key], set));
  if (type === "multi") {
    const b = button("选择", () => {
      const picked = new Set(String(node[key]).split("+")),
        items = group("checks");
      for (const [value, name] of opt) {
        const cb = el("input");
        cb.type = "checkbox";
        cb.checked = picked.has(value);
        cb.onchange = () => (cb.checked ? picked.add(value) : picked.delete(value));
        const l = el("label");
        l.append(cb, name);
        items.append(l);
      }
      sheet(
        label,
        group(
          "stack",
          items,
          button(
            "应用",
            () => {
              if (!picked.size) {
                message("请至少选择一项");
                return;
              }
              set([...picked].join("+"));
              closeSheet();
              redraw();
            },
            "primary"
          )
        )
      );
    });
    const names = new Map(opt);
    b.textContent =
      String(node[key])
        .split("+")
        .map((x) => names.get(x) || "无")
        .join("、") || "选择";
    return field(label, b);
  }
  if (type === "counter") {
    const entries = Object.entries(pack.counters),
      code = node[key] === "spell" ? "0x1" : node[key];
    const choices = [
      ["0x1", "魔力指示物 · 0x1"],
      ...entries.filter(([k]) => k !== "0x1").map(([k, v]) => [k, v + " · " + k])
    ];
    if (!choices.some(([k]) => k === code)) choices.push([code, code]);
    const edit = button("新建、修改、查找…", () =>
      pickName(ctx, true, (id) => {
        set(id);
        redraw();
      })
    );
    return group("stack", field(label, select(choices, code, set)), edit);
  }
  const n = input(
    node[key],
    (v) => {
      if (type === "int") {
        if (v === "" || !Number.isFinite(Number(v))) return;
        set(Math.trunc(Number(v)));
      } else set(v);
    },
    type === "int" ? "number" : "text"
  );
  return field(label, n);
}
