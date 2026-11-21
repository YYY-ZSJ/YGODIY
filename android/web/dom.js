export const $ = (id) => document.getElementById(id);
export function el(tag, cls = "", text = "") {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== "") node.textContent = text;
  return node;
}
export function button(label, click, cls = "") {
  const b = el("button", cls, label);
  b.type = "button";
  b.onclick = click;
  return b;
}
export function field(title, node, wide = false) {
  const label = el("label", "field" + (wide ? " wide" : ""));
  label.append(document.createTextNode(title), node);
  return label;
}
export function input(value, change, type = "text") {
  const n = el(type === "textarea" ? "textarea" : "input");
  if (type !== "textarea") n.type = type;
  n.value = value ?? "";
  n.oninput = () => change(n.value);
  return n;
}
export function select(options, value, change) {
  const n = el("select");
  for (const option of options) {
    const [key, label] = Array.isArray(option) ? option : [option, option];
    n.add(new Option(label, key));
  }
  n.value = value;
  n.onchange = () => change(n.value);
  return n;
}
export function group(cls, ...children) {
  const d = el("div", cls);
  d.append(...children);
  return d;
}
export function sheet(title, content) {
  $("sheet-title").textContent = title;
  $("sheet-body").replaceChildren(content);
  $("sheet-body").scrollTop = 0;
  if (!$("sheet").open) $("sheet").showModal();
}
export function closeSheet() {
  $("sheet").close();
}
let timer;
export function message(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(timer);
  timer = setTimeout(() => t.classList.remove("show"), 2900);
}
export function ask(title, label, ok, value) {
  const entry = input(value ?? "", () => {});
  const action = button(
    "确定",
    () => {
      if (value !== undefined && !entry.value.trim()) {
        entry.focus();
        return;
      }
      closeSheet();
      ok(entry.value.trim());
    },
    "primary"
  );
  sheet(
    title,
    group(
      "stack",
      el("p", "", label),
      ...(value === undefined ? [] : [entry]),
      group("row", action, button("取消", closeSheet))
    )
  );
  if (value !== undefined) entry.focus();
}
