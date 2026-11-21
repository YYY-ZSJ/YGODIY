import { el, button, group, input, sheet } from "./dom.js";
import { kinds, starter } from "./block-text.js";
const start = {
  group: "入门练习",
  title: "第一次制卡：让自己抽一张",
  body: [
    {
      text: "准备一张练习卡。点左侧「卡片」栏下方的「新建」，取名「见习记录员」。在顶部模式框选 OCG/TCG，右边选怪兽卡、效果怪兽，中间可以看卡面。"
    },
    {
      text: "先说出想做的事：自己主要阶段，让自己抽1张卡，每回合限1次。「效果」决定何时能做，「处理」决定做什么。槽就像填空，每个槽只列出可以放进去的积木。"
    },
    {
      text: "点模式框的「DIY 工作台」→「效果」，点左栏「会发动的效果」，将类型选为「起动效果」，次数选为这张卡每回合1次。点中栏的「处理」，再点左栏「动作与控制」下的「抽卡」。点中栏新放入的抽卡积木，在右栏选「自己」，张数填1。"
    },
    {
      text: "看中栏下方的规范文本。把张数改为2，观察预览；再改回1。点「写回卡面」确认，切换到「卡面」就能看到成句。只有自己确认写入，才会替换手写效果。"
    },
    {
      text: "如果找不到动作，先展开中栏效果，点它的「处理」槽，再到左栏选动作。想改哪块就点中栏对应行；放错可点「删除选中的积木」或「撤销」。"
    },
    {
      text: "要一张成品图片，在卡面参数底部点「导出图片」→「保存卡图 PNG」。要以后接着改，导出 .ydiy 工程。手机关闭后草稿仍可接着编辑。"
    }
  ]
};
export function guide(main, ctx) {
  const tabs = el("div", "tabs"),
    bar = el("div", "qtrow"),
    reader = el("article", "book-reader"),
    search = input("", filter),
    selectChapter = el("select"),
    tools = el("div", "row");
  let mode = "入门练习",
    entries = [],
    index = 0;
  const intro = [
    start,
    {
      group: "入门练习",
      title: "卡包、卡片与草稿",
      body: [
        {
          text: "横屏左边第一列是卡包，第二列是卡片。点卡包切换整组作品，点卡片切换编辑对象。长按后拖动一行就能排序，高级搜索可按名称定位。点「保存草稿」可再次保存。"
        },
        {
          text: "模式下拉框在右侧顶部。选 OCG/TCG 后可在右边编辑，预览位于中间；选 DIY 工作台后，点「效果」进入积木编辑。在专注模式里，预览让出空间给三个编辑栏。"
        }
      ]
    }
  ];
  const blocks = Object.entries(ctx.library.blocks).map(([key, b]) => ({
    title: b.label,
    group: kinds[b.kind],
    key,
    block: b
  }));
  search.placeholder = "查本栏课程，例如输入「代价」或「连锁」";
  search.className = "guide-search";
  selectChapter.className = "grow";
  selectChapter.onchange = () => {
    index = Number(selectChapter.value);
    show();
  };
  function show() {
    reader.replaceChildren();
    tools.replaceChildren();
    const entry = entries[index];
    if (!entry) {
      reader.textContent = "没有匹配的章节。";
      return;
    }
    reader.append(el("h2", "", entry.title));
    if (entry.block) {
      const b = entry.block;
      for (const [i, p] of b.help.entries())
        reader.append(el("h3", "", ["这块做什么", "动手拼一次", "遇到问题时"][i]), el("p", "", p));
      if (b.fields.length)
        reader.append(el("h3", "", "可以调整的参数"), el("p", "", b.fields.map((f) => f[1]).join("、")));
      if (b.slots.length)
        reader.append(
          el("h3", "", "可以接哪些积木"),
          ...b.slots.map((s) =>
            el("p", "", s[1] + " → " + kinds[s[2]] + "，" + (s[3] ? "最多一块" : "可放多块"))
          )
        );
    } else if (mode === "练习桌") {
      const n = input("1", () => {}, "number");
      n.min = 1;
      n.max = 20;
      reader.append(
        el("p", "", "先选要抽的张数，再核对中文。练习中的调整会留在这里；点「加入当前卡」才会修改作品。"),
        group("qtrow", el("span", "", "自己抽几张"), n)
      );
      const result = el("p", "sample");
      const sample = () => {
        const node = starter(ctx.library.blocks);
        node.operation[0].count = Math.min(20, Math.max(1, Number(n.value) || 1));
        return node;
      };
      reader.append(
        button(
          "看搭法",
          () =>
            (result.textContent = "会发动的效果 → 处理 → 抽卡：自己抽 " + sample().operation[0].count + " 张。")
        ),
        result,
        button("加入当前卡", () => {
          ctx.card.effects.push(sample());
          ctx.save();
          ctx.workTab("效果");
        })
      );
    } else
      for (const part of entry.body) {
        if (part.image) {
          const img = el("img");
          img.src = part.image;
          img.alt = part.alt;
          reader.append(img);
        } else reader.append(el("p", "", part.text));
      }
    const prev = button("上一节", () => step(-1)),
      next = button("下一节", () => step(1));
    prev.disabled = index === 0;
    next.disabled = index === entries.length - 1;
    tools.append(prev, next);
    const illustration = reader.querySelector("img");
    if (illustration)
      tools.append(
        button("查看配图原图", () => {
          const img = illustration.cloneNode();
          img.style.width = "100%";
          sheet(illustration.alt, img);
        })
      );
    selectChapter.value = index;
    reader.scrollTop = 0;
  }
  function step(diff) {
    index += diff;
    show();
  }
  function filter() {
    const source =
      mode === "入门练习"
        ? intro
        : mode === "决斗规则"
          ? ctx.library.chapters
          : mode === "积木图鉴"
            ? blocks
            : [{ title: "抽卡练习" }];
    entries = source.filter((e) =>
      [e.title, e.group, ...(e.block?.help || [])].some((t) => String(t || "").includes(search.value.trim()))
    );
    index = 0;
    selectChapter.replaceChildren(...entries.map((e, i) => new Option(i + 1 + ". " + e.title, i)));
    show();
  }
  function switchTab(name) {
    mode = name;
    search.value = "";
    tabs.replaceChildren();
    for (const t of ["入门练习", "决斗规则", "积木图鉴", "练习桌"])
      tabs.append(button(t, () => switchTab(t), t === name ? "active" : ""));
    filter();
  }
  bar.append(el("span", "", "章节"), selectChapter);
  main.replaceChildren(
    group(
      "guide-shell",
      tabs,
      group("guide-content", search, bar, reader, tools),
      group(
        "foot",
        button("返回 DIY 工作台", () => ctx.go("workbench"), "align-right")
      )
    )
  );
  switchTab(mode);
}
