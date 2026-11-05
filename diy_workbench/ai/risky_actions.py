"""删除、导出、安装：模型只能提出请求，每一次都由玩家在弹窗里确认；自动应用不起作用。"""

import os
import time
from dataclasses import dataclass, field

from PyQt5.QtWidgets import QFileDialog, QMessageBox

from sandbox.test_data import coverage

CONFIRM_TIMEOUT = 3600
EXPORT_TIMEOUT = 900
UNVERIFIED_NOTE = "仍然继续会在卡包里标记「未通过验证」。"


@dataclass
class PendingAction:
    kind: str
    title: str
    lines: list
    target: object
    unverified: list = field(default_factory=list)


class RiskyActions:
    def __init__(self, operations):
        self.operations = operations

    @property
    def project(self):
        return self.operations.changes.project

    def delete_card(self, card_uid):
        pi, _, tab = self.operations._find(card_uid)
        pack = self.project.manager.packs[pi]
        lines = ["卡片：%s" % tab.get("title", ""), "卡包：%s" % pack.get("title", ""), "删除后不能撤销。"]
        if len(pack.get("tabs", [])) == 1:
            lines.insert(2, "这是卡包里最后一张卡，卡包也会一起删除。")
        return PendingAction("delete_card", "删除卡片", lines, card_uid)

    def delete_pack(self, pack_id):
        pack = self.project.pack(pack_id)
        names = [tab.get("title", "") for tab in pack.get("tabs", [])]
        lines = ["卡包：%s" % pack.get("title", ""), "共 %d 张卡：%s" % (len(names), "、".join(names[:20]) + ("……" if len(names) > 20 else "")),
                 "删除后不能撤销。"]
        return PendingAction("delete_pack", "删除卡包", lines, pack_id)

    def unverified(self, pack):
        rows = []
        for tab in pack.get("tabs", []):
            document = dict(tab, data=self.project.data(tab))
            if ((document.get("diy") or {}).get("blocks") or {}).get("effects"):
                proof = coverage(document)
                if not proof["verified"]:
                    rows.append("%s：测试通过 %d/%d 项" % (tab.get("title", ""), proof["passed"], proof["total"]))
        return rows

    def export_pack(self, pack_id):
        pack = self.project.pack(pack_id)
        rows = self.unverified(pack)
        return PendingAction("export_pack", "导出卡包", ["卡包：%s（%d 张卡）" % (pack.get("title", ""), len(pack.get("tabs", []))),
                                                     "下一步由你选择保存位置。"], pack_id, rows)

    def install_pack(self, pack_id):
        from ygopack import build, mdpro3
        pack = self.project.pack(pack_id)
        target, note = mdpro3.expansions_dir()
        if not target:
            raise ValueError("不能安装：%s" % note)
        path = os.path.join(target, "ygodiy-" + build.slug(pack.get("title") or "DIY") + ".ypk")
        lines = ["卡包：%s（%d 张卡）" % (pack.get("title", ""), len(pack.get("tabs", []))), "安装到：%s" % path]
        if os.path.exists(path):
            lines.append("这个文件已经存在，会被覆盖。")
        return PendingAction("install_pack", "安装到 MDPro3", lines, pack_id, self.unverified(pack))

    def delete(self, action):
        manager = self.project.manager
        selected_pack, selected_card = self.project.selection()
        if action.kind == "delete_card":
            pi, ti, tab = self.operations._find(action.target)
            manager.pack_list.setCurrentRow(pi)
            manager.tab_list.setCurrentRow(ti)
            manager.delete_tab()
            removed = tab.get("title", "")
        else:
            pack = self.project.pack(action.target)
            removed = pack.get("title", "")
            manager.pack_list.setCurrentRow(next(i for i, item in enumerate(manager.packs) if item is pack))
            manager.delete_pack()
        for pi, pack in enumerate(manager.packs):        # 删的不是玩家正在看的卡时，回到原来的位置
            for ti, tab in enumerate(pack.get("tabs", [])):
                if tab is selected_card:
                    manager.pack_list.setCurrentRow(pi)
                    manager.tab_list.setCurrentRow(ti)
        return {"deleted": removed, "note": "已按玩家确认删除。"}

    def still_valid(self, action):
        if action.kind == "delete_card":
            self.operations._find(action.target)
        else:
            self.project.pack(action.target)


class RiskyController:
    def __init__(self, controller):
        self.controller = controller

    @property
    def actions(self):
        return self.controller.operations.risky

    def ask(self, action, extra=None):
        box = QMessageBox(self.controller.panel)
        box.setWindowTitle("确认：" + action.title)
        box.setText("AI 请求%s。\n\n%s" % (action.title, "\n".join(action.lines)))
        rows = list(extra or action.unverified)
        if rows:
            box.setInformativeText("以下内容没有通过验证：\n%s\n\n%s" % ("\n".join(rows[:12]), UNVERIFIED_NOTE))
        accept = box.addButton("仍然继续" if rows else "确认", QMessageBox.AcceptRole)
        cancel = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec_()
        return box.clickedButton() is accept

    def _stopped(self, request):
        worker = self.controller.worker
        return worker is None or worker.cancel_flag.is_set() or time.monotonic() > request["expires_at"]

    def resolve(self, request, result):
        action = result.get("data")
        if not isinstance(action, PendingAction):
            return result
        request["expires_at"] = time.monotonic() + CONFIRM_TIMEOUT
        if not self.ask(action):
            return {"ok": False, "error": "玩家取消了这次操作，没有执行。", "error_code": "player_declined"}
        if self._stopped(request):
            return {"ok": False, "error": "请求已停止，操作没有执行。"}
        try:
            self.actions.still_valid(action)
        except ValueError as error:
            return {"ok": False, "error": str(error)}
        if action.kind in ("delete_card", "delete_pack"):
            return {"ok": True, "risk": "confirm", "data": self.actions.delete(action)}
        save_to = None
        if action.kind == "export_pack":
            pack = self.actions.project.pack(action.target)
            save_to, _ = QFileDialog.getSaveFileName(self.controller.panel, "导出卡包", "ygodiy-%s.ypk" % pack.get("title", "DIY"), "卡包 (*.ypk)")
            if not save_to:
                return {"ok": False, "error": "玩家取消了这次操作，没有执行。", "error_code": "player_declined"}
        self._run(request, action, save_to, list(action.unverified))
        return None

    def _run(self, request, action, save_to, marks):
        pack = self.actions.project.pack(action.target)
        request["expires_at"] = time.monotonic() + EXPORT_TIMEOUT
        def finished(ok, lines, summary, verify_failed):
            try:
                if verify_failed:
                    failures = [text for mark, text in lines if mark == "×"] or ["沙盒加载检查没有通过"]
                    request["expires_at"] = time.monotonic() + CONFIRM_TIMEOUT
                    if self.ask(action, failures) and not self._stopped(request):
                        self._run(request, action, save_to, marks + failures)
                        return
                output = {"ok": ok, "risk": "confirm", "data": {"summary": summary, "marked_unverified": bool(marks) and ok,
                                                               "lines": [text for _, text in lines][:20]}}
                if not ok:
                    output = {"ok": False, "error": summary}
                self.controller._operation_done(request, output)
            except Exception:
                request["result"] = {"ok": False, "error": "导出结果未能附回当前请求，请查看卡包页。"}
            request["ready"].set()
        self.controller.app._workbench._export(action.kind == "install_pack", pack, save_to, marks, finished)
