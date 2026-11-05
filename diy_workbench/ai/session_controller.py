"""会话选择、草稿与附件的界面协调，不参与卡片批次的存储。"""

from PyQt5.QtCore import QObject

from . import card_context
from .session_store import SessionStore
from .session_view import SessionDialog
from .settings import settings_path

LEGACY_PREFIX_NOTICE = "已保留旧会话前缀；新建对话可使用新版积木目录和意图式测试工具。"


class Sessions(QObject):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller, self.panel = controller, controller.panel
        self.store = SessionStore(controller.files, settings_path().parent / "AI会话", self)
        self.store.opened.connect(self._opened)
        self.store.failed.connect(self.panel.status.setText)
        self.panel.history_requested.connect(self.show_list)
        self.panel.attachment_changed.connect(self.attach)
        self.panel.target_requested.connect(self.jump)
        self.dialog = None

    def initialize(self):
        manager = getattr(self.controller.app, "card_tab_manager", None)
        sources = []
        if manager:
            from language_switch import _card_uid
            for pack in manager.packs:
                for tab in pack["tabs"]:
                    legacy = (tab.get("diy") or {}).get("ai")
                    if isinstance(legacy, dict):
                        sources.append((_card_uid(manager, tab), tab.get("title", "卡片"), legacy))
        self.store.initialize(sources)

    def _opened(self, record):
        ctl = self.controller
        if ctl.closing:
            return
        ctl._save()
        ctl.record = record
        ctl.changes.bind_record(record)
        self.panel.show_session(ctl.tab, record)
        self.location()
        self.panel.set_busy(ctl.worker is not None, True)
        if ctl.worker is None and ctl.loaded and not ctl._configuration_note():
            prefix = record.get("prefix")
            if prefix and ("YGODIY_BLOCK_REFERENCE_V2" not in prefix.get("system", "") or "YGODIY_INTENT_TEST_V1" not in prefix.get("system", "")):
                self.panel.status.setText(LEGACY_PREFIX_NOTICE)
            elif self.panel.status.text() == LEGACY_PREFIX_NOTICE:
                self.panel.status.clear()
        ctl._update_context()

    def location(self):
        ctl = self.controller
        mode = card_context.active_mode(ctl.app)
        record = ctl.record or {}
        name = ((ctl.tab or {}).get("data") or {}).get("name") or (ctl.tab or {}).get("title") or "未选择卡片"
        self.panel.set_attachment(name, mode["label"], record.get("attached", True) and ctl.tab is not None)

    def attach(self, enabled):
        if self.controller.record is not None:
            self.controller.record["attached"] = enabled
            self.controller._schedule_save()
            self.location()
            self.controller._update_context()

    def show_list(self):
        ctl = self.controller
        ctl._save()
        dialog = self.dialog = SessionDialog(self.store, self.panel)
        dialog.delete_requested.connect(self.delete)
        dialog.exec_()
        self.dialog = None
        dialog.deleteLater()

    def delete(self, uid):
        ctl = self.controller
        if ctl.target is not None and ctl.target.get("id") == uid:
            ctl.cancel()
        self.store.delete(uid)

    def new(self):
        self.controller._save()
        self.store.create()

    def jump(self, uid, mode):
        operations = self.controller.operations
        try:
            pi, ti, _ = operations._find(uid)
            manager = self.controller.app.card_tab_manager
            manager.pack_list.setCurrentRow(pi)
            manager.tab_list.setCurrentRow(ti)
            target = next(item for item in card_context.modes(self.controller.app) if item["id"] == mode)
            self.controller.app.combo_box.setCurrentIndex(target["index"])
        except (ValueError, KeyError, StopIteration):
            self.panel.status.setText("记录中的目标卡片或模式已不存在。")
