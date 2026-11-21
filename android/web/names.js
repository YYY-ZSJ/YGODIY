import { el, group, button, ask, input, sheet, closeSheet, message } from "./dom.js";
export function manage(panel, ctx, type, rerender, onPick) {
  const counter = type === "指示物",
    noun = counter ? "指示物" : "字段",
    key = counter ? "counters" : "setnames";
  const dict = ctx.pack[key] || (ctx.pack[key] = {}),
    list = el("div", "pack-names");
  let active = Object.keys(dict)[0];
  function display() {
    list.replaceChildren();
    for (const [id, name] of Object.entries(dict)) {
      const b = button(
        id + "　" + name,
        () => {
          active = id;
          for (const row of list.children) row.classList.toggle("selected-row", row === b);
        },
        id === active ? "selected-row" : ""
      );
      b.ondblclick = () => (onPick ? onPick(id, name) : edit(true));
      list.append(b);
    }
  }
  function edit(existing) {
    if (existing && !active) return;
    const old = existing ? active : "",
      code = input(old, () => {}),
      name = input(existing ? dict[old] : "", () => {});
    code.placeholder = "留空自动分配，或输入 0x 编号";
    name.placeholder = noun + "名称";
    sheet(
      (existing ? "修改" : "新建") + noun,
      group(
        "stack",
        code,
        name,
        button(
          "确定",
          () => {
            const max = 65535;
            let n = code.value.trim() ? Number(code.value.trim()) : counter ? 2 : 0xa01;
            if (!code.value.trim()) while (n <= max && dict["0x" + n.toString(16)]) n++;
            if (!Number.isInteger(n) || n < 1 || n > max || !name.value.trim()) {
              message("请输入有效的编号和名称。");
              return;
            }
            const id = "0x" + n.toString(16);
            if (old !== id && dict[id]) {
              message("编号已被占用");
              return;
            }
            if (old) delete dict[old];
            dict[id] = name.value.trim();
            if (existing)
              for (const c of ctx.pack.cards) {
                adjustReference(c.effects, old, id, dict[id], counter);
                if (!counter) c.setcodes = (c.setcodes || []).map((k) => (k === old ? id : k));
              }
            ctx.save();
            active = id;
            closeSheet();
            if (onPick) onPick(id, dict[id]);
            else display();
          },
          "primary"
        )
      )
    );
  }
  const find = () => {
    const q = input("", show),
      results = el("div", "stack");
    function show() {
      results.replaceChildren();
      for (const [id, name] of Object.entries(dict).filter(([i, n]) => (i + n).includes(q.value.trim())))
        results.append(
          button(id + "　" + name, () => {
            active = id;
            closeSheet();
            if (onPick) onPick(id, dict[id]);
            else display();
          })
        );
    }
    show();
    q.placeholder = "输入名称或编号";
    sheet("查找" + noun, group("stack", q, results));
  };
  panel.append(
    ...(onPick
      ? []
      : [
          group(
            "tabs",
            button("自己的字段", () => rerender("字段"), counter ? "" : "active"),
            button("指示物", () => rerender("指示物"), counter ? "active" : "")
          )
        ]),
    list,
    group(
      "row",
      button("＋ 新建" + noun, () => edit(false)),
      button("修改编号或名称", () => edit(true)),
      button("删除选中的", () => {
        if (active)
          ask("删除" + noun, "删除名称「" + dict[active] + "」？已有积木保留编号。", () => {
            delete dict[active];
            active = Object.keys(dict)[0];
            ctx.save();
            display();
          });
      }),
      button("查找" + noun + "…", find),
      ...(onPick
        ? [
            button("选用", () => {
              if (active) onPick(active, dict[active]);
            })
          ]
        : [])
    )
  );
  display();
}
function adjustReference(nodes, old, id, name, counter) {
  for (const node of nodes) {
    if (counter && node.counter === old) node.counter = id;
    if (!counter && ["f_set", "f_prev_set"].includes(node.block) && Number(node.setcode) === Number(old)) {
      node.setcode = id;
      node.name = name;
    }
    for (const value of Object.values(node))
      if (Array.isArray(value)) adjustReference(value, old, id, name, counter);
  }
}
export function pickName(ctx, counter, onPick) {
  const panel = group("stack"),
    type = counter ? "指示物" : "字段";
  function open() {
    panel.replaceChildren();
    manage(panel, ctx, type, open, (id, name) => {
      closeSheet();
      onPick(id, name);
    });
    sheet("选用或管理" + type, panel);
  }
  open();
}
