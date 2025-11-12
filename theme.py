# theme.py
# -*- coding: utf-8 -*-
"""
Global Theme for Reconcile GUI (PyQt5)
- HiDPI on
- Fusion style + soft palette
- Clean QSS (light theme) ที่อ่านไทย/อังกฤษสบายตา
- Helpers: apply_theme(), set_table_defaults(view), polish_widget_tree(root)

วิธีใช้:
    from theme import apply_theme, set_table_defaults
    app = QtWidgets.QApplication(sys.argv)
    apply_theme(app)

    # หลังสร้าง table view:
    set_table_defaults(self.tableView)
"""
from PyQt5 import QtCore, QtGui, QtWidgets

# -----------------------------
# QSS — โทนสว่าง สะอาด ตาโปร
# -----------------------------
THEME_QSS = """
* { font-family: "Segoe UI", "Sarabun", "Noto Sans Thai", system-ui; font-size: 13px; color:#111827; }
QMainWindow, QWidget { background: #f7f8fa; }
QStatusBar { background: transparent; }

QMenuBar { background: transparent; }
QMenuBar::item { padding:6px 10px; margin:2px; border-radius:8px; }
QMenuBar::item:selected { background:#e5e7eb; }

QToolBar { background: transparent; border:0; spacing:6px; }
QToolButton {
  background:#ffffff; border:1px solid #e5e7eb; border-radius:10px; padding:6px 10px;
}
QToolButton:hover { background:#f3f4f6; }

QGroupBox {
  font-weight:600; border:1px solid #e5e7eb; border-radius:12px;
  margin-top:12px; background:#ffffff;
}
QGroupBox::title { subcontrol-origin: margin; left:12px; top:-9px; padding:0 6px; background:#ffffff; color:#374151; }

QPushButton {
  background:#ffffff; border:1px solid #e5e7eb; border-radius:10px;
  padding:8px 14px; font-weight:600;
}
QPushButton:hover { background:#f3f4f6; }
QPushButton:pressed { background:#e5e7eb; }
QPushButton:disabled { color:#9ca3af; border-color:#eef2f7; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {
  background:#ffffff; border:1px solid #e5e7eb; border-radius:10px;
  padding:6px 10px;
}
QComboBox QAbstractItemView { border:1px solid #e5e7eb; selection-background-color:#eef2ff; }

QTabWidget::pane {
  border:1px solid #e5e7eb; border-radius:12px; margin-top:-1px; background:#ffffff;
}
QTabBar::tab {
  padding:8px 14px; margin:4px; border:1px solid #e5e7eb; border-radius:10px; background:#ffffff;
}
QTabBar::tab:selected { background:#eef2ff; border-color:#c7d2fe; }

QHeaderView::section {
  background:#f3f4f6; padding:8px; border:0; border-right:1px solid #e5e7eb; font-weight:600;
}
QTableView {
  gridline-color:#eef2f7; selection-background-color:#dbeafe; selection-color:#111827;
  alternate-background-color:#fafafa;
}
QTableView::item { padding:6px; }

QScrollBar:vertical { width:11px; background:transparent; margin:0; }
QScrollBar::handle:vertical { background:#cbd5e1; min-height:40px; border-radius:6px; }
QScrollBar:horizontal { height:11px; background:transparent; margin:0; }
QScrollBar::handle:horizontal { background:#cbd5e1; min-width:40px; border-radius:6px; }
"""

# -----------------------------
# Palette (Fusion) แบบ soft
# -----------------------------
def _soft_fusion_palette():
    pal = QtGui.QPalette()
    base = QtGui.QColor("#ffffff")
    alt  = QtGui.QColor("#fafafa")
    text = QtGui.QColor("#111827")
    win  = QtGui.QColor("#f7f8fa")
    hl   = QtGui.QColor("#dbeafe")

    pal.setColor(QtGui.QPalette.Window, win)
    pal.setColor(QtGui.QPalette.WindowText, text)
    pal.setColor(QtGui.QPalette.Base, base)
    pal.setColor(QtGui.QPalette.AlternateBase, alt)
    pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#111827"))
    pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#f9fafb"))
    pal.setColor(QtGui.QPalette.Text, text)
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#ffffff"))
    pal.setColor(QtGui.QPalette.ButtonText, text)
    pal.setColor(QtGui.QPalette.BrightText, QtGui.QColor("#ef4444"))
    pal.setColor(QtGui.QPalette.Highlight, hl)
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#111827"))
    return pal

# -----------------------------
# Public API
# -----------------------------
def apply_theme(app: QtWidgets.QApplication) -> None:
    """เรียกครั้งเดียวหลังสร้าง QApplication"""
    # HiDPI
    try:
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    app.setStyle("Fusion")
    app.setPalette(_soft_fusion_palette())
    app.setStyleSheet(THEME_QSS)

def set_table_defaults(view: QtWidgets.QTableView) -> None:
    """ตั้งค่า QTableView ให้ดูดีแบบมาตรฐาน"""
    view.setAlternatingRowColors(True)
    view.setSortingEnabled(True)
    view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
    view.verticalHeader().setDefaultSectionSize(24)
    view.verticalHeader().setVisible(False)
    hh = view.horizontalHeader()
    hh.setStretchLastSection(True)
    hh.setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    hh.setMinimumSectionSize(90)

def polish_widget_tree(root: QtWidgets.QWidget) -> None:
    """
    ปรับ margin/spacing ทั่วยอด (ใช้ครั้งเดียวหลัง build UI)
    เหมาะกับหน้าที่มี layout หลายชั้น
    """
    def _walk(w: QtWidgets.QWidget):
        lay = w.layout()
        if lay is not None:
            lay.setContentsMargins(12, 12, 12, 12)
            lay.setSpacing(8)
        for child in w.findChildren(QtWidgets.QWidget):
            _walk(child)
    _walk(root)
