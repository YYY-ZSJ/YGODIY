import { manage } from "./names.js";
import { el, group, button, input } from "./dom.js";
import { blocksView } from "./blocks.js";
import { editor } from "./editor.js";
import { frameName } from "./project.js";

export function workbench(main, ctx) {
  const labels = ["效果", "卡面", "卡包"],
    tabs = el("div", "tabs"),
    body = el("div", "wb-content");
  const tab = ctx.state.workTab || "效果";
  labels.forEach((l) => tabs.append(button(l, () => ctx.workTab(l), l === tab ? "active" : "")));
  main.replaceChildren(
    group(
      "wb",
      tabs,
      body,
      group(
        "foot",
        el("span", "", "卡包「" + ctx.pack.name + "」 · " + ctx.pack.cards.length + " 张"),
        button("导出这个卡包…", () => ctx.exportProject(false))
      )
    )
  );
  if (tab === "效果") blocksView(body, ctx);
  else if (tab === "卡面") editor(body, ctx);
  else packPage(body, ctx);
}
function packPage(body, ctx) {
  const { pack, card, state } = ctx;
  const tbl = el("table"),
    head = el("tr");
  for (const s of ["卡号", "卡名", "种类", "字段", "效果", "卡面文字"]) head.append(el("th", "", s));
  tbl.append(head);
  for (const c of pack.cards) {
    const row = el("tr", c === card ? "active" : "");
    for (const t of [
      c.data.cardpass,
      c.data.name,
      frameName(c.data),
      (c.setcodes || []).map((i) => pack.setnames?.[i] || i).join("、"),
      c.effects.length + " 个效果",
      c.data.effect_text ? "已填写" : "空白"
    ])
      row.append(el("td", "", t));
    row.onclick = () => {
      state.card = c.id;
      ctx.save();
      ctx.side();
      ctx.redraw();
      for (const r of tbl.rows) r.classList.toggle("active", r === row);
    };
    row.ondblclick = () => {
      state.card = c.id;
      ctx.workTab("效果");
    };
    tbl.append(row);
  }
  const settings = group(
    "box stack",
    el("h3", "", "卡包设置"),
    group("row", el("span", "", "包名"), el("span", "", pack.name)),
    group(
      "row",
      el("span", "", "作者"),
      input(pack.author || "", (v) => {
        pack.author = v;
        ctx.save();
      })
    )
  );
  const names = el("div", "box stack");
  function namesTab(type) {
    names.replaceChildren();
    manage(names, ctx, type, namesTab);
  }
  namesTab("字段");
  const actions = group(
    "box stack",
    el("h3", "", "导出"),
    group(
      "row",
      button("导入卡片或卡包…", () => Documents.importPack()),
      button("导出这张卡…", () => ctx.exportProject(true)),
      button("导出这个卡包…", () => ctx.exportProject(false)),
      button("导出文字", () => ctx.copyText())
    )
  );
  body.replaceChildren(
    group(
      "pack-page",
      group(
        "box",
        el("h3", "", "卡片一览"),
        el("small", "", "卡包「" + pack.name + "」 · " + pack.cards.length + " 张"),
        group("pack-table", tbl)
      ),
      group("pack-cols", settings, names),
      actions
    )
  );
}
