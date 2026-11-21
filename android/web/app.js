import { $, el, group, button, closeSheet, message, ask, sheet } from "./dom.js";
import { initialProject, packOf, cardOf, fromManifest, MODES } from "./project.js";
import { editor } from "./editor.js";
import { workbench } from "./workbench.js";
import { guide } from "./guide.js";
import { sidebars } from "./sidebar.js";
import { exportProject } from "./library.js";
import { paint } from "./render.js";

async function boot() {
  const [assets, library] = await Promise.all(
    ["art.json", "library.json"].map(async (path) => {
      const r = await fetch(path);
      if (!r.ok) throw Error("缺少本地文件 " + path);
      return r.json();
    })
  );
  const stored = Documents.draft(),
    state = stored ? JSON.parse(stored) : initialProject();
  if (state.version !== 1 || !state.packs?.length) throw Error("草稿格式无法读取");
  let mode = state.mode || "ocg",
    tick = 0,
    raf = 0,
    pendingCrop = false;
  const page = $("main"),
    combo = $("mode");
  for (const [key, title] of [
    ...Object.entries(MODES),
    ["workbench", "DIY 工作台"],
    ["guide", "积木入门"],
    ["support", "支持作者"]
  ])
    combo.add(new Option(title, key));
  combo.onchange = () => go(combo.value);
  function save() {
    const ok = Documents.save(JSON.stringify(state));
    if (!ok) message("草稿保存失败，请导出 .ydiy 备份。");
    return ok;
  }
  function context() {
    return {
      state,
      pack: packOf(state),
      card: cardOf(state),
      assets,
      library,
      save,
      go,
      refresh,
      redraw,
      side,
      notify: message,
      pickArt: (crop) => {
        pendingCrop = crop;
        Documents.pickImage(cardOf(state).id);
      },
      copyText,
      exportProject: (single) => exportProject(context(), single),
      workTab: (t) => {
        state.workTab = t;
        go("workbench");
      },
      focus: () => {
        state.focus = state.focus === false;
        save();
        refresh();
      }
    };
  }
  function side() {
    sidebars(context());
  }
  function redraw() {
    const token = ++tick;
    cancelAnimationFrame(raf);
    if (mode === "guide" || (mode === "workbench" && state.focus !== false)) return;
    raf = requestAnimationFrame(async () => {
      const surface = el("canvas");
      try {
        await paint(surface, cardOf(state), assets);
        if (token !== tick) return;
        const view = $("card-canvas");
        view.width = surface.width;
        view.height = surface.height;
        view.getContext("2d").drawImage(surface, 0, 0);
      } catch (e) {
        message(e.message);
      }
    });
  }
  function copyText() {
    Documents.copyText(
      [cardOf(state).data.name, cardOf(state).data.lb_text, cardOf(state).data.effect_text]
        .filter(Boolean)
        .join("\n")
    );
    message("文字已复制");
  }
  function refresh() {
    if (Object.hasOwn(MODES, mode)) mode = cardOf(state).style.mode;
    combo.value = mode;
    const wb = mode === "workbench",
      book = mode === "guide";
    $("workspace").className = book ? "guide" : wb ? "workbench" + (state.focus !== false ? " focus" : "") : "";
    $("copy-text").hidden = wb || book;
    side();
    const ctx = context();
    if (book) guide(page, ctx);
    else if (wb) workbench(page, ctx);
    else editor(page, ctx);
    redraw();
  }
  function go(next) {
    if (next === "support") {
      combo.value = mode;
      const links = el("div", "stack");
      for (const [id, name] of assets.support.entries())
        links.append(button(name[0], () => Documents.authorLink(id)));
      sheet("支持作者", links);
      return;
    }
    mode = next;
    state.mode = mode;
    if (Object.hasOwn(MODES, mode)) cardOf(state).style.mode = mode;
    save();
    refresh();
  }
  $("copy-text").onclick = copyText;
  $("close-sheet").onclick = closeSheet;
  window.receiveDocument = (e) => {
    try {
      if (e.type === "art") {
        const c = state.packs.flatMap((p) => p.cards).find((c) => c.id === e.card);
        if (c) {
          c.art = e.id;
          c.style.demo = false;
          c.style.fit = pendingCrop ? "cover" : "contain";
          save();
          refresh();
          if (pendingCrop) document.querySelector("[data-crop]")?.click();
          message("卡图已保存");
        }
      } else if (e.type === "import") {
        const { pack, skipped } = fromManifest(e.manifest, library.blocks);
        state.packs.push(pack);
        state.pack = pack.id;
        state.card = pack.cards[0].id;
        save();
        refresh();
        message(
          "已导入 " + pack.cards.length + " 张卡" + (skipped ? "，跳过 " + skipped + " 块桌面专用积木" : "")
        );
      } else message(e.text);
    } catch (error) {
      message(error.message);
    }
  };
  window.deviceBack = () => {
    if ($("sheet").open) closeSheet();
    else if (mode === "guide") go("workbench");
    else ask("退出制卡器", "草稿保存在本机，下次可继续编辑。", () => Documents.exit());
  };
  if (!stored) save();
  refresh();
  Documents.initialized();
}
boot().catch((error) => {
  $("workspace").className = "guide";
  $("main").replaceChildren(
    group(
      "box",
      el("h2", "", "无法打开编辑器"),
      el("p", "", error.message),
      button("重试", () => location.reload())
    )
  );
});
