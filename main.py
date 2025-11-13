#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reconcile GUI – Main Entry (Edit Data + Compare + Lookup + Plugins)
- Home: ปุ่มใหญ่ 3 เมนูหลัก และ "Load Feature (.py)" สำหรับโหลดปลั๊กอินแบบ runtime
- Plugins: บันทึก path ปลั๊กอินไว้ใน plugins.json เป็น "relative path" หากอยู่ใต้โฟลเดอร์แอป
- Autoload: โหลดกลับอัตโนมัติทุกครั้งที่เปิดโปรแกรม
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
    from edit_data_view import EditDataView
except Exception:
    EditDataView = None

try:
    from compare_view import CompareWindow
except Exception:
    CompareWindow = None

# ---- optional import (lookup) ----
LookupValueView = None
LookupWindow = None
try:
    from lookup_value_gui import LookupValueView as _LVV
    LookupValueView = _LVV
except Exception:
    pass

if LookupValueView is None:
    try:
        from lookup_value_gui import LookupWindow as _LWW
        LookupWindow = _LWW
    except Exception:
        pass

APP_TITLE = "Reconcile GUI – Edit Data • Lookup • Compare • Plugins"


# =========================
# BigButton (ปุ่มเมนูใหญ่)
# =========================
class BigButton(QtWidgets.QPushButton):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.setMinimumHeight(120)
        w = QtWidgets.QWidget(self)
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(18, 16, 18, 16)
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
        l = QtWidgets.QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.addWidget(w)


# =========================
# Home Page
# =========================
class HomePage(QtWidgets.QWidget):
    goEdit = QtCore.pyqtSignal()
    goCompare = QtCore.pyqtSignal()
    goLookup = QtCore.pyqtSignal()
    requestLoadPlugin = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        title = QtWidgets.QLabel("Reconcile GUI")
        tf = title.font()
        tf.setPointSize(22)
        tf.setBold(True)
        title.setFont(tf)
        title.setAlignment(QtCore.Qt.AlignCenter)

        tips = QtWidgets.QLabel("เลือกเมนูที่ต้องการเริ่มงาน หรือโหลดฟีเจอร์ใหม่จากไฟล์ .py")
        tips.setAlignment(QtCore.Qt.AlignCenter)
        tips.setStyleSheet("color:#6b7280;")

        btn_edit = BigButton("Edit Data", "Trim / Delete / Pad / Group-Sum / Calculation\nโหลดไฟล์ → แก้ไข → Export")
        btn_edit.clicked.connect(self.goEdit.emit)

        btn_lookup = BigButton("Lookup Values", "ค้นหาค่า/แมปค่า จากไฟล์อ้างอิง เช่น Supplier/Vendor Mapping")
        btn_lookup.clicked.connect(self.goLookup.emit)

        btn_compare = BigButton("Compare Files", "Load A/B → Filter → (Aggregate) → Compare → Summary/Export")
        btn_compare.clicked.connect(self.goCompare.emit)

        btn_load_plugin = BigButton("Load Feature (.py)", "เลือกไฟล์ .py เพื่อโหลดฟีเจอร์ใหม่แบบอัตโนมัติ")
        btn_load_plugin.clicked.connect(self.requestLoadPlugin.emit)

        self._grid = QtWidgets.QGridLayout()
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(14)
        self._grid.addWidget(btn_load_plugin, 0, 0)
        # self._grid.addWidget(btn_edit, 1, 0)
        self._grid.addWidget(btn_compare, 1, 0)
        # ถ้าต้องการแสดงปุ่ม Lookup บน Home ด้วย ให้ uncomment บรรทัดถัดไป
        # self._grid.addWidget(btn_lookup, 0, 1)
        self._next_row, self._next_col = 2, 0

        wrap = QtWidgets.QWidget()
        wrap.setLayout(self._grid)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)
        root.addWidget(title)
        root.addWidget(tips)
        root.addWidget(wrap)
        root.addStretch(1)

    def add_plugin_button(self, title: str, subtitle: str, on_click):
        btn = BigButton(title, subtitle)
        btn.clicked.connect(on_click)
        self._grid.addWidget(btn, self._next_row, self._next_col)
        self._next_col += 1
        if self._next_col > 1:
            self._next_col, self._next_row = 0, self._next_row + 1


# =========================
# Edit Page
# =========================
class EditPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        title = QtWidgets.QLabel("Edit Data")
        f = title.font()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        self.backHome = QtWidgets.QPushButton("← Home")
        self.backHome.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        self.backHome.setFixedHeight(34)
        header.addWidget(self.backHome)
        header.addWidget(title)
        header.addStretch(1)
        self.editor = EditDataView(self) if EditDataView else QtWidgets.QLabel("ไม่พบ EditDataView")
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.addLayout(header)
        root.addWidget(self.editor)


# =========================
# Lookup Page
# =========================
class LookupPage(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(8)
        title = QtWidgets.QLabel("Lookup Values")
        f = title.font()
        f.setPointSize(16)
        f.setBold(True)
        title.setFont(f)
        self.backHome = QtWidgets.QPushButton("← Home")
        self.backHome.setFixedHeight(34)
        self.backHome.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        header.addWidget(self.backHome)
        header.addWidget(title)
        header.addStretch(1)
        if LookupValueView:
            self.lookup = LookupValueView(self)
            root = QtWidgets.QVBoxLayout(self)
            root.addLayout(header)
            root.addWidget(self.lookup)
        else:
            lbl = QtWidgets.QLabel("ไม่พบ LookupValueView – จะเปิดเป็นหน้าต่างแยกแทน")
            lbl.setStyleSheet("color:#ef4444;")
            root = QtWidgets.QVBoxLayout(self)
            root.addLayout(header)
            root.addWidget(lbl)


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
        self._home, self._edit, self._lookup = HomePage(), EditPage(), LookupPage()
        self._stack.addWidget(self._home)
        self._stack.addWidget(self._edit)
        self._stack.addWidget(self._lookup)
        self.statusBar().showMessage("Ready")

        # Connects
        self._home.goEdit.connect(self.show_edit)
        self._home.goCompare.connect(self.open_compare_window)
        self._home.goLookup.connect(self.show_or_open_lookup)
        self._home.requestLoadPlugin.connect(self.load_plugin_via_dialog)
        self._edit.backHome.clicked.connect(self.show_home)
        self._lookup.backHome.clicked.connect(self.show_home)

        # Holders
        self._compare = None
        self._lookup_window = None
        self._plugin_windows = []
        self._loaded_plugins = []  # [(title, subtitle, opener_fn, stored_path_str)]

        self._build_menu()
        self._load_plugins_registry()

    # ----- menu -----
    def _build_menu(self):
        mb = self.menuBar()
        filem = mb.addMenu("&File")
        filem.addAction("Home", self.show_home)
        filem.addAction("Exit", self.close)

        pluginm = mb.addMenu("&Plugins")
        pluginm.addAction("Load Feature (.py)", self.load_plugin_via_dialog)
        pluginm.addAction("Reload Saved Features", self._load_plugins_registry)
        pluginm.addAction("Sync Registry (remove missing files)", self._clear_missing_from_registry)

        helpm = mb.addMenu("&Help")
        helpm.addAction("About", lambda: QtWidgets.QMessageBox.information(
            self, "About",
            "Reconcile GUI – Enrich • Filter • Aggregate\n"
            "ระบบปลั๊กอิน: โหลด .py แล้วจำค่าไว้ใน plugins.json (relative เมื่ออยู่ใต้โฟลเดอร์แอป)."
        ))

    # ----- routes -----
    def show_home(self):
        self._stack.setCurrentWidget(self._home)
        self.statusBar().showMessage("Home")

    def show_edit(self):
        self._stack.setCurrentWidget(self._edit)
        self.statusBar().showMessage("Edit Data ready")

    def show_or_open_lookup(self):
        if LookupValueView:
            self._stack.setCurrentWidget(self._lookup)
        elif LookupWindow:
            self._lookup_window = LookupWindow()
            self._lookup_window.show()
        else:
            QtWidgets.QMessageBox.warning(self, "Lookup", "ไม่พบ LookupValueView/LookupWindow")
        self.statusBar().showMessage("Lookup ready")

    def open_compare_window(self):
        if CompareWindow is None:
            QtWidgets.QMessageBox.warning(self, "Compare", "ไม่พบ CompareWindow")
            return
        self._compare = CompareWindow()
        # ✅ เชื่อมปุ่ม Home ของ Compare ให้กลับหน้า Home + ปิดหน้าต่าง Compare
        self._compare.requestHome.connect(lambda: (self._compare.close(), self.show_home(), self.raise_(), self.activateWindow()))
        self._compare.show()
        self.statusBar().showMessage("Compare window opened")

    # ====== plugin registry: relative/absolute helpers ======
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
            # อยู่ใต้โฟลเดอร์แอป -> เก็บ relative
            return os.path.relpath(str(p), str(app_dir))
        return str(p)

    def _resolve_stored_path(self, stored: str) -> Path:
        """
        แปลง stored path -> absolute path
        - ถ้าเป็น path relative ให้ join กับ app_dir
        - ถ้าเป็น absolute คืนค่าตามนั้น
        """
        sp = Path(stored)
        if not sp.is_absolute():
            return (self._app_dir() / sp).resolve()
        return sp.resolve()

    # ====== plugin persist ======
    def _save_plugins_registry(self):
        try:
            db = {"plugins": [self._to_storable_path(p) for (_, _, _, p) in self._loaded_plugins]}
            self._plugins_db_path().write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print("save plugins registry failed:", e)

    def _load_plugins_registry(self):
        """
        อ่าน plugins.json แล้วพยายาม autoload
        รองรับทั้ง relative และ absolute path
        """
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
                # ไม่เจอไฟล์ ข้ามไป (ให้ผู้ใช้ Sync Registry เพื่อล้าง)
                continue
            try:
                title, subtitle, opener = self._load_plugin_from_py(str(abs_path))
                self._loaded_plugins.append((title, subtitle, opener, stored))  # เก็บ "stored" เดิมไว้
                self._home.add_plugin_button(title, subtitle, opener)
                loaded += 1
            except Exception as e:
                print(f"autoload plugin failed for {stored}: {e}")

        if loaded:
            self.statusBar().showMessage(f"Autoloaded {loaded} plugin(s)")

    def _clear_missing_from_registry(self):
        """
        ลบปลั๊กอินที่ path (หลัง resolve) หายไป ออกจาก registry
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
        QtWidgets.QMessageBox.information(self, "Plugins", "Synced registry and removed missing files.")

    # ====== plugin logic ======
    def load_plugin_via_dialog(self):
        cur_dir = str(self._app_dir())
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Feature (.py)", cur_dir, "Python (*.py)")
        if not path:
            return
        try:
            title, subtitle, opener = self._load_plugin_from_py(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Feature Failed", f"{e}\n\n{traceback.format_exc()}")
            return

        stored = self._to_storable_path(path)  # << เก็บเป็น relative ถ้าอยู่ใต้โฟลเดอร์แอป
        self._loaded_plugins.append((title, subtitle, opener, stored))
        self._home.add_plugin_button(title, subtitle, opener)
        self._save_plugins_registry()
        self.statusBar().showMessage(f"Loaded feature: {title}")

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
        if not (widget_cls and inspect.isclass(widget_cls) and issubclass(widget_cls, QWidget)):
            names = ["LookupWindow", "LookupApp", "MainFeature", "FeatureWindow", "MainWindow"]
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
            self.statusBar().showMessage(f"Opened: {title}")

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
