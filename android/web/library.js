import { el, group, button, sheet, closeSheet, message } from "./dom.js";
import { manifest } from "./project.js";
import { paint, printBleed } from "./render.js";
function fileName(s) {
  return (s || "YGODIY").replace(/[\\/:*?"<>|\x00-\x1f]/g, "_").slice(0, 76);
}
export function exportProject(ctx, single) {
  const { card, pack } = ctx;
  Documents.exportPack(
    fileName(single ? card.data.name : pack.name) + ".ydiy",
    JSON.stringify(manifest(pack, single ? [card] : pack.cards, single))
  );
}
export function exportSheet(ctx) {
  const { state, card, assets, save } = ctx;
  const check = el("input");
  check.type = "checkbox";
  check.checked = state.bleed;
  check.onchange = () => {
    state.bleed = check.checked;
    save();
  };
  const line = el("label");
  line.append(check, " 四周延伸 3 毫米，附裁切标记");
  const png = button(
    "保存卡图 PNG",
    async () => {
      png.disabled = true;
      try {
        const canvas = el("canvas");
        await paint(canvas, card, assets);
        Documents.exportImage(
          fileName(card.data.name) + ".png",
          (state.bleed ? printBleed(canvas) : canvas).toDataURL("image/png").split(",")[1]
        );
        closeSheet();
      } catch (e) {
        message(e.message);
      } finally {
        png.disabled = false;
      }
    },
    "primary"
  );
  sheet("导出图片", group("stack", line, png));
}
