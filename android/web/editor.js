import { el, button, group, field, input, select, ask, sheet, closeSheet, message } from "./dom.js";
import { CALLS, MT, frameName } from "./project.js";
import { exportSheet } from "./library.js";

const indexed = (options) => options.map((v, i) => [i, v]);
const COLOR_OPTIONS = [
  ["黑色", "#000000"],
  ["白色", "#ffffff"],
  ["金色", "#d5a72d"],
  ["红色", "#e12820"]
];
const ATTR_COLORS = ["#f3da65", "#89669f", "#87ab6a", "#74b9d4", "#d96e65", "#9c8981", "#c6b58e"];
export function editor(panel, ctx) {
  const { card: c, assets, state, save, redraw, side } = ctx,
    d = c.data,
    s = c.style;
  const form = el("div", "qtform");
  panel.replaceChildren(form);
  function set(obj, k, v, rebuild = false) {
    obj[k] = v;
    save();
    redraw();
    if (k === "name") side();
    if (rebuild) show();
  }
  function line(...parts) {
    return group("qtrow", ...parts);
  }
  function label(caption, widget, cls = "") {
    const l = el("label", cls);
    l.append(caption + " ", widget);
    return l;
  }
  function text(obj, k, placeholder = "", cls = "") {
    const v = input(obj[k], (value) => set(obj, k, value));
    v.placeholder = placeholder;
    v.className = cls;
    return v;
  }
  function choices(obj, k, options, number = false) {
    return select(options, obj[k], (v) => set(obj, k, number ? Number(v) : v, true));
  }
  function crop(enabled) {
    const controls = group("stack");
    for (const [k, name, min, max, step] of [
      ["zoom", "缩放", 1, 3, 0.05],
      ["x", "水平位置", 0, 100, 1],
      ["y", "垂直位置", 0, 100, 1]
    ]) {
      const slider = input(s[k], (v) => set(s, k, Number(v)), "range");
      Object.assign(slider, { min, max, step, value: s[k] });
      controls.append(field(name, slider));
    }
    if (enabled)
      controls.append(
        button("选择新卡图", () => {
          closeSheet();
          Documents.pickImage(c.id);
        })
      );
    sheet("裁剪卡图", controls);
  }
  function artRow() {
    const adjust = button("调整卡图", () => crop(true));
    adjust.dataset.crop = "true";
    return line(
      button("上传卡图(不裁剪)", () => ctx.pickArt(false)),
      button("上传卡图(裁剪)", () => ctx.pickArt(true)),
      adjust,
      button("清除卡图", () => {
        c.art = "";
        s.demo = false;
        save();
        redraw();
      })
    );
  }
  function quick(textarea) {
    const bar = group("qtrow symbols");
    for (const txt of state.shortcuts)
      bar.append(
        button(txt, () => {
          const start = textarea.selectionStart,
            end = textarea.selectionEnd;
          textarea.setRangeText(
            txt === "「」" ? "「" + textarea.value.slice(start, end) + "」" : txt,
            start,
            end,
            "end"
          );
          if (txt === "「」" && start === end) textarea.setSelectionRange(start + 1, start + 1);
          set(d, "effect_text", textarea.value);
          textarea.focus();
        })
      );
    bar.append(
      button("自定义…", () =>
        ask(
          "快捷文字按钮",
          "用中文逗号分隔各个按钮的文字。",
          (v) => {
            state.shortcuts = [
              ...new Set(
                v
                  .split(/[\n，,]/)
                  .map((x) => x.trim())
                  .filter(Boolean)
              )
            ].slice(0, 22);
            save();
            show();
          },
          state.shortcuts.join("，")
        )
      )
    );
    return bar;
  }
  function uploadAndStyle() {
    const row = group("qtrow color-row", el("span", "", "卡名颜色："));
    for (const [name, hex] of COLOR_OPTIONS) {
      const b = button("", () => set(s, "ink", hex, true), "swatch"),
        i = el("i");
      i.style.background = hex;
      b.append(i, name);
      row.append(b);
    }
    row.append(
      label(
        "其他",
        input(s.ink || "#161616", (v) => set(s, "ink", v), "color")
      ),
      button("自动", () => set(s, "ink", "", true))
    );
    return [row, artRow()];
  }
  function basic() {
    const type = choices(d, "card_type", indexed(["怪兽卡", "魔法卡", "陷阱卡"]), true);
    const nameRow = line(label("卡名", text(d, "name", "请输入卡名"), "grow"), label("类型", type));
    if (s.mode === "ocg")
      nameRow.append(
        label(
          "卡模",
          choices(s, "template", [
            ["official", "官方"],
            ["new", "经典"]
          ])
        )
      );
    if (s.mode === "past") nameRow.append(label("第几期", choices(s, "series", Object.keys(assets.past))));
    const lang = select(
      [
        ["0", "简体中文"],
        ["1", "繁体中文"]
      ],
      s.language || "0",
      (v) => {
        if (v === "0" || v === "1")
          for (const key of ["name", "effect_text", "lb_text"]) d[key] = Documents.chinese(d[key], v === "1");
        set(s, "language", v, true);
        side();
      }
    );
    form.append(nameRow, line(label("语言", lang)), ...uploadAndStyle());
    if (!d.card_type) {
      form.append(
        group(
          "qtrow detail-row",
          el("span", "", "详细"),
          choices(d, "race", indexed(assets.races), true),
          choices(d, "call_way", indexed(CALLS), true),
          choices(
            d,
            "extra1",
            indexed(["", "通常", "调整", "二重", "灵魂", "反转", "特殊召唤", "同盟", "卡通", "灵摆"]),
            true
          ),
          choices(
            d,
            "extra2",
            indexed(["", "通常", "调整", "二重", "灵魂", "反转", "特殊召唤", "同盟", "卡通", "灵摆"]),
            true
          )
        ),
        line(label("自定义种族", text(s, "raceText", "输入种族名"), "grow"))
      );
      const attrs = line(el("span", "", "属性："));
      Array.from("光暗风水炎地神").forEach((a, i) => {
        const b = button(a, () => set(d, "attribute", a, true), "attr");
        b.style.background = ATTR_COLORS[i];
        b.setAttribute("aria-pressed", d.attribute === a);
        attrs.append(b);
      });
      form.append(attrs);
      if (d.call_way === 7) {
        const arrows = line(el("span", "", "连接箭头"));
        Array.from("↖↑↗←→↙↓↘").forEach((a, i) =>
          arrows.append(
            button(
              a,
              () => {
                d.link_status[i] = !d.link_status[i];
                set(d, "link_status", d.link_status, true);
              },
              d.link_status[i] ? "is-selected" : ""
            )
          )
        );
        form.append(arrows);
      } else {
        const key = d.call_way === 5 ? "rank" : "level",
          title = key === "rank" ? "阶级" : "等级";
        const stars = group("qtrow starrow", el("span", "", title + " " + d[key]));
        for (let i = 0; i <= 13; i++) {
          const b = button(i ? "✪" : "×", () => set(d, key, i, true), i <= d[key] && i ? "filled" : "");
          b.setAttribute("aria-label", title + " " + i);
          stars.append(b);
        }
        form.append(stars);
      }
      form.append(
        line(
          label("攻击", text(d, "ATK", "ATK", "stat")),
          ...(d.call_way === 7 ? [] : [label("防御", text(d, "DEF", "DEF", "stat"))])
        )
      );
      if (frameName(d).endsWith("灵摆"))
        form.append(
          line(
            label(
              "灵摆刻度",
              choices(
                d,
                "lb_level",
                Array.from({ length: 14 }, (_, i) => String(i))
              )
            )
          ),
          field(
            "灵摆效果",
            input(d.lb_text, (v) => set(d, "lb_text", v), "textarea")
          )
        );
    } else
      form.append(
        line(
          el("span", "", "类别"),
          choices(
            d,
            "mt_type",
            indexed(MT).filter(([i]) => (d.card_type === 1 ? i !== 5 : [0, 1, 5].includes(i))),
            true
          )
        )
      );
    const effect = input(d.effect_text, (v) => set(d, "effect_text", v), "textarea");
    effect.className = "effect-text";
    effect.placeholder = "效果";
    effect.setAttribute("aria-label", "效果文字");
    form.append(
      quick(effect),
      effect,
      line(
        label(
          "效果字号",
          choices(
            s,
            "size",
            Array.from({ length: 36 }, (_, i) => [i - 15, (i - 15 > 0 ? "+" : "") + (i - 15)]),
            true
          )
        ),
        label(
          "卡名对齐",
          choices(s, "align", [
            ["left", "左对齐"],
            ["center", "居中"],
            ["right", "右对齐"]
          ])
        )
      ),
      line(label("卡密", text(d, "cardpass"), "grow"), label("卡包", text(d, "cardpack"), "grow")),
      line(label("版权", text(s, "copyright", "自定义版权名称"), "grow"))
    );
  }
  function show() {
    form.replaceChildren();
    if (["field", "back"].includes(s.mode)) {
      const back = s.mode === "back";
      form.append(
        line(
          label(
            back ? "卡背" : "底纹",
            choices(s, back ? "back" : "field", Object.keys(back ? assets.back : assets.field))
          )
        ),
        artRow(),
        line(label("名称", text(d, "name"), "grow")),
        line(label("版权", text(s, "copyright"), "grow"))
      );
    } else {
      basic();
      if (s.mode === "manga")
        form.append(
          line(
            label(
              "卡图",
              select(
                [
                  ["mono", "黑白"],
                  ["color", "彩色"]
                ],
                s.mono ? "mono" : "color",
                (v) => set(s, "mono", v === "mono")
              )
            )
          )
        );
    }
    form.append(
      line(
        button("导出数据", () => ctx.exportProject(true)),
        button("导入数据", () => Documents.importPack())
      ),
      line(
        button("导出图片", () => exportSheet(ctx)),
        button("导出设置", () => exportSheet(ctx))
      )
    );
  }
  show();
}
