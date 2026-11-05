"""运行期批次的应用与撤销界面；冲突默认停止，保留手改须玩家选择。"""

from PyQt5.QtCore import QObject, Qt
from PyQt5.QtWidgets import QMenu, QMessageBox

from . import history
from .change_view import ChangeDialog, STATE_LABELS


class ChangeCoordinator(QObject):
    def __init__(self, controller):
        super().__init__(controller.panel)
        self.controller, self.panel, self.book = controller, controller.panel, controller.operations.changes
        self.book.changed.connect(self._changed)
        self.panel.change_apply_requested.connect(self.apply)
        self.panel.change_reject_requested.connect(self.reject)
        self.panel.change_undo_requested.connect(self.undo)
        self.panel.change_history_requested.connect(self.show_history)

    def _changed(self, plan):
        plan.answer["changes"]["available"] = True
        for uid, record in self.controller.sessions.store.records.items():
            if any(message is plan.answer for message in record["messages"]):
                self.controller.dirty.add(uid)
        self.controller._render()
        self.controller._schedule_save()

    def bind(self, tab):
        if tab is None:
            return
        self.bind_record(history.session(tab))

    def bind_record(self, record):
        for message in record.get("messages", []):
            if message.get("changes"):
                message["changes"]["available"] = message["changes"]["id"] in self.book.plans

    def apply(self, uid):
        if self.controller.worker is None and uid in self.book.plans:
            self.book.apply(uid)

    def reject(self, uid):
        if self.controller.worker is None and uid in self.book.plans:
            self.book.reject(uid)

    def undo(self, uid):
        if self.controller.worker is not None or uid not in self.book.plans:
            return
        reviewed = self.book.undo_review(uid)
        if not reviewed["conflicts"]:
            self.book.undo(uid)
            return
        box = QMessageBox(self.panel)
        box.setWindowTitle("撤销遇到字段冲突")
        box.setTextFormat(Qt.PlainText)
        box.setText("应用后检测到玩家改动。默认整批停止。\n\n保留项：\n" + "\n".join(reviewed["kept"]) +
                    "\n\n其余可撤销字段：%d 项；可移除的未改动新对象：%d 个。" % (len(reviewed["cells"]), len(reviewed["removals"])))
        stop = box.addButton("整批停止", QMessageBox.RejectRole)
        partial = box.addButton("撤销其余字段，保留我的手改", QMessageBox.ActionRole)
        box.setDefaultButton(stop)
        box.setEscapeButton(stop)
        box.exec_()
        if box.clickedButton() is partial:
            self.book.undo(uid, partial=True, expected=reviewed)
        else:
            self.book._fail(self.book.plans[uid], "已停止整批撤销，未修改项目。\n" + "\n".join(reviewed["conflicts"]))

    def show_history(self):
        menu = QMenu(self.panel)
        plans = [p for p in self.book.plans.values() if p.cells or p.creations]
        if not plans:
            menu.addAction("本次启动尚无 AI 修改批次").setEnabled(False)
        for plan in reversed(plans):
            action = menu.addAction("%s · %s" % ((plan.owner or {}).get("title", "卡片"), STATE_LABELS[plan.state]))
            action.triggered.connect(lambda checked=False, uid=plan.id: self._show_plan(uid))
        menu.exec_(self.panel.batch_button.mapToGlobal(self.panel.batch_button.rect().bottomLeft()))

    def _show_plan(self, uid):
        from .change_view import ChangeCard
        plan = self.book.plans[uid]
        dialog = ChangeDialog(plan.report(), self.panel)
        actions = ChangeCard(dialog)
        actions.target_requested.connect(self.controller.sessions.jump)
        actions.set_report(plan.report())
        actions.set_busy(self.controller.worker is not None)
        actions.details.hide()
        def execute(key, callback):
            callback(key)
            actions.set_report(plan.report())
            dialog.set_report(plan.report())
        for signal, callback in ((actions.apply_requested, self.apply), (actions.reject_requested, self.reject), (actions.undo_requested, self.undo)):
            signal.connect(lambda key, callback=callback: execute(key, callback))
        dialog.layout().insertWidget(1, actions)
        dialog.exec_()
