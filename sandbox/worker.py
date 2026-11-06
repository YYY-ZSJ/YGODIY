"""本地沙盒单情景入口。输入只有卡片/情景，不读AI配置、不进行网络请求。"""

import copy
import json
from pathlib import Path
import re

from .fixtures import lower_field, prepare
from .intents import IntentRunner, expand_intents
from .test_templates import apply_template


def allowed_codes(core, text):
    quoted = set(re.findall(r"「([^」]+)」", text))
    return {code for code, name in core.names.items() if name in quoted} | {
        int(value) for value in re.findall(r"(?<!\d)\d{5,10}(?!\d)", text)}


def run_case(core, record, lua, source, text):
    from .probe import load_check
    code = record["code"]
    core.add_card(record)
    core.overrides[code] = lua.encode("utf-8")
    scene = apply_template(copy.deepcopy(source))
    codes, ref = prepare(core, code, scene.get("virtual_cards", {}), allowed_codes(core, text))
    scripts = dict(core.overrides)
    loaded, errors = load_check(core, code, lua.encode("utf-8"))
    core.overrides = scripts
    if not loaded or errors:
        return {"status": "加载失败", "errors": errors, "checks": [], "unreached_assertions": scene["expect"]}
    actions = expand_intents(scene["intents"], ref)
    for source_check in scene["expect"]:
        check = dict(source_check)
        if "card" in check:
            check["card"] = ref(check["card"])
        actions.append(check)
    field = lower_field(scene["field"], ref, codes["__filler__"])
    runner = IntentRunner(core, {"name": scene["name"], "field": field, "actions": actions, "seed": 20261022})
    try:
        runner.run()
    except Exception as error:
        runner.fail("情景执行异常：%s：%s" % (type(error).__name__, str(error)[:600]))
    result = runner.report()
    result["references"] = {name: value for name, value in codes.items() if name != "__filler__"}
    key, params = scene["template"], scene.get("parameters", {})
    proof = True
    if key == "count_exceeded":
        proof = sum(i.get("do") == "activate" and i.get("card") == code for i in runner.executed_intents) >= params.get("limit", 1)
    elif key == "decline":
        proof = code in runner.declined
    elif key.startswith("flip_"):
        proof = any(m["type"] in ("pos_change", "flipsummoning") and m.get("code") == code for m in runner.duel.log)
    if not proof and result["status"] == "通过":
        result.update(status="未验证", evidence="模板要求的实际动作没有发生，不能只凭名称算覆盖。")
    result["template_verified"] = proof
    return result


def evaluate(payload):
    from diy_workbench.store import generate
    from .core import Core
    from .test_data import intent_text, validate
    document = payload["document"]
    text = intent_text(document)
    scene = validate(payload["scenario"], text)
    generated = generate(copy.deepcopy(document))
    if generated.error:
        return {"status": "编译失败", "errors": [generated.error], "checks": [], "unreached_assertions": scene["expect"]}
    core = Core(payload["runtime"])
    return run_case(core, generated.rec, generated.lua, scene, text)


def main(source, target):
    try:
        payload = json.loads(Path(source).read_text(encoding="utf-8"))
        value = evaluate(payload)
    except Exception as error:
        value = {"status": "环境异常", "errors": [type(error).__name__ + "：" + str(error)[:1000]],
                 "checks": [], "unreached_assertions": []}
    Path(target).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    import sys

    main(sys.argv[1], sys.argv[2])
