import { $, el, group, button, input, ask, sheet, closeSheet } from "./dom.js";
import { newPack, newCard, copy } from "./project.js";

function sortable(items, buttonFor, reorder) {
  const box = el("div", "items");
  for (const item of items) {
    const b = buttonFor(item);
    b.dataset.id = item.id;
    b.draggable = true;
    b.ondragstart = (e) => e.dataTransfer.setData("text/plain", item.id);
    b.ondragover = (e) => e.preventDefault();
    b.ondrop = (e) => {
      e.preventDefault();
      const id = e.dataTransfer.getData("text/plain");
      if (items.some((x) => x.id === id)) reorder(id, item.id);
    };
    box.append(b);
  }
  let timer,
    source,
    moved = false;
  box.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse" || !e.target.dataset.id) return;
    source = e.target.dataset.id;
    moved = false;
    timer = setTimeout(() => {
      box.classList.add("dragging");
      box.setPointerCapture(e.pointerId);
    }, 450);
  });
  box.addEventListener("pointermove", (e) => {
    if (!box.classList.contains("dragging")) return;
    moved = true;
    const next = document.elementFromPoint(e.clientX, e.clientY)?.closest(".items button");
    box.querySelector(".drop-target")?.classList.remove("drop-target");
    if (box.contains(next)) next.classList.add("drop-target");
  });
  const end = (e) => {
    clearTimeout(timer);
    const active = box.classList.contains("dragging"),
      b = box.querySelector(".drop-target");
    box.classList.remove("dragging");
    b?.classList.remove("drop-target");
    if (active && moved && b && e.type === "pointerup") reorder(source, b.dataset.id);
  };
  box.onpointerup = end;
  box.onpointercancel = end;
  return box;
}
export function sidebars(ctx) {
  const { state, pack, card, save, refresh } = ctx;
  function change(fn) {
    fn();
    save();
    refresh();
  }
  function build(isPack) {
    const entries = isPack ? state.packs : pack.cards,
      active = isPack ? pack : card,
      label = isPack ? "卡包" : "卡片";
    const name = (x) => (isPack ? x.name : x.data.name);
    const pick = (x) =>
      change(() => {
        if (isPack) {
          state.pack = x.id;
          state.card = x.cards[0].id;
        } else state.card = x.id;
      });
    function rename(x) {
      ask(
        "修改" + label + "名称",
        label + "名称",
        (v) =>
          change(() => {
            if (isPack) x.name = v;
            else x.data.name = v;
          }),
        name(x)
      );
    }
    const list = sortable(
      entries,
      (x) => {
        const b = button(
          name(x) || "未命名",
          () => {
            if (x !== active) pick(x);
          },
          x === active ? "selected" : ""
        );
        b.ondblclick = () => rename(x);
        return b;
      },
      (from, to) =>
        change(() => {
          const i = entries.findIndex((x) => x.id === from),
            k = entries.findIndex((x) => x.id === to);
          entries.splice(k, 0, entries.splice(i, 1)[0]);
        })
    );
    function add() {
      ask(
        "新建" + label,
        "名称",
        (v) =>
          change(() => {
            const x = isPack ? newPack(v) : newCard(v);
            entries.push(x);
            if (isPack) state.pack = x.id;
            state.card = isPack ? x.cards[0].id : x.id;
          }),
        isPack ? "卡包" + (entries.length + 1) : "新卡片"
      );
    }
    function duplicate() {
      change(() => {
        const x = copy(active);
        x.id = newCard().id;
        if (isPack) {
          x.name += " 副本";
          for (const c of x.cards) c.id = newCard().id;
          state.pack = x.id;
          state.card = x.cards[0].id;
        } else {
          x.data.name += " 副本";
          state.card = x.id;
        }
        entries.push(x);
      });
    }
    function remove() {
      ask("删除" + label, "删除「" + name(active) + "」？", () =>
        change(() => {
          const i = entries.indexOf(active);
          entries.splice(i, 1);
          if (!entries.length) entries.push(isPack ? newPack("卡包1") : newCard());
          const next = entries[Math.min(i, entries.length - 1)];
          if (isPack) state.pack = next.id;
          state.card = isPack ? next.cards[0].id : next.id;
        })
      );
    }
    function search() {
      const results = el("div", "stack"),
        q = input("", show);
      q.placeholder = "输入" + label + "名";
      q.className = "search";
      function show() {
        results.replaceChildren();
        for (const x of entries.filter((x) => name(x).includes(q.value)))
          results.append(
            button(name(x), () => {
              closeSheet();
              pick(x);
            })
          );
      }
      show();
      sheet(
        label + "高级搜索",
        group(
          "stack",
          q,
          results,
          button("重命名当前" + label, () => rename(active))
        )
      );
    }
    const root = $(isPack ? "pack-list" : "card-list");
    root.replaceChildren(
      el("h2", "", label),
      list,
      ...(isPack
        ? []
        : [
            button("保存草稿", () => {
              if (save()) ctx.notify("草稿已保存");
            })
          ]),
      button("新建", add),
      button("复制", duplicate),
      button("删除", remove),
      button("高级搜索", search)
    );
  }
  build(true);
  build(false);
}
