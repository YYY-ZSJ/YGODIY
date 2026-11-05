"""两个沙盒工具的卡片适配；沿用已有候选、冲突检测和批次撤销。"""

import copy
from dataclasses import dataclass

from sandbox.test_data import MAX_SCENARIOS, coverage, intent_text, revision, suite, validate
from sandbox.test_templates import effect_texts


@dataclass
class SandboxJob:
    uid: str
    plan: object
    document: dict
    scenarios: list


@dataclass
class ScenarioEdit:
    uid: str
    before: dict
    after: dict
    reason: str


class SandboxTools:
    def __init__(self, operations):
        self.operations = operations

    def document(self, card_uid=None):
        plan = self.operations.changes.current
        if plan is None:
            raise ValueError("测试必须属于当前请求的卡片快照。")
        uid = card_uid or plan.target
        return plan, uid, plan.working_document(uid)

    def write(self, scenario, card_uid=None, approved=False):
        plan, uid, document = self.document(card_uid)
        text = intent_text(document)
        scene = validate(scenario, text)
        tests = suite(document)
        numbers = [n for n, _, _ in effect_texts(text)]
        if scene["effect"] not in numbers:
            raise ValueError("原文中没有这个编号效果。")
        preceding = [n for n in numbers if n < scene["effect"]]
        if any(not any(r.get("effect") == n for r in tests["results"]) for n in preceding):
            raise ValueError("请按编号分批：先为前一个效果写少量情景并运行，保留结果后再处理下一个。")
        previous = next((s for s in tests["scenarios"] if s["id"] == scene["id"]), None)
        frozen = any(r.get("scenario_id") == scene["id"] and any(c.get("completed") and not c.get("passed")
                     for c in r.get("checks", [])) for r in tests.get("results", []))
        if previous is not None and scene != previous:
            unchanged = {k: v for k, v in previous.items() if k not in ("expect", "name")} == {k: v for k, v in scene.items() if k not in ("expect", "name")}
            stronger = unchanged and scene["expect"][:len(previous["expect"])] == previous["expect"]
            semantic_change = (any(scene.get(k) != previous.get(k) for k in ("effect", "template", "basis"))
                               or scene["expect"][:len(previous["expect"])] != previous["expect"])
            if (semantic_change or (frozen and not stronger)) and not approved:
                return ScenarioEdit(uid, previous, scene, "已实际执行断言并失败" if frozen else "将改变原文要求或已有预期")
            if approved:
                tests.setdefault("edits", []).append({"before": previous, "after": scene, "player_approved": True})
        if previous is None and len(tests["scenarios"]) >= MAX_SCENARIOS:
            raise ValueError("每张卡最多60个情景，请先整理已有情景。")
        tests["scenarios"] = [scene if s["id"] == scene["id"] else s for s in tests["scenarios"]]
        if previous is None:
            tests["scenarios"].append(scene)
        return self.operations.changes.stage("tests", tests=tests, card_uid=uid)

    def prepare(self, effect, card_uid=None, scenario_id=None):
        plan, uid, document = self.document(card_uid)
        scenes = [s for s in suite(document)["scenarios"] if s["effect"] == effect and (scenario_id is None or s["id"] == scenario_id)]
        if not scenes:
            raise ValueError("该编号效果还没有情景，请先用write_test_scenario逐个写入。")
        diy = document.get("diy") or {}
        payload = {"_card_uid": uid, "data": {k: copy.deepcopy(v) for k, v in document.get("data", {}).items() if k not in ("image", "_image_ref")},
                   "diy": {k: copy.deepcopy(diy[k]) for k in ("blocks", "setcodes", "design_text", "script") if k in diy}}
        return SandboxJob(uid, plan, payload, scenes)

    def record(self, job, result):
        if self.operations.changes.current is not job.plan:
            return {"ok": False, "error": "请求已结束；已完成测试仍保留在调用记录，未写入新的批次。"}
        document = job.plan.working_document(job.uid)
        tests = suite(document)
        tests["results"].append(copy.deepcopy(result))
        return {"ok": True, "risk": "modify", "data": self.operations.changes.stage("tests", tests=tests, card_uid=job.uid)}

    def evidence(self, card_uid=None):
        plan, uid, document = self.document(card_uid)
        proof = coverage(document)
        try:
            tab = self.operations._find(uid)[2]
            live = dict(tab, data=self.operations.changes.project.data(tab))
            stale = revision(live) not in (revision(plan.cards[uid]), revision(document))
        except ValueError:
            stale = not any((c["kind"] == "card" and c["document"]["_card_uid"] == uid) or
                (c["kind"] == "pack" and any(t["_card_uid"] == uid for t in c["document"]["tabs"])) for c in plan.creations)
        if stale:
            proof.update(verified=False, passed=0, notice="请求期间卡片已被玩家修改或删除；本次测试针对旧快照，当前卡未验证。")
            for item in proof["requirements"]:
                if item["status"] == "通过":
                    item["status"] = "过期"
        return proof

    def saved_document(self, uid):
        for plan in reversed(list(self.operations.changes.plans.values())):
            changed = any(c["key"][0] != "editor" and c["key"][1] == uid for c in plan.cells.values())
            created = any((c["kind"] == "card" and c["document"]["_card_uid"] == uid) or
                (c["kind"] == "pack" and any(t["_card_uid"] == uid for t in c["document"]["tabs"])) for c in plan.creations)
            if plan.state == "pending" and (changed or created):
                return plan.working_document(uid), True
        tab = self.operations._find(uid)[2]
        return dict(tab, data=self.operations.changes.project.data(tab)), False

    def progress(self, document):
        tests = suite(document)
        return {"scenarios": [{k: s[k] for k in ("id", "effect", "name", "template")} for s in tests["scenarios"]],
                **coverage(document, tests)}
