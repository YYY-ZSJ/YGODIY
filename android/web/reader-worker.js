/* 中文读法在独立线程运行，首次打开积木时才装入。所有文件来自 APK。 */
importScripts("runtime/pyodide.js");
let engine;
async function start() {
  const base = new URL("runtime/", self.location.href).href;
  const py = await loadPyodide({ indexURL: base, stdLibURL: base + "stdlib.data" });
  const response = await fetch("reader.py");
  if (!response.ok) throw Error("缺少中文积木资料");
  py.runPython(await response.text());
  return py.globals.get("render_text");
}
self.onmessage = async ({ data }) => {
  try {
    if (!engine)
      engine = start().catch((error) => {
        engine = null;
        throw error;
      });
    const render = await engine;
    self.postMessage({ id: data.id, text: JSON.parse(render(JSON.stringify(data.model))) });
  } catch (error) {
    self.postMessage({
      id: data.id,
      error: "未能生成文字，请检查积木参数，或更新系统 WebView 后重试。",
      detail: error.message || String(error)
    });
  }
};
