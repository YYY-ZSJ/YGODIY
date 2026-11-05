"""沙盒工具的异步桥接及失败反例确认；不持有网络Key。"""

import json
import re
import time

from PyQt5.QtWidgets import QMessageBox

from .sandbox_process import SCENE_TIMEOUT, SandboxWorker
from .sandbox_tools import SandboxJob, ScenarioEdit


class SandboxController:
    def __init__(self, controller):
        self.controller = controller
        self.worker = None

    def resolve(self, request, result):
        data = result.get("data")
        if isinstance(data, ScenarioEdit):
            from .sandbox_view import expectation_text
            box = QMessageBox(self.controller.panel)
            box.setWindowTitle("修改已失败的测试反例")
            box.setText("「%s」%s。\n这次修改可能避开原来的错误。是否允许生成这项修改候选？" % (data.before["name"], data.reason))
            before = "；".join(expectation_text(c) for c in data.before["expect"][:4])
            after = "；".join(expectation_text(c) for c in data.after["expect"][:4])
            box.setInformativeText("原文：%s\n原预期：%s\n新预期：%s\n默认保留原反例；完整布场和意图差异可展开详情。" % (data.before["basis"], before, after))
            box.setDetailedText("修改前：\n" + json.dumps(data.before, ensure_ascii=False, indent=2) +
                                "\n修改后：\n" + json.dumps(data.after, ensure_ascii=False, indent=2))
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            if box.exec_() != QMessageBox.Yes:
                return {"ok": False, "error": "玩家保留了已失败反例；可修积木或追加更强情景。", "error_code": "scenario_edit_declined"}
            if (self.controller.worker is None or self.controller.worker.cancel_flag.is_set()
                    or time.monotonic() > request["expires_at"]):
                return {"ok": False, "error": "请求已停止或超时，情景修改未执行。"}
            return {"ok": True, "risk": "modify", "data": self.controller.operations.sandbox.write(data.after, data.uid, approved=True)}
        if not isinstance(data, SandboxJob):
            return result
        if self.worker is not None:
            return {"ok": False, "error": "沙盒仍在结束上一项任务，请稍后再试。"}
        ctl = self.controller
        answer, target, job = ctl.answer, ctl.target, data
        request["expires_at"] = time.monotonic() + (SCENE_TIMEOUT + 3) * len(job.scenarios) + 30
        self.worker = worker = SandboxWorker(job.document, job.scenarios, ctl.panel)
        request["sandbox_worker"] = worker
        record_errors = []
        def progress(result):
            result = dict(result, card_uid=job.uid)
            answer["test_reports"] = answer.get("test_reports", []) + [result]
            try:
                saved = ctl.operations.sandbox.record(job, result)
                if not saved["ok"]:
                    record_errors.append(saved["error"])
            except Exception as error:
                record_errors.append(str(error) if isinstance(error, ValueError) else "测试结果写入候选时发生异常。")
            ctl.sessions.store.save(target)
            ctl._render()
        def completed(value):
            try:
                if value.get("error") or record_errors:
                    output = {"ok": False, "error": value.get("error") or "结果已收到，但未写入候选：" + "；".join(record_errors),
                              "error_code": "sandbox_unavailable"}
                else:
                    verification = ctl.operations.sandbox.evidence(job.uid) if ctl.operations.changes.current is job.plan else {}
                    output = {"ok": True, "risk": "modify", "data": {
                        "status": "applied" if job.plan.auto else "pending", "affected_modes": ["DIY 工作台"],
                        "results": value["results"], "cancelled": value.get("cancelled"), "verification": verification,
                        "note": "只对已完成的情景有测试证据；缺项/过期/执行受阻均未验证。"}}
                ctl._operation_done(request, output)
            except Exception:
                request["result"] = {"ok": False, "error": "沙盒结果未能附回当前请求，已完成情景保留在调用记录。"}
            finally:
                request["ready"].set()
        def finished():
            self.worker = None
            worker.deleteLater()
            ctl._close_when_idle()
        worker.progressed.connect(progress)
        worker.completed.connect(completed)
        worker.finished.connect(finished)
        ctl.panel.status.setText("正在按意图运行沙盒；可以停止。")
        worker.start()
        return None

    def cancel(self):
        if self.worker is not None:
            self.worker.cancel()

    def show_results(self, uid):
        from .sandbox_view import TestDialog
        try:
            document, pending = self.controller.operations.sandbox.saved_document(uid)
        except ValueError as error:
            self.controller.panel.status.setText(str(error))
            return
        TestDialog(document, pending, self.controller.panel).exec_()

    def bind_evidence(self, answer):
        plan = self.controller.operations.changes.current
        if plan is None:
            return ""
        touches = any(c["key"][-1] in ("blocks", "tests", "effect_text", "design_text") for c in plan.cells.values())
        claim = bool(re.search(r"已实现|与原文一致|全部.*通过|完全.*一致", answer.get("text", "")))
        if not touches and not claim:
            return ""
        targets = {r["card_uid"] for r in answer.get("test_reports", []) if r.get("card_uid")}
        targets.update(c["key"][1] for c in plan.cells.values() if c["key"][0] != "editor" and c["key"][-1] in ("blocks", "tests", "effect_text", "design_text"))
        if not targets and plan.target:
            targets.add(plan.target)
        if not targets:
            return "没有卡片测试证据；未验证。"
        values = [self.controller.operations.sandbox.evidence(uid) for uid in sorted(targets)]
        evidence = {"requirements": [r for value in values for r in value["requirements"]],
                    "unverified_scenarios": [r for value in values for r in value["unverified_scenarios"]],
                    "passed": sum(value["passed"] for value in values), "total": sum(value["total"] for value in values),
                    "verified": all(value["verified"] for value in values)}
        answer["verification"] = evidence
        return "尚有未验证或过期的边界，请查看测试清单；不能据此认定整张卡与原文完全一致。" if not evidence["verified"] else ""

    def shutdown(self):
        self.cancel()
        if self.worker is not None:
            self.worker.wait()
