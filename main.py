#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reconcile GUI – Main Entry (Compare + Plugins)
- Home: โฟกัสที่ Compare + Plugins
- Load Feature (.py): โหลดปลั๊กอิน (QWidget) เพิ่ม และเก็บใน plugins.json
- Manage Features: เปลี่ยนชื่อ / ซ่อนปลั๊กอินออกจาก Home (ลบจาก registry แต่ไม่ลบไฟล์จริง)
- Autoload: เปิดโปรแกรมมาโหลดปลั๊กอินจาก plugins.json อัตโนมัติ
- ใช้ธีมกลางจาก theme.py (apply_theme)
"""

import sys
import os
import json
import traceback
import importlib.util
import inspect
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

# ===== our modules =====
try:
    from theme import apply_theme
except Exception:
    def apply_theme(app):
        pass

try:
    from compare_view import CompareWindow
except Exception:
    CompareWindow = None

APP_TITLE = "Reconcile GUI – Compare • Plugins"


# =========================
# BigButton (ปุ่มเมนูใหญ่)
# =========================
class BigButton(QtWidgets.QPushButton):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setMinimumHeight(110)

        container = QtWidgets.QWidget(self)
        lay = QtWidgets.QVBoxLayout(container)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)

        lbl_title = QtWidgets.QLabel(title)
        f = lbl_title.font()
        f.setPointSize(18)
        f.setBold(True)
        lbl_title.setFont(f)

        lbl_sub = QtWidgets.QLabel(subtitle)
        lbl_sub.setStyleSheet("color:#6b7280;")
        lbl_sub.setWordWrap(True)

        lay.addWidget(lbl_title)
        lay.addWidget(lbl_sub)

        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(container)


# =========================
# Home Page
# =========================
class HomePage(QtWidgets.QWidget):
    goCompare = QtCore.pyqtSignal()
    requestLoadPlugin = QtCore.pyqtSignal()
    requestManagePlugins = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        # ================================
        #  LOGO + TITLE (อยู่บนแถวเดียว)
        # ================================
        title_row = QtWidgets.QHBoxLayout()
        title_row.setSpacing(10)
        title_row.addStretch(1)

        logo_path = Path(__file__).parent / "logo.png"
        if logo_path.exists():
            logo_label = QtWidgets.QLabel()
            pix = QtGui.QPixmap(str(logo_path))
            pix = pix.scaled(42, 42, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            logo_label.setPixmap(pix)
            logo_label.setAlignment(QtCore.Qt.AlignVCenter)
            title_row.addWidget(logo_label)
        else:
            logo_label = QtWidgets.QLabel()
            logo_label.setText("[logo]")
            logo_label.setAlignment(QtCore.Qt.AlignVCenter)
            title_row.addWidget(logo_label)

        title = QtWidgets.QLabel("Reconcile GUI")
        f = title.font()
        f.setPointSize(22)
        f.setBold(True)
        title.setFont(f)
        title_row.addWidget(title)

        title_row.addStretch(1)
        root.addLayout(title_row)

        subtitle = QtWidgets.QLabel("Enrich • Filter • Aggregate • Compare")
        subtitle.setAlignment(QtCore.Qt.AlignCenter)
        subtitle.setStyleSheet("color:#6b7280; margin-bottom: 8px;")
        root.addWidget(subtitle)

        # -------- Core Actions --------
        core_box = QtWidgets.QGroupBox("Main action")
        core_lay = QtWidgets.QVBoxLayout(core_box)
        core_lay.setContentsMargins(16, 12, 16, 16)
        core_lay.setSpacing(10)

        btn_compare = BigButton(
            "⚖️  Compare Files",
            "Load A/B → Filter / Aggregate → Compare → Coverage & Value Diff",
        )
        btn_compare.clicked.connect(self.goCompare.emit)

        btn_load_plugin = BigButton(
            "📥 Load Feature (.py)",
            "เลือกไฟล์ .py ที่มี QWidget subclass เพื่อนำมาใช้เป็นฟีเจอร์เพิ่มเติม",
        )
        btn_load_plugin.clicked.connect(self.requestLoadPlugin.emit)

        btn_manage = QtWidgets.QPushButton("🧩 Manage Features (rename / remove)")
        btn_manage.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        btn_manage.setToolTip("แก้ชื่อฟีเจอร์ / ซ่อนฟีเจอร์ที่ไม่ใช้จากหน้า Home")
        btn_manage.setFixedHeight(36)
        btn_manage.clicked.connect(self.requestManagePlugins.emit)

        core_lay.addWidget(btn_compare)
        core_lay.addWidget(btn_load_plugin)
        core_lay.addWidget(btn_manage)

        # -------- Plugins area --------
        plugins_box = QtWidgets.QGroupBox("Loaded features")
        plugins_box.setStyleSheet("QGroupBox { margin-top: 14px; }")
        plugins_lay = QtWidgets.QVBoxLayout(plugins_box)
        plugins_lay.setContentsMargins(16, 10, 16, 16)
        plugins_lay.setSpacing(6)

        self.lbl_plugins_hint = QtWidgets.QLabel(
            "ฟีเจอร์ที่โหลดจากไฟล์ .py จะปรากฏตรงนี้\n"
            "• คลิกที่ฟีเจอร์เพื่อเปิดหน้าต่าง\n"
            "• ใช้เมนู Plugins → Manage Features เพื่อเปลี่ยนชื่อ / ซ่อน"
        )
        self.lbl_plugins_hint.setStyleSheet("color:#9ca3af;")
        self.lbl_plugins_hint.setWordWrap(True)
        plugins_lay.addWidget(self.lbl_plugins_hint)

        self._grid = QtWidgets.QGridLayout()
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)

        self._plugins_wrap = QtWidgets.QWidget()
        self._plugins_wrap.setLayout(self._grid)
        plugins_lay.addWidget(self._plugins_wrap)

        self._next_row, self._next_col = 0, 0
        # list[(title, subtitle, stored, QPushButton)]
        self._plugin_buttons = []

        root.addWidget(core_box)
        root.addWidget(plugins_box)
        root.addStretch(1)

    # ---------- plugins area API ----------
    def clear_plugin_buttons(self):
        for _, _, _, btn in self._plugin_buttons:
            self._grid.removeWidget(btn)
            btn.setParent(None)
        self._plugin_buttons.clear()
        self._next_row, self._next_col = 0, 0

    def add_plugin_button(self, title: str, subtitle: str, on_click, stored: str = ""):
        btn = BigButton(title, subtitle)
        btn.clicked.connect(on_click)
        self._grid.addWidget(btn, self._next_row, self._next_col)
        self._plugin_buttons.append((title, subtitle, stored, btn))

        self._next_col += 1
        if self._next_col > 1:
            self._next_col = 0
            self._next_row += 1

    def rebuild_plugins(self, plugins):
        """
        plugins: list of (title, subtitle, opener_fn, stored_path)
        """
        self.clear_plugin_buttons()
        if not plugins:
            self.lbl_plugins_hint.setText(
                "ยังไม่มีฟีเจอร์ที่โหลดเข้ามา\n"
                "→ ใช้ปุ่ม “Load Feature (.py)” เพื่อเพิ่มฟีเจอร์ใหม่"
            )
        else:
            self.lbl_plugins_hint.setText(
                "คลิกที่ฟีเจอร์เพื่อเปิดหน้าต่าง\n"
                "ใช้เมนู Plugins → Manage Features เพื่อเปลี่ยนชื่อ / ซ่อนฟีเจอร์"
            )
        for title, subtitle, opener, stored in plugins:
            self.add_plugin_button(title, subtitle, opener, stored)


# =========================
# Manage Features Dialog
# =========================
class ManageFeaturesDialog(QtWidgets.QDialog):
    """
    Dialog สำหรับจัดการฟีเจอร์:
      - แก้ชื่อ (Title, Subtitle) ที่แสดงบน Home
      - ทำเครื่องหมาย Remove เพื่อลบออกจาก registry (ไม่ลบไฟล์จริง)
    """

    def __init__(self, plugins, parent=None):
        """
        plugins: list of (title, subtitle, opener_fn, stored_path)
        """
        super().__init__(parent)
        self.setWindowTitle("Manage Features")
        self.resize(800, 420)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        info = QtWidgets.QLabel(
            "ปรับชื่อฟีเจอร์ให้จำง่าย หรือเอาออกจากหน้า Home ได้จากหน้านี้\n"
            "หมายเหตุ: การ Remove จะลบออกจาก plugins.json แต่ไม่ลบไฟล์ต้นฉบับ"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#6b7280;")
        layout.addWidget(info)

        self.table = QtWidgets.QTableWidget(len(plugins), 4)
        self.table.setHorizontalHeaderLabels(["Name (Title)", "Subtitle", "Stored Path", "Remove?"])
        self.table.verticalHeader().setVisible(False)
        hh = self.table.horizontalHeader()
        hh.setStretchLastSection(False)
        hh.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QtWidgets.QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)

        for row, (title, subtitle, opener, stored) in enumerate(plugins):
            # Name (editable)
            it_name = QtWidgets.QTableWidgetItem(title)
            it_name.setFlags(it_name.flags() | QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 0, it_name)

            # Subtitle (editable)
            it_sub = QtWidgets.QTableWidgetItem(subtitle)
            it_sub.setFlags(it_sub.flags() | QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 1, it_sub)

            # Path (read-only)
            it_path = QtWidgets.QTableWidgetItem(stored or "")
            it_path.setFlags(it_path.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 2, it_path)

            # Remove (checkbox)
            it_rm = QtWidgets.QTableWidgetItem()
            it_rm.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            it_rm.setCheckState(QtCore.Qt.Unchecked)
            self.table.setItem(row, 3, it_rm)

        layout.addWidget(self.table)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addWidget(btn_box)

        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

    def result_rows(self):
        """
        คืน list ของ (remove_flag, new_title, new_subtitle, stored_path)
        """
        rows = []
        for r in range(self.table.rowCount()):
            it_name = self.table.item(r, 0)
            it_sub = self.table.item(r, 1)
            it_path = self.table.item(r, 2)
            it_rm = self.table.item(r, 3)
            remove = it_rm.checkState() == QtCore.Qt.Checked if it_rm is not None else False
            title = it_name.text().strip() if it_name else ""
            sub = it_sub.text().strip() if it_sub else ""
            stored = it_path.text().strip() if it_path else ""
            rows.append((remove, title, sub, stored))
        return rows


# =========================
# Main Window (Router + Plugins)
# =========================
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 820)

        self._stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self._stack)

        self._home = HomePage()
        self._stack.addWidget(self._home)

        self._status = self.statusBar()
        self._status.showMessage("Ready")

        # holders
        self._compare = None
        self._plugin_windows = []
        # _loaded_plugins: list[(title, subtitle, opener_fn, stored_path)]
        self._loaded_plugins = []

        # connect Home signals
        self._home.goCompare.connect(self.open_compare_window)
        self._home.requestLoadPlugin.connect(self.load_plugin_via_dialog)
        self._home.requestManagePlugins.connect(self._manage_features)

        # developer credit label (bottom-right)
        self.dev_label = QtWidgets.QLabel("พัฒนาโดย Fulfillment Team", self)
        self.dev_label.setStyleSheet(
            "color:#9ca3af; font-size:11px; padding:4px; background:transparent;"
        )
        self.dev_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self._build_menu()
        self._load_plugins_registry()
        self._position_dev_label()

    # ---------- dev label positioning ----------
    def _position_dev_label(self):
        if not hasattr(self, "dev_label") or self.dev_label is None:
            return
        margin = 8
        w = self.dev_label.sizeHint().width()
        h = self.dev_label.sizeHint().height()
        x = self.width() - w - margin
        y = self.height() - h - margin
        self.dev_label.move(x, y)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_dev_label()

    # ----- menu -----
    def _build_menu(self):
        mb = self.menuBar()

        filem = mb.addMenu("&File")
        filem.addAction("Home", self.show_home)
        filem.addSeparator()
        filem.addAction("Exit", self.close)

        pluginm = mb.addMenu("&Plugins")
        pluginm.addAction("Load Feature (.py)", self.load_plugin_via_dialog)
        pluginm.addAction("Manage Features (rename / remove)", self._manage_features)
        pluginm.addSeparator()
        pluginm.addAction("Reload Saved Features", self._load_plugins_registry)
        pluginm.addAction("Sync Registry (remove missing files)", self._clear_missing_from_registry)

        helpm = mb.addMenu("&Help")
        helpm.addAction(
            "About",
            lambda: QtWidgets.QMessageBox.information(
                self,
                "About",
                "Reconcile GUI – Compare • Plugins\n"
                "ระบบปลั๊กอิน: โหลด .py แล้วจดจำไว้ใน plugins.json\n"
                "สามารถเปลี่ยนชื่อฟีเจอร์ / ซ่อนฟีเจอร์ได้จากเมนู Plugins → Manage Features",
            ),
        )

    # ----- routes -----
    def show_home(self):
        self._stack.setCurrentWidget(self._home)
        self._status.showMessage("Home")

    def open_compare_window(self):
        if CompareWindow is None:
            QtWidgets.QMessageBox.warning(self, "Compare", "ไม่พบ CompareWindow")
            return
        self._compare = CompareWindow()
        # เชื่อมปุ่ม Home ของ Compare ให้กลับมาหน้า Main + ปิดหน้าต่าง Compare
        self._compare.requestHome.connect(
            lambda: (self._compare.close(), self.show_home(), self.raise_(), self.activateWindow())
        )
        self._compare.show()
        self._status.showMessage("Compare window opened")

    # ====== plugin registry: helpers ======
    def _app_dir(self) -> Path:
        return Path(os.path.abspath(sys.argv[0])).parent

    def _plugins_db_path(self) -> Path:
        return self._app_dir() / "plugins.json"

    def _to_storable_path(self, path_str: str) -> str:
        """
        แปลง absolute path -> relative path (ถ้าอยู่ใต้โฟลเดอร์แอป)
        มิฉะนั้นเก็บ absolute ตามเดิม
        """
        p = Path(path_str).resolve()
        app_dir = self._app_dir().resolve()
        try:
            common = os.path.commonpath([str(p), str(app_dir)])
        except Exception:
            common = ""
        if common == str(app_dir):
            return os.path.relpath(str(p), str(app_dir))
        return str(p)

    def _resolve_stored_path(self, stored: str) -> Path:
        sp = Path(stored)
        if not sp.is_absolute():
            return (self._app_dir() / sp).resolve()
        return sp.resolve()

    # ====== plugin persist ======
    def _save_plugins_registry(self):
        try:
            db = {"plugins": [self._to_storable_path(p) for (_, _, _, p) in self._loaded_plugins]}
            self._plugins_db_path().write_text(
                json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print("save plugins registry failed:", e)

    def _load_plugins_registry(self):
        """
        อ่าน plugins.json แล้ว autoload ใหม่ทั้งหมด (เคลียร์ของเดิมก่อน)
        """
        self._loaded_plugins = []
        self._home.rebuild_plugins([])

        try:
            p = self._plugins_db_path()
            if not p.exists():
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            stored_paths = list(dict.fromkeys(data.get("plugins", [])))  # unique & keep order
        except Exception as e:
            print("load plugins registry failed:", e)
            return

        loaded = 0
        for stored in stored_paths:
            abs_path = self._resolve_stored_path(stored)
            if not abs_path.is_file():
                continue
            try:
                title, subtitle, opener = self._load_plugin_from_py(str(abs_path))
                self._loaded_plugins.append((title, subtitle, opener, stored))
                loaded += 1
            except Exception as e:
                print(f"autoload plugin failed for {stored}: {e}")

        self._home.rebuild_plugins(self._loaded_plugins)
        if loaded:
            self._status.showMessage(f"Autoloaded {loaded} plugin(s)")

    def _clear_missing_from_registry(self):
        """
        ลบปลั๊กอินที่ path หายไป ออกจาก registry
        """
        still_exist = []
        for item in self._loaded_plugins:
            if len(item) != 4:
                continue
            title, subtitle, opener, stored = item
            if self._resolve_stored_path(stored).is_file():
                still_exist.append(item)
        self._loaded_plugins = still_exist
        self._save_plugins_registry()
        self._home.rebuild_plugins(self._loaded_plugins)
        QtWidgets.QMessageBox.information(self, "Plugins", "Synced registry and removed missing files.")

    # ====== plugin manage ======
    def _manage_features(self):
        if not self._loaded_plugins:
            QtWidgets.QMessageBox.information(
                self,
                "Manage Features",
                "ยังไม่มีฟีเจอร์ที่โหลดเข้ามา\nกรุณาใช้ “Load Feature (.py)” ก่อน",
            )
            return

        dlg = ManageFeaturesDialog(self._loaded_plugins, parent=self)
        if dlg.exec_() != QtWidgets.QDialog.Accepted:
            return

        rows = dlg.result_rows()
        new_list = []
        for (remove, new_title, new_sub, stored_row), old in zip(rows, self._loaded_plugins):
            old_title, old_sub, opener, old_stored = old
            if remove:
                continue  # ลบออกจาก registry
            new_list.append(
                (
                    new_title or old_title,
                    new_sub or old_sub,
                    opener,
                    old_stored,
                )
            )

        self._loaded_plugins = new_list
        self._save_plugins_registry()
        self._home.rebuild_plugins(self._loaded_plugins)
        self._status.showMessage("Updated features list")

    # ====== plugin logic ======
    def load_plugin_via_dialog(self):
        cur_dir = str(self._app_dir())
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Feature (.py)", cur_dir, "Python (*.py)"
        )
        if not path:
            return
        try:
            title, subtitle, opener = self._load_plugin_from_py(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self, "Load Feature Failed", f"{e}\n\n{traceback.format_exc()}"
            )
            return

        stored = self._to_storable_path(path)
        self._loaded_plugins.append((title, subtitle, opener, stored))
        self._home.rebuild_plugins(self._loaded_plugins)
        self._save_plugins_registry()
        self._status.showMessage(f"Loaded feature: {title}")

    def _load_plugin_from_py(self, path: str):
        module_name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot create spec for file")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)

        QWidget = QtWidgets.QWidget
        widget_cls = getattr(mod, "EXPORTED_WIDGET", None)

        # หา QWidget subclass
        if not (widget_cls and inspect.isclass(widget_cls) and issubclass(widget_cls, QWidget)):
            names = ["MainWindow", "FeatureWindow", "LookupWindow", "LookupApp"]
            for n in names:
                c = getattr(mod, n, None)
                if c and inspect.isclass(c) and issubclass(c, QWidget):
                    widget_cls = c
                    break
            if not widget_cls:
                for _, c in inspect.getmembers(mod, inspect.isclass):
                    if issubclass(c, QWidget) and c.__module__ == mod.__name__:
                        widget_cls = c
                        break

        if not widget_cls:
            raise RuntimeError("ไม่พบ QWidget subclass ในไฟล์ปลั๊กอินนี้")

        title = getattr(widget_cls, "WINDOW_TITLE", widget_cls.__name__)
        subtitle = f"{os.path.basename(path)} • {widget_cls.__name__}"

        def _open():
            try:
                win = widget_cls()
            except Exception:
                win = widget_cls(parent=None)
            win.setWindowTitle(title)
            win.show()
            self._plugin_windows.append(win)
            self._status.showMessage(f"Opened: {title}")

        return title, subtitle, _open


# =========================
# Entrypoint
# =========================
def _enable_hi_dpi():
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)


if __name__ == "__main__":
    _enable_hi_dpi()
    app = QtWidgets.QApplication(sys.argv)
    apply_theme(app)
    app.setApplicationName("Reconcile GUI")
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
