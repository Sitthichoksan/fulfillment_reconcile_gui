#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reconcile GUI – Main Entry (Compare + Plugins)
- Home: ปุ่มใหญ่ 2 เมนูหลัก (Compare, Load Feature (.py))
- ตัด Edit Data และ Lookup ออกไปตามที่ขอ
- Plugins: โหลดฟีเจอร์จากไฟล์ .py และจำ path ไว้ใน plugins.json
- ใช้ธีมกลางจาก theme.py
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
    def apply_theme(app): pass

try:
    from compare_view import CompareWindow
except Exception:
    CompareWindow = None

# lookup ถูกตัดออกแล้ว แต่คง import แบบ optional ไว้ไม่ให้ error
LookupValueView = None
LookupWindow = None

APP_TITLE = "Reconcile GUI – Compare • Plugins"


# =========================
# BigButton
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
        f = lbl_title.font(); f.setPointSize(18); f.setBold(True)
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
# Home Page (เหลือ Compare + Load Feature)
# =========================
class HomePage(QtWidgets.QWidget):
    goCompare = QtCore.pyqtSignal()
    requestLoadPlugin = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        title = QtWidgets.QLabel("Reconcile GUI")
        f = title.font(); f.setPointSize(22); f.setBold(True)
        title.setFont(f)
        title.setAlignment(QtCore.Qt.AlignCenter)

        tips = QtWidgets.QLabel("เลือก Compare Files หรือ โหลดฟีเจอร์ใหม่จาก .py")
        tips.setAlignment(QtCore.Qt.AlignCenter)
        tips.setStyleSheet("color:#6b7280;")

        # --- removed: Edit Data / Lookup ---

        btn_compare = BigButton("Compare Files",
                                "Load A/B → Filter → Aggregate → Compare → Summary/Export")
        btn_compare.clicked.connect(self.goCompare.emit)

        btn_load_plugin = BigButton("Load Feature (.py)",
                                    "โหลดปลั๊กอินเพิ่มจากไฟล์ Python (QWidget)")
        btn_load_plugin.clicked.connect(self.requestLoadPlugin.emit)

        # layout
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        grid.addWidget(btn_load_plugin, 0, 0)
        grid.addWidget(btn_compare, 1, 0)

        self._grid = grid
        self._next_row, self._next_col = 2, 0

        wrap = QtWidgets.QWidget(); wrap.setLayout(grid)

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
# Main Window
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
        self.statusBar().showMessage("Ready")

        # signals
        self._home.goCompare.connect(self.open_compare_window)
        self._home.requestLoadPlugin.connect(self.load_plugin_via_dialog)

        self._compare = None
        self._plugin_windows = []
        self._loaded_plugins = []   # (title, subtitle, opener_fn, stored_path)

        self._build_menu()
        self._load_plugins_registry()

    # ========== menu ==========
    def _build_menu(self):
        mb = self.menuBar()

        m_file = mb.addMenu("&File")
        m_file.addAction("Home", self.show_home)
        m_file.addAction("Exit", self.close)

        m_plug = mb.addMenu("&Plugins")
        m_plug.addAction("Load Feature (.py)", self.load_plugin_via_dialog)
        m_plug.addAction("Reload Saved Features", self._load_plugins_registry)
        m_plug.addAction("Sync Registry (remove missing)", self._clear_missing_from_registry)

        m_help = mb.addMenu("&Help")
        m_help.addAction("About", lambda: QtWidgets.QMessageBox.information(
            self, "About",
            "Reconcile GUI – Compare & Plugins\n"
            "ระบบปลั๊กอิน: โหลด .py แล้วจำไว้ใน plugins.json"
        ))

    # ========== routes ==========
    def show_home(self):
        self._stack.setCurrentWidget(self._home)
        self.statusBar().showMessage("Home")

    def open_compare_window(self):
        if CompareWindow is None:
            QtWidgets.QMessageBox.warning(self, "Compare", "ไม่พบ CompareWindow")
            return
        self._compare = CompareWindow()
        self._compare.requestHome.connect(
            lambda: (self._compare.close(), self.show_home(), self.raise_(), self.activateWindow())
        )
        self._compare.show()
        self.statusBar().showMessage("Compare Window opened")

    # ========== plugin registry ==========
    def _app_dir(self) -> Path:
        return Path(os.path.abspath(sys.argv[0])).parent

    def _plugins_db_path(self) -> Path:
        return self._app_dir() / "plugins.json"

    def _to_storable_path(self, path_str: str) -> str:
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
        return (self._app_dir() / sp).resolve() if not sp.is_absolute() else sp.resolve()

    def _save_plugins_registry(self):
        try:
            db = {"plugins": [self._to_storable_path(p) for (_, _, _, p) in self._loaded_plugins]}
            self._plugins_db_path().write_text(
                json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            print("save registry failed:", e)

    def _load_plugins_registry(self):
        try:
            p = self._plugins_db_path()
            if not p.exists():
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            stored_paths = list(dict.fromkeys(data.get("plugins", [])))
        except Exception as e:
            print("load registry failed:", e)
            return

        loaded = 0
        for stored in stored_paths:
            abs_path = self._resolve_stored_path(stored)
            if not abs_path.is_file():
                continue
            try:
                title, subtitle, opener = self._load_plugin_from_py(str(abs_path))
                self._loaded_plugins.append((title, subtitle, opener, stored))
                self._home.add_plugin_button(title, subtitle, opener)
                loaded += 1
            except Exception as e:
                print(f"autoload plugin failed for {stored}: {e}")

        if loaded:
            self.statusBar().showMessage(f"Autoloaded {loaded} plugin(s)")

    def _clear_missing_from_registry(self):
        still = []
        for item in self._loaded_plugins:
            title, subtitle, opener, stored = item
            if self._resolve_stored_path(stored).is_file():
                still.append(item)
        self._loaded_plugins = still
        self._save_plugins_registry()
        QtWidgets.QMessageBox.information(self, "Plugins", "Synced registry.")

    # ========== plugin loader ==========
    def load_plugin_via_dialog(self):
        cur = str(self._app_dir())
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Feature (.py)", cur, "Python (*.py)"
        )
        if not path:
            return
        try:
            title, subtitle, opener = self._load_plugin_from_py(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Plugin error", f"{e}\n\n{traceback.format_exc()}")
            return

        stored = self._to_storable_path(path)
        self._loaded_plugins.append((title, subtitle, opener, stored))
        self._home.add_plugin_button(title, subtitle, opener)
        self._save_plugins_registry()
        self.statusBar().showMessage(f"Loaded plugin: {title}")

    def _load_plugin_from_py(self, path: str):
        module_name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("Cannot import module")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)

        QWidget = QtWidgets.QWidget
        widget_cls = getattr(mod, "EXPORTED_WIDGET", None)

        if not (widget_cls and inspect.isclass(widget_cls) and issubclass(widget_cls, QWidget)):
            fallback = ["MainWindow", "FeatureWindow", "LookupApp", "LookupWindow"]
            for name in fallback:
                c = getattr(mod, name, None)
                if c and inspect.isclass(c) and issubclass(c, QWidget):
                    widget_cls = c
                    break

        if not widget_cls:
            for _, c in inspect.getmembers(mod, inspect.isclass):
                if issubclass(c, QWidget) and c.__module__ == mod.__name__:
                    widget_cls = c
                    break

        if not widget_cls:
            raise RuntimeError("ไม่พบ QWidget subclass ในปลั๊กอินนี้")

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
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())
