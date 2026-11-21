import { pickName } from "./names.js";
import { el, button, group, ask, message } from "./dom.js";
import { copy } from "./project.js";

import { fieldControl } from "./block-fields.js";
import { kinds, colors, reader, starter, summary } from "./block-text.js";
export function blocksView(main, ctx) {
  const { card, pack, library, save } = ctx,
    defs = library.blocks,
    undo = [];
  const palette = el("div", "palette"),
    tree = el("div", "tree"),
    props = el("div", "inspector"),
    output = el("div", "sample");
  let selected = null,
    owner = null,
    slot = null,
    tab = "规范文本",
    rendered = null,
    ticket = 0,
    timer,
    issues = [];
  const rootSlot = ["effects", "效果", "hat", 0, null],
    opened = new Set(),
    previews = el("div", "tabs");
  const write = button("写回卡面", () =>
    ask("写回卡面", "用规范文本替换当前卡的效果文字和灵摆效果？", () => {
      if (rendered) {
        [card.data.effect_text, card.data.lb_text] = rendered;
        save();
        ctx.redraw();
        paintOutput();
        message("已写回卡面");
      }
    })
  );
  function remember() {
    undo.push(copy(card.effects));
    if (undo.length > 25) undo.shift();
  }
  function change(fn) {
    remember();
    fn();
    save();
    redraw();
  }
  function pickSlot(list, s) {
    selected = null;
    owner = list;
    slot = s;
    redraw(false);
  }
  function fits(def, s) {
    return s && s[2] === def.kind && (!s[4] || s[4].includes(def.initial.block));
  }
  function insert(key) {
    const def = defs[key];
    let target = owner,
      s = slot;
    if (def.kind === "hat") {
      target = card.effects;
      s = rootSlot;
    } else if (!s && selected) {
      s = defs[selected.block].slots.find((v) => fits(def, v) && (!v[3] || !(selected[v[0]] || []).length));
      target = s && selected[s[0]];
    }
    if (!fits(def, s) || !target) {
      message("先在中栏点选与此积木匹配的空槽");
      return;
    }
    if (s[3] && target.length >= s[3]) {
      message("此槽已满，请先移除原积木");
      return;
    }
    change(() => {
      selected = copy(def.initial);
      target.push(selected);
      owner = target;
      slot = null;
      opened.add(selected);
    });
  }
  function fillPalette() {
    palette.replaceChildren(el("div", "", "全部积木"));
    for (const [kind, title] of Object.entries(kinds)) {
      const section = el("details");
      section.open = slot ? slot[2] === kind : kind === (selected ? defs[selected.block].kind : "hat");
      const name = el("summary", "", title);
      name.style.color = colors[kind];
      section.append(name);
      for (const [key, def] of Object.entries(defs).filter(([, d]) => d.kind === kind)) {
        const b = button("■ " + def.label, () => insert(key));
        b.style.background = colors[kind] + "22";
        b.style.color = colors[kind];
        section.append(b);
      }
      palette.append(section);
    }
  }
  function selectNode(node, list) {
    selected = node;
    owner = list;
    slot = null;
    opened.add(node);
    redraw(false);
  }
  function row(node, list) {
    const def = defs[node.block],
      li = el("details"),
      title = el(
        "summary",
        "tree-node" + (selected === node ? " selected-node" : ""),
        "● " + summary(node, def, pack.counters)
      );
    title.style.backgroundColor = colors[def.kind] + "29";
    li.open = opened.has(node);
    li.append(title);
    title.onclick = (e) => {
      e.preventDefault();
      const was = selected === node && opened.has(node);
      selectNode(node, list);
      if (was) {
        opened.delete(node);
        fillTree();
      }
    };
    for (const s of def.slots) {
      const children = node[s[0]] || (node[s[0]] = []),
        sub = el("details");
      sub.open = true;
      const line = el(
        "summary",
        "slot-node" + (slot === s && owner === children ? " selected-node" : ""),
        "▢ " + s[1] + (children.length ? "" : "　（放一块" + kinds[s[2]] + "）")
      );
      line.onclick = (e) => {
        e.preventDefault();
        pickSlot(children, s);
      };
      sub.append(line, ...children.map((k) => row(k, children)));
      li.append(sub);
    }
    return li;
  }
  function fillTree() {
    tree.replaceChildren(...card.effects.map((node) => row(node, card.effects)));
    if (!card.effects.length)
      tree.append(
        button("＋ 添加效果", () => insert("effect")),
        button("试拼「抽一张卡」", () =>
          change(() => {
            selected = starter(defs);
            owner = card.effects;
            owner.push(selected);
            opened.add(selected);
            slot = null;
          })
        )
      );
  }
  function paintOutput() {
    previews.replaceChildren();
    for (const name of ["规范文本", "设计稿", "检查"])
      previews.append(
        button(
          name,
          () => {
            tab = name;
            paintOutput();
          },
          tab === name ? "active" : ""
        )
      );
    if (tab === "设计稿") output.textContent = card.data.effect_text || "当前卡面还没有效果文字。";
    else if (tab === "检查") output.textContent = issues.join("\n") || "已检查积木连接。";
    else
      output.textContent = rendered
        ? rendered.filter(Boolean).join("\n") || "请添加效果和处理。"
        : "正在生成中文效果…";
    write.disabled = !rendered?.some(Boolean);
  }
  function generate() {
    const token = ++ticket;
    clearTimeout(timer);
    rendered = null;
    issues = [];
    if (!card.effects.length) {
      rendered = ["", ""];
      issues.push("请添加一块效果积木。");
      paintOutput();
      return;
    }
    for (const e of card.effects)
      if (e.block === "effect" && !e.operation.length && !e.modes?.length)
        issues.push("效果的「处理」槽还没有动作。");
    paintOutput();
    timer = setTimeout(async () => {
      const r = await reader([card.effects, card.data.name, pack.counters]);
      if (token !== ticket || !props.isConnected) return;
      if (r.error) {
        issues.push(r.error);
        rendered = null;
        paintOutput();
        output.textContent = r.error;
        write.disabled = true;
      } else {
        rendered = r.text;
        paintOutput();
      }
    }, 110);
  }
  function setValue(node, key, value) {
    if (node[key] === value) return;
    remember();
    node[key] = value;
    save();
    fillTree();
    generate();
  }
  function details() {
    props.replaceChildren();
    if (!selected) {
      props.append(
        el(
          "p",
          "",
          slot
            ? "已选「" + slot[1] + "」。点左栏中的" + kinds[slot[2]] + "积木放入这里。"
            : "选中一块积木，在这里改它的选项。"
        )
      );
      return;
    }
    const def = defs[selected.block],
      grid = el("div", "fields");
    props.append(el("h3", "", def.label), grid);
    for (const f of def.fields) grid.append(fieldControl(selected, f, ctx, setValue, redraw));
    if (["f_set", "f_prev_set"].includes(selected.block))
      grid.append(
        button("新建、修改、查找字段…", () =>
          pickName(ctx, false, (id, name) =>
            change(() => {
              selected.setcode = id;
              selected.name = name;
            })
          )
        )
      );
    if (!def.fields.length && def.help[0]) props.append(el("p", "hint", def.help[0]));
  }
  const del = button("删除选中的积木", () => {
    if (selected && owner)
      change(() => {
        owner.splice(owner.indexOf(selected), 1);
        selected = null;
        slot = null;
        owner = null;
      });
  });
  const back = button("撤销", () => {
    if (undo.length) {
      card.effects = undo.pop();
      selected = owner = slot = null;
      opened.clear();
      card.effects.forEach((n) => opened.add(n));
      save();
      redraw();
    }
  });
  const legend = el("div", "legend");
  for (const [k, v] of Object.entries(kinds)) {
    const l = el("span", "", "■ " + v);
    l.style.color = colors[k];
    legend.append(l);
  }
  legend.append("　（空心▢是槽：放同色的积木）");
  const head = group(
    "summary",
    el(
      "b",
      "",
      card.data.name +
        "　" +
        (card.data.card_type === 0
          ? "怪兽 · " +
            card.data.level +
            "星 · " +
            card.data.attribute +
            " · " +
            card.data.ATK +
            "/" +
            card.data.DEF
          : card.data.card_type === 1
            ? "魔法卡"
            : "陷阱卡")
    ),
    group(
      "row",
      button("字段：" + ((card.setcodes || []).map((k) => pack.setnames?.[k] || k).join("、") || "无"), () =>
        pickName(ctx, false, (id) => {
          const codes = new Set(card.setcodes || []);
          if (codes.has(id)) codes.delete(id);
          else codes.add(id);
          card.setcodes = [...codes];
          save();
          ctx.refresh();
        })
      ),
      button("修改卡面信息", () => ctx.workTab("卡面")),
      button(ctx.state.focus !== false ? "退出专注模式" : "专注模式", () => ctx.focus())
    )
  );
  const rule = button(
    "出场限制： " + (card.effects.some((e) => e.block === "summon_rule") ? "已设置" : "无") + " ▼",
    () => {
      const e = card.effects.find((x) => x.block === "summon_rule");
      if (e) selectNode(e, card.effects);
      else insert("summon_rule");
    }
  );
  main.replaceChildren(
    group(
      "block-layout",
      head,
      group("row", rule),
      group(
        "row",
        del,
        back,
        button("积木入门", () => ctx.go("guide"))
      ),
      legend,
      group("block-grid", palette, tree, props),
      group("outbox", previews, output, group("row", write))
    )
  );
  function redraw(gen = true) {
    fillPalette();
    fillTree();
    details();
    del.disabled = !selected;
    back.disabled = !undo.length;
    if (gen) generate();
  }
  card.effects.forEach((n) => opened.add(n));
  redraw();
}
