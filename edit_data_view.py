#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Edit Data View (PyQt5) – Fresh Build (No Lookup)
Clean, Excel‑like UI with dual preview (Raw/Input vs Output)

Features
- Load CSV/TSV/TXT/DAT/LOG + Excel (xls/xlsx), auto delimiter + encoding
- Trim with pre-filter (contains/equals/starts/ends/regex) and multiple trim ops
- Delete rows by filter
- Pad left/right to fixed width with chosen fill char (only-shorter option)
- Group/Aggregate: Group only (with count), Agg only (sum/avg/min/max/count_distinct), or Group+Agg
- Calculation: A <op> B with + - * / // %, supports constant on either side, writes to new column
- Chain operations without reloading, undo/redo history, dry‑run preview dialog per action
- Export current Output to CSV/Excel
- Context menu: copy selected rows as CSV
- HiDPI flags set early, Fusion style + light palette for clean looks

Requires: PyQt5, pandas, openpyxl (for .xlsx)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Tuple, Callable, Dict
import io, csv, re

import pandas as pd
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton, QLabel, QLineEdit,
    QComboBox, QFileDialog, QMessageBox, QSpinBox, QStatusBar, QSizePolicy, QShortcut,
    QGroupBox, QCheckBox, QDialog
)

# ------------------------------
# HiDPI flags (must be set before QApplication)
# ------------------------------
try:
    if QtWidgets.QApplication.instance() is None:
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
except Exception:
    pass

# ------------------------------
# Busy helper
# ------------------------------
class _Busy:
    def __init__(self, widget: QWidget, msg: str, status: QStatusBar):
        self.w = widget; self.msg = msg; self.status = status
    def __enter__(self):
        try:
            self.w.setCursor(QtCore.Qt.BusyCursor)
            if self.status: self.status.showMessage(f"{self.msg}…")
        except Exception:
            pass
        return self
    def __exit__(self, exc_type, exc, tb):
        try:
            self.w.unsetCursor()
            if self.status: self.status.showMessage("Done ✓" if exc_type is None else "Error ✗", 2500)
        except Exception:
            pass
        return False

# ------------------------------
# Small preview dialog for Dry‑run
# ------------------------------
class _PreviewDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, df: pd.DataFrame, limit: int = 1000):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(960, 560)
        lay = QVBoxLayout(self)
        info = QLabel(f"Rows: {len(df)}  |  Showing: {min(len(df), limit)}")
        lay.addWidget(info)
        tv = QTableView(self)
        model = _PandasModel(self)
        show = df if len(df) <= limit else df.head(limit)
        model.set_df(show)
        tv.setModel(model)
        set_table_defaults(tv)
        lay.addWidget(tv, 1)
        btns = QHBoxLayout()
        btn_ok = QPushButton("Apply")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch(1); btns.addWidget(btn_ok); btns.addWidget(btn_cancel)
        lay.addLayout(btns)

# ------------------------------
# Pandas -> Qt model (sortable)
# ------------------------------
class _PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = pd.DataFrame()

    def set_df(self, df: pd.DataFrame):
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if self._df is None else len(self._df)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if self._df is None else len(self._df.columns)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or self._df is None:
            return None
        if role == QtCore.Qt.DisplayRole:
            try:
                v = self._df.iat[index.row(), index.column()]
                return "" if pd.isna(v) else str(v)
            except Exception:
                return ""
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if self._df is None:
            return None
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                try: return str(self._df.columns[section])
                except Exception: return ""
            else:
                return str(section + 1)
        return None

    def sort(self, column: int, order: QtCore.Qt.SortOrder = QtCore.Qt.AscendingOrder):
        if self._df is None or self._df.empty:
            return
        colname = self._df.columns[column]
        s = pd.to_numeric(self._df[colname], errors="ignore")
        self.layoutAboutToBeChanged.emit()
        self._df = (self._df.assign(**{colname: s})
                          .sort_values(by=colname, ascending=(order == QtCore.Qt.AscendingOrder), kind="mergesort")
                          .reset_index(drop=True))
        self.layoutChanged.emit()

# ------------------------------
# Checkable ComboBox (multi select)
# ------------------------------
class CheckableComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModel(QtGui.QStandardItemModel(self))
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("Select…")
        lv = QtWidgets.QListView(self)
        lv.setUniformItemSizes(True)
        lv.setWordWrap(False)
        lv.setMinimumWidth(280)
        lv.setMinimumHeight(220)  # กันความสูงเป็น 0
        self.setView(lv)

        # สำคัญ: กันโฟกัสหลุดแล้ว popup ปิด/ซ่อน
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.model().dataChanged.connect(lambda *args: self._update_display_text())
        self.model().rowsInserted.connect(lambda *args: self._update_display_text())
        self.model().rowsRemoved.connect(lambda *args: self._update_display_text())

    def set_items(self, items: List[str]):
        m: QtGui.QStandardItemModel = self.model()  # type: ignore
        m.blockSignals(True)
        m.clear()
        for text in items:
            it = QtGui.QStandardItem(text)
            it.setFlags(QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEnabled)
            it.setData(QtCore.Qt.Unchecked, QtCore.Qt.CheckStateRole)
            m.appendRow(it)
        m.blockSignals(False)
        self._update_display_text()

    def checked_items(self) -> List[str]:
        out: List[str] = []
        m: QtGui.QStandardItemModel = self.model()  # type: ignore
        for i in range(m.rowCount()):
            it: QtGui.QStandardItem = m.item(i)
            if it.checkState() == QtCore.Qt.Checked:
                out.append(it.text())
        return out

    def clear_checks(self):
        m: QtGui.QStandardItemModel = self.model()  # type: ignore
        for i in range(m.rowCount()):
            it = m.item(i)
            it.setCheckState(QtCore.Qt.Unchecked)
        self._update_display_text()

    def _update_display_text(self):
        sel = self.checked_items()
        if not sel:
            txt = ""
        elif len(sel) <= 3:
            txt = ", ".join(sel)
        else:
            txt = f"{len(sel)} selected"
        self.lineEdit().setText(txt)

    def showPopup(self) -> None:
        # ให้ QComboBox เตรียม popup ก่อน
        super().showPopup()
        view = self.view()
        if isinstance(view, QtWidgets.QListView):
            # กว้างพอสำหรับข้อความยาว
            w = max(view.sizeHintForColumn(0) + 48, self.width())
            view.setMinimumWidth(w)

            # ดันขึ้นบนสุด + กันไปอยู่ข้างหลัง widget อื่น
            view.setWindowFlags(
                QtCore.Qt.Popup
                | QtCore.Qt.FramelessWindowHint
                | QtCore.Qt.WindowStaysOnTopHint
            )
            view.raise_()
            view.activateWindow()
            view.setFocus(QtCore.Qt.PopupFocusReason)

            # บังคับความสูงตามจำนวนแถว (ไม่ให้ 0px)
            rows = self.model().rowCount()
            h = min(320, max(220, rows * 24 + 8))
            view.setFixedHeight(h)

            # บางเครื่องต้องรีโปสิชันใต้ combobox แบบกำหนดเอง
            gp = self.mapToGlobal(self.rect().bottomLeft())
            view.move(gp.x(), gp.y())

# ------------------------------
# Utility funcs
# ------------------------------
_DEF_DELIMS = ["\t", "|", ";", ","]

def set_table_defaults(tv: QTableView):
    tv.setAlternatingRowColors(True)
    tv.setSortingEnabled(True)
    tv.setSelectionBehavior(QTableView.SelectRows)
    tv.setSelectionMode(QTableView.ExtendedSelection)
    tv.setWordWrap(False)
    tv.horizontalHeader().setStretchLastSection(True)
    tv.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    tv.verticalHeader().setVisible(False)
    tv.verticalHeader().setDefaultSectionSize(26)
    tv.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
    tv.horizontalHeader().setMinimumSectionSize(72)
    tv.horizontalHeader().setMinimumSectionSize(60)


def _copy_selection_as_csv(view: QTableView):
    sel = view.selectionModel().selectedRows()
    if not sel:
        return
    model = view.model()
    cols = model.columnCount()
    out = io.StringIO(); w = csv.writer(out)
    w.writerow([model.headerData(c, QtCore.Qt.Horizontal) for c in range(cols)])
    for idx in sel:
        r = idx.row()
        w.writerow([model.data(model.index(r, c), QtCore.Qt.DisplayRole) for c in range(cols)])
    QtWidgets.QApplication.clipboard().setText(out.getvalue())

# Clean DataFrame to string-safe (no "nan")
def df_to_str(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        out[c] = pd.Series(out[c], dtype="string").fillna("")
    return out

# Auto detect delimiter from file content

def read_any(path: Path) -> pd.DataFrame:
    p = str(path).lower()
    if p.endswith((".xls", ".xlsx")):
        df = pd.read_excel(str(path))
        return df_to_str(df)

    delim = ","
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(4096)
        for d in _DEF_DELIMS:
            if d in head:
                delim = d; break
    except Exception:
        pass

    last_err = None
    for enc in ("utf-8", "utf-8-sig", "cp874", "tis-620", "latin1"):
        try:
            df = pd.read_csv(str(path), sep=delim, dtype=str, encoding=enc)
            return df_to_str(df)
        except Exception as e:
            last_err = e
    raise last_err if last_err else RuntimeError("Cannot read file")

# ------------------------------
# Main widget
# ------------------------------

def force_combo_popup(combo: QtWidgets.QComboBox):
    """Make any QComboBox use a top-level QListView popup that won't be clipped/hidden."""
    view = QtWidgets.QListView()  # ไม่มี parent → เป็น top-level จริง ๆ
    view.setUniformItemSizes(True)
    view.setWordWrap(False)
    view.setMinimumWidth(280)
    view.setMinimumHeight(220)
    combo.setView(view)
    combo.setFocusPolicy(QtCore.Qt.StrongFocus)

    # ยก popup ขึ้นทุกครั้งก่อนแสดง
    old_show = combo.showPopup
    def _show():
        old_show()
        v = combo.view()
        if isinstance(v, QtWidgets.QListView):
            w = max(v.sizeHintForColumn(0) + 48, combo.width())
            v.setMinimumWidth(w)
            v.setWindowFlags(QtCore.Qt.Popup | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
            v.raise_(); v.activateWindow(); v.setFocus(QtCore.Qt.PopupFocusReason)
            rows = combo.model().rowCount()
            h = min(320, max(220, rows * 24 + 8))
            v.setFixedHeight(h)
            gp = combo.mapToGlobal(combo.rect().bottomLeft())
            v.move(gp.x(), gp.y())
    combo.showPopup = _show  # type: ignore[attr-defined]


class EditDataView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Data – Fresh")
        self.resize(1380, 820)

        # Data holders
        self.df_raw: Optional[pd.DataFrame] = None
        self.df_out: Optional[pd.DataFrame] = None
        self._current_path: Optional[Path] = None
        self.preview_limit = 5000

        # History (undo/redo)
        self._hist: List[Tuple[pd.DataFrame, str]] = []
        self._redo_stack: List[Tuple[pd.DataFrame, str]] = []
        self._max_hist = 50

        # Status bar
        self.status = QStatusBar(self); self.status.setSizeGripEnabled(False)

        # Toolbar
        self.btn_open = QPushButton("Open…")
        self.btn_reload = QPushButton("Reload")
        self.btn_reset_out = QPushButton("Reset Output")
        self.btn_undo = QPushButton("Undo")
        self.btn_redo = QPushButton("Redo")
        self.chk_dryrun = QCheckBox("Dry‑run (preview)")
        self.cmb_limit = QComboBox(); self.cmb_limit.addItems(["1000","5000","20000","All"]); self.cmb_limit.setCurrentText("5000")
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_xlsx = QPushButton("Export Excel")

        # Root layout
        root = QVBoxLayout(self); root.setContentsMargins(10,10,10,10); root.setSpacing(6)

        # Top bar
        top = QHBoxLayout(); top.setSpacing(6)
        for w in (self.btn_open, self.btn_reload, self.btn_reset_out, self.btn_undo, self.btn_redo):
            w.setMinimumHeight(28)
        top.addWidget(self.btn_open); top.addWidget(self.btn_reload); top.addWidget(self.btn_reset_out)
        top.addWidget(self.btn_undo); top.addWidget(self.btn_redo)
        top.addStretch(1)
        top.addWidget(self.chk_dryrun)
        top.addStretch(1)
        top.addWidget(QLabel("Preview limit:")); top.addWidget(self.cmb_limit)
        top.addStretch(1)
        top.addWidget(self.btn_export_csv); top.addWidget(self.btn_export_xlsx)
        root.addLayout(top)

        # --- Main body with splitters (Preview top 70%, Tools bottom 30%)
        self.main_split = QtWidgets.QSplitter(QtCore.Qt.Vertical)

        # TOP: dual preview side-by-side (Input 50 : Output 50)
        self.preview_split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        gb_in = QGroupBox("Input (Raw)"); in_lay = QVBoxLayout(gb_in); in_lay.setContentsMargins(8,8,8,8)
        self.view_raw = QTableView(); self.model_raw = _PandasModel(); self.view_raw.setModel(self.model_raw)
        set_table_defaults(self.view_raw)
        in_lay.addWidget(self.view_raw)

        gb_out = QGroupBox("Output"); out_lay = QVBoxLayout(gb_out); out_lay.setContentsMargins(8,8,8,8)
        self.view_out = QTableView(); self.model_out = _PandasModel(); self.view_out.setModel(self.model_out)
        set_table_defaults(self.view_out)
        out_lay.addWidget(self.view_out)

        self.view_raw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view_out.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view_raw.customContextMenuRequested.connect(lambda p: self._table_menu(self.view_raw, p))
        self.view_out.customContextMenuRequested.connect(lambda p: self._table_menu(self.view_out, p))

        self.preview_split.addWidget(gb_in)
        self.preview_split.addWidget(gb_out)
        self.preview_split.setStretchFactor(0, 1)
        self.preview_split.setStretchFactor(1, 1)

        # BOTTOM: compact tools (tabs) full width
        self.tabs = QtWidgets.QTabWidget(); self.tabs.setTabPosition(QtWidgets.QTabWidget.North)
        self.tabs.setElideMode(QtCore.Qt.ElideNone)
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._init_tab_trim()
        self._init_tab_delete()
        self._init_tab_pad()
        self._init_tab_group()
        self._init_tab_calc()

        bottom_tools = QtWidgets.QWidget(); tools_lay = QVBoxLayout(bottom_tools); tools_lay.setContentsMargins(0,0,0,0); tools_lay.addWidget(self.tabs)

        # Assemble main splitter
        self.main_split.addWidget(self.preview_split)
        self.main_split.addWidget(bottom_tools)
        self.main_split.setStretchFactor(0, 7)  # 70%
        self.main_split.setStretchFactor(1, 3)  # 30%

        root.addWidget(self.main_split, 1)
        root.addWidget(self.status)

        # Shortcuts
        self.sc_open = QShortcut(QtGui.QKeySequence("Ctrl+O"), self); self.sc_open.activated.connect(self._open)
        self.sc_reload = QShortcut(QtGui.QKeySequence("F5"), self); self.sc_reload.activated.connect(self._reload)
        self.sc_save_csv = QShortcut(QtGui.QKeySequence("Ctrl+S"), self); self.sc_save_csv.activated.connect(self._export_csv)
        self.sc_save_xlsx = QShortcut(QtGui.QKeySequence("Ctrl+Shift+S"), self); self.sc_save_xlsx.activated.connect(self._export_xlsx)
        self.sc_undo = QShortcut(QtGui.QKeySequence("Ctrl+Z"), self); self.sc_undo.activated.connect(self._undo_action)
        self.sc_redo = QShortcut(QtGui.QKeySequence("Ctrl+Y"), self); self.sc_redo.activated.connect(self._redo_action)

        # Wire topbar
        self.btn_open.clicked.connect(self._open)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_reset_out.clicked.connect(self._reset_output)
        self.cmb_limit.currentTextChanged.connect(self._on_limit_changed)
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_xlsx.clicked.connect(self._export_xlsx)
        self.btn_undo.clicked.connect(self._undo_action)
        self.btn_redo.clicked.connect(self._redo_action)

    # ------------------------------
    # Tabs
    # ------------------------------
    def _init_tab_trim(self):
        # Filter + Trim operation (Excel-like)
        w = QGroupBox("Trim (with Filter)"); lay = QVBoxLayout(w)

        # Filter row
        fr = QHBoxLayout()
        self.trim_filter_col = QComboBox(); self.trim_filter_mode = QComboBox(); self.trim_filter_mode.addItems([
            "(all)", "contains", "equals", "startswith", "endswith", "regex"
        ])
        self.trim_filter_q = QLineEdit(); self.trim_filter_q.setPlaceholderText("filter query (optional)")
        fr.addWidget(QLabel("Filter col")); fr.addWidget(self.trim_filter_col, 2)
        fr.addWidget(QLabel("Mode")); fr.addWidget(self.trim_filter_mode)
        fr.addWidget(QLabel("Query")); fr.addWidget(self.trim_filter_q, 2)
        lay.addLayout(fr)

        # Operation row
        orow = QHBoxLayout()
        self.trim_target_col = QComboBox()
        self.trim_op = QComboBox(); self.trim_op.addItems([
            "Keep left N", "Keep right N", "Remove left N", "Remove right N",
            "Remove substring", "Strip chars (both)", "Strip left chars", "Strip right chars"
        ])
        self.trim_n = QSpinBox(); self.trim_n.setRange(0, 10000); self.trim_n.setValue(0)
        self.trim_sub = QLineEdit(); self.trim_sub.setPlaceholderText("substring / chars")
        self.btn_trim_apply = QPushButton("Apply")
        orow.addWidget(QLabel("Target col")); orow.addWidget(self.trim_target_col, 2)
        orow.addWidget(QLabel("Op")); orow.addWidget(self.trim_op, 2)
        orow.addWidget(QLabel("N / Text")); orow.addWidget(self.trim_n); orow.addWidget(self.trim_sub, 2)
        orow.addWidget(self.btn_trim_apply)
        lay.addLayout(orow)

        note = QLabel("ถ้าไม่ใส่ Filter จะใช้กับทุกแถว | Keep/Remove ใช้ N | Remove substring/Strip ใช้ช่อง Text")
        note.setStyleSheet("color:#6b7280;")
        lay.addWidget(note)

        self.btn_trim_apply.clicked.connect(self._do_trim)
        self._top_align(w, lay); self.tabs.addTab(w, "Trim")

    def _init_tab_delete(self):
        w = QGroupBox("Delete rows by Filter"); lay = QVBoxLayout(w)
        r = QHBoxLayout()
        self.del_col = QComboBox(); self.del_mode = QComboBox(); self.del_mode.addItems([
            "contains", "equals", "startswith", "endswith", "regex"
        ])
        self.del_q = QLineEdit(); self.del_q.setPlaceholderText("query to match")
        self.btn_del_apply = QPushButton("Delete matched rows")
        r.addWidget(QLabel("Column")); r.addWidget(self.del_col, 2)
        r.addWidget(QLabel("Mode")); r.addWidget(self.del_mode)
        r.addWidget(QLabel("Query")); r.addWidget(self.del_q, 2)
        r.addWidget(self.btn_del_apply)
        lay.addLayout(r)
        note = QLabel("ตัวอย่าง: contains + cs1 → ลบทุกแถวที่มี cs1 ในคอลัมน์ที่เลือก | regex รองรับแพทเทิร์นเต็มรูปแบบ")
        note.setStyleSheet("color:#6b7280;")
        lay.addWidget(note)
        self.btn_del_apply.clicked.connect(self._do_delete)
        self._top_align(w, lay); self.tabs.addTab(w, "Delete")

    def _init_tab_pad(self):
        w = QGroupBox("Pad"); lay = QVBoxLayout(w)
        r = QHBoxLayout()
        self.pad_col = QComboBox(); self.pad_side = QComboBox(); self.pad_side.addItems(["Left", "Right"])
        self.pad_len = QSpinBox(); self.pad_len.setRange(1, 10000); self.pad_len.setValue(8)
        self.pad_char = QLineEdit(); self.pad_char.setMaxLength(1); self.pad_char.setText("0")
        self.pad_only_shorter = QCheckBox("Only rows shorter than length"); self.pad_only_shorter.setChecked(True)
        self.btn_pad_apply = QPushButton("Apply")
        r.addWidget(QLabel("Column")); r.addWidget(self.pad_col, 2)
        r.addWidget(QLabel("Side")); r.addWidget(self.pad_side)
        r.addWidget(QLabel("Length")); r.addWidget(self.pad_len)
        r.addWidget(QLabel("Fill")); r.addWidget(self.pad_char)
        r.addWidget(self.pad_only_shorter); r.addWidget(self.btn_pad_apply)
        lay.addLayout(r)
        note = QLabel("ถ้า Fill=0 และ Side=Left จะใช้ zfill(); เปิด Only-shorter เพื่อไม่เขียนทับค่าที่ยาวพอแล้ว")
        note.setStyleSheet("color:#6b7280;")
        lay.addWidget(note)
        self.btn_pad_apply.clicked.connect(self._do_pad)
        self._top_align(w, lay); self.tabs.addTab(w, "Pad")

    def _init_tab_group(self):
        w = QGroupBox("Group / Aggregate"); lay = QVBoxLayout(w)

        mode_box = QGroupBox("Mode"); mode_l = QHBoxLayout(mode_box)
        self.rb_group = QtWidgets.QRadioButton("Group only")
        self.rb_sum   = QtWidgets.QRadioButton("Agg only")
        self.rb_both  = QtWidgets.QRadioButton("Group + Agg"); self.rb_both.setChecked(True)
        for rb in (self.rb_group, self.rb_sum, self.rb_both): mode_l.addWidget(rb)
        lay.addWidget(mode_box)

        r = QHBoxLayout()
        self.lbl_group_by = QLabel("Group by"); self.grp_cols = CheckableComboBox(); self.grp_cols.setMinimumWidth(240)
        self.lbl_sum_cols = QLabel("Agg columns"); self.sum_cols = CheckableComboBox(); self.sum_cols.setMinimumWidth(240)
        self.lbl_aggs = QLabel("Functions"); self.agg_funcs = CheckableComboBox(); self.agg_funcs.setMinimumWidth(200)
        self.agg_funcs.set_items(["sum","avg","min","max","count_distinct"])
        self.btn_group_apply = QPushButton("Run")
        r.addWidget(self.lbl_group_by); r.addWidget(self.grp_cols,2)
        r.addWidget(self.lbl_sum_cols); r.addWidget(self.sum_cols,2)
        r.addWidget(self.lbl_aggs); r.addWidget(self.agg_funcs,1)
        r.addWidget(self.btn_group_apply)
        lay.addLayout(r)

        note = QLabel("Group only → count per group | Agg only → รวมทั้งตาราง | Group+Agg → group แล้วคำนวณหลายฟังก์ชันได้")
        note.setStyleSheet("color:#6b7280;")
        note.setWordWrap(True)
        lay.addWidget(note)

        self.btn_group_apply.clicked.connect(self._do_group_sum)
        self.rb_group.toggled.connect(self._update_group_sum_visibility)
        self.rb_sum.toggled.connect(self._update_group_sum_visibility)
        self.rb_both.toggled.connect(self._update_group_sum_visibility)
        self._update_group_sum_visibility()

        self._top_align(w, lay); self.tabs.addTab(w, "Group / Sum")

    def _init_tab_calc(self):
        w = QGroupBox("Calculation"); lay = QVBoxLayout(w)
        r1 = QHBoxLayout()
        self.cal_a = QComboBox();
        self.cal_op = QComboBox(); self.cal_op.addItems(["+","-","*","/","//","%"])
        self.cal_b = QComboBox();
        self.cal_use_const_left = QCheckBox("const ⟵ A")  # constant op B
        self.cal_use_const_right = QCheckBox("B ⟵ const") # A op constant
        self.cal_const = QLineEdit(); self.cal_const.setPlaceholderText("constant value")
        r1.addWidget(QLabel("Col A")); r1.addWidget(self.cal_a,2)
        r1.addWidget(QLabel("Op")); r1.addWidget(self.cal_op)
        r1.addWidget(QLabel("Col B")); r1.addWidget(self.cal_b,2)
        r1.addWidget(self.cal_use_const_left)
        r1.addWidget(self.cal_use_const_right)
        r1.addWidget(self.cal_const)
        lay.addLayout(r1)

        r2 = QHBoxLayout()
        self.cal_out = QLineEdit(); self.cal_out.setPlaceholderText("result column name")
        self.btn_calc = QPushButton("Compute")
        r2.addWidget(QLabel("Output")); r2.addWidget(self.cal_out)
        r2.addWidget(self.btn_calc)
        lay.addLayout(r2)
        note = QLabel("หารด้วยศูนย์จะให้ค่าเป็นว่าง (NA). เลือก const เพื่อใช้ค่าคงที่แทนคอลัมน์ฝั่งซ้าย/ขวา")
        note.setStyleSheet("color:#6b7280;")
        lay.addWidget(note)
        self.btn_calc.clicked.connect(self._do_calc)
        self._top_align(w, lay); self.tabs.addTab(w, "Calculation")

    # ------------------------------
    # Initial sizing (70/30 and 50/50)
    # ------------------------------
    def showEvent(self, e: QtGui.QShowEvent):
        super().showEvent(e)
        if not hasattr(self, "_sizes_set"):
            self._sizes_set = True
            # Set vertical split sizes: 70% preview, 30% tools
            h = max(800, self.height())
            self.main_split.setSizes([int(h*0.7), int(h*0.3)])
            # Set horizontal split sizes: 50/50 for input/output
            w = max(1200, self.width())
            self.preview_split.setSizes([int(w*0.5), int(w*0.5)])

    # ------------------------------
    # Menus
    # ------------------------------
    def _table_menu(self, view: QTableView, pos: QtCore.QPoint):
        m = QtWidgets.QMenu(view)
        act_copy = m.addAction("Copy selected rows as CSV")
        if m.exec_(view.viewport().mapToGlobal(pos)) == act_copy:
            _copy_selection_as_csv(view)

    # ------------------------------
    # History helpers
    # ------------------------------
    def _push_history(self, df: pd.DataFrame, desc: str):
        # limit size & clear redo on new action
        self._hist.append((df.copy(), desc))
        if len(self._hist) > self._max_hist:
            self._hist = self._hist[-self._max_hist:]
        self._redo_stack.clear()

    def _undo_action(self):
        if not self._hist:
            return
        cur = (self.df_out.copy() if self.df_out is not None else pd.DataFrame(), "current")
        self._redo_stack.append(cur)
        last_df, _ = self._hist.pop()
        self.df_out = last_df.copy()
        self._set_preview(self.df_out)
        self._refresh_comboboxes()
        self.status.showMessage("Undo ✓", 1500)

    def _redo_action(self):
        if not self._redo_stack:
            return
        cur = (self.df_out.copy() if self.df_out is not None else pd.DataFrame(), "current")
        self._hist.append(cur)
        df, _ = self._redo_stack.pop()
        self.df_out = df.copy()
        self._set_preview(self.df_out)
        self._refresh_comboboxes()
        self.status.showMessage("Redo ✓", 1500)

    def _commit_or_preview(self, new_df: pd.DataFrame, desc: str):
        if self.chk_dryrun.isChecked():
            dlg = _PreviewDialog(self, f"Preview – {desc}", new_df, limit=1000)
            if dlg.exec_() != QDialog.Accepted:
                self.status.showMessage("Preview canceled", 1500)
                return
        # commit
        self._push_history(self.df_out if self.df_out is not None else pd.DataFrame(), desc)
        self.df_out = df_to_str(new_df)
        self._set_preview(self.df_out); self._refresh_comboboxes()
        self.status.showMessage(
            f"Columns loaded: {len(cols)} → {', '.join(cols[:6])}{'…' if len(cols)>6 else ''}",
            2500
        )


    # ------------------------------
    # Topbar actions
    # ------------------------------
    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open file", str(Path.home()),
                                              "Data files (*.csv *.tsv *.txt *.dat *.log *.xls *.xlsx);;All files (*.*)")
        if not path:
            return
        self._load_file(Path(path))

    def _reload(self):
        if not self._current_path:
            return
        self._load_file(self._current_path)

    def _reset_output(self):
        if self.df_raw is None:
            return
        self._push_history(self.df_out if self.df_out is not None else pd.DataFrame(), "reset_output")
        self.df_out = self.df_raw.copy()
        self._set_preview(self.df_out)
        self._refresh_comboboxes()

    def _on_limit_changed(self, text: str):
        self.preview_limit = 0 if text == "All" else int(text or 0)
        if self.df_raw is not None:
            self._set_preview(self.df_raw, raw=True)
        if self.df_out is not None:
            self._set_preview(self.df_out)

    def _export_csv(self):
        if self.df_out is None or self.df_out.empty:
            QMessageBox.information(self, "Export CSV", "ไม่มีข้อมูลใน Output ให้ส่งออก")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "output.csv", "CSV (*.csv)")
        if not path:
            return
        with _Busy(self, "Exporting CSV", self.status):
            self.df_out.to_csv(path, index=False, encoding="utf-8-sig")

    def _export_xlsx(self):
        if self.df_out is None or self.df_out.empty:
            QMessageBox.information(self, "Export Excel", "ไม่มีข้อมูลใน Output ให้ส่งออก")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "output.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        with _Busy(self, "Exporting Excel", self.status):
            self.df_out.to_excel(path, index=False)

    # ------------------------------
    # Load & Preview
    # ------------------------------
    def _load_file(self, path: Path):
        self._current_path = path
        with _Busy(self, f"Loading {path.name}", self.status):
            try:
                df = read_any(path)
            except Exception as e:
                QMessageBox.warning(self, "Open file", f"เปิดไฟล์ไม่สำเร็จ: {e}")
                return
        self.df_raw = df.copy(); self.df_out = df.copy()
        self._hist.clear(); self._redo_stack.clear()
        self._set_preview(self.df_raw, raw=True)
        self._set_preview(self.df_out)
        self._refresh_comboboxes()

    def _set_preview(self, df: pd.DataFrame, raw: bool = False):
        show = df if (self.preview_limit == 0 or len(df) <= self.preview_limit) else df.head(self.preview_limit)
        (self.model_raw if raw else self.model_out).set_df(show)

    def _refresh_comboboxes(self):
        # Force refresh of all combo boxes and ensure Group/Sum tabs get current columns
        cols = []
        # Prefer output, fallback to raw
        if self.df_out is not None and len(self.df_out.columns) > 0:
            cols = list(self.df_out.columns)
        elif self.df_raw is not None and len(self.df_raw.columns) > 0:
            cols = list(self.df_raw.columns)

        # Update normal combo boxes
        for cb in (
            getattr(self, 'trim_filter_col', None),
            getattr(self, 'trim_target_col', None),
            getattr(self, 'del_col', None),
            getattr(self, 'pad_col', None),
            getattr(self, 'cal_a', None),
            getattr(self, 'cal_b', None),
        ):
            if cb:
                cb.blockSignals(True)
                cb.clear()
                cb.addItems(cols)
                cb.blockSignals(False)

        # Update checkable combo boxes safely
        if hasattr(self, 'grp_cols') and self.grp_cols:
            self.grp_cols.set_items(cols)
        if hasattr(self, 'sum_cols') and self.sum_cols:
            self.sum_cols.set_items(cols)
        if hasattr(self, 'agg_funcs') and self.agg_funcs:
            self.agg_funcs.set_items(["sum", "avg", "min", "max", "count_distinct"])

        # Debug indicator if nothing loaded
        if not cols:
            self.status.showMessage("⚠️ No columns available — please open a file first", 4000)

    def _top_align(self, w: QWidget, lay: QVBoxLayout):
        lay.addStretch(1)
        w.setLayout(lay)

    # def _top_align(self, w: QWidget, lay: QVBoxLayout):
    #     lay.addStretch(1); w.setLayout(lay)(self, w: QWidget, lay: QVBoxLayout):
    #     lay.addStretch(1); w.setLayout(lay)

    def _top_align(self, w: QWidget, lay: QVBoxLayout):
        lay.addStretch(1)
        w.setLayout(lay)


    # ------------------------------
    # Filters
    # ------------------------------
    @staticmethod
    def _build_mask(df: pd.DataFrame, col: str, mode: str, q: str) -> pd.Series:
        if not col or col not in df.columns or mode == "(all)" or not q:
            return pd.Series([True]*len(df))
        s = df[col].astype(str)
        if mode == "contains":
            pat = re.escape(q)
            return s.str.contains(pat, na=False, regex=True)
        if mode == "equals":
            return s == q
        if mode == "startswith":
            return s.str.startswith(q, na=False)
        if mode == "endswith":
            return s.str.endswith(q, na=False)
        if mode == "regex":
            try:
                return s.str.contains(q, na=False, regex=True)
            except Exception:
                return pd.Series([False]*len(df))
        return pd.Series([True]*len(df))

    # ------------------------------
    # Actions
    # ------------------------------
    def _do_trim(self):
        if self.df_out is None or self.df_out.empty:
            return
        fcol = self.trim_filter_col.currentText(); fmode = self.trim_filter_mode.currentText(); fq = self.trim_filter_q.text().strip()
        tcol = self.trim_target_col.currentText(); op = self.trim_op.currentText()
        n = int(self.trim_n.value()); text = self.trim_sub.text()
        if not tcol or tcol not in self.df_out.columns:
            return
        with _Busy(self, "Trimming", self.status):
            df = self.df_out.copy(); mask = self._build_mask(df, fcol, fmode, fq)
            s = df.loc[mask, tcol].astype(str)
            if op == "Keep left N":
                df.loc[mask, tcol] = s.str.slice(0, n)
            elif op == "Keep right N":
                df.loc[mask, tcol] = s.str.slice(-n)
            elif op == "Remove left N":
                df.loc[mask, tcol] = s.str.slice(n)
            elif op == "Remove right N":
                df.loc[mask, tcol] = s.str.slice(0, s.str.len()-n)
            elif op == "Remove substring":
                if text:
                    df.loc[mask, tcol] = s.str.replace(re.escape(text), "", regex=True)
            elif op == "Strip chars (both)":
                df.loc[mask, tcol] = s.str.strip(text or None)
            elif op == "Strip left chars":
                df.loc[mask, tcol] = s.str.lstrip(text or None)
            elif op == "Strip right chars":
                df.loc[mask, tcol] = s.str.rstrip(text or None)
        desc = f"trim:{tcol} [{op}]"
        self._commit_or_preview(df, desc)

    def _do_delete(self):
        if self.df_out is None or self.df_out.empty:
            return
        col = self.del_col.currentText(); mode = self.del_mode.currentText(); q = self.del_q.text().strip()
        if not col or col not in self.df_out.columns or not q:
            return
        with _Busy(self, "Deleting rows", self.status):
            df0 = self.df_out.copy(); mask = self._build_mask(df0, col, mode, q)
            df = df0.loc[~mask].copy()
        desc = f"delete:{col} {mode} {q}"
        self._commit_or_preview(df, desc)

    def _do_pad(self):
        if self.df_out is None or self.df_out.empty:
            return
        col = self.pad_col.currentText(); side = self.pad_side.currentText()
        n = int(self.pad_len.value()); ch = (self.pad_char.text() or " ")[0]
        only_shorter = self.pad_only_shorter.isChecked()
        if not col or col not in self.df_out.columns or n <= 0:
            return
        with _Busy(self, "Padding", self.status):
            df = self.df_out.copy(); s = df[col].astype(str)
            if only_shorter:
                need = s.str.len() < n
            else:
                need = pd.Series([True]*len(df))
            if side == "Left":
                val = s.str.zfill(n) if ch == "0" else s.str.pad(n, side="left", fillchar=ch)
            else:
                val = s.str.pad(n, side="right", fillchar=ch)
            df.loc[need, col] = val[need]
        desc = f"pad:{col} {side} {n} '{ch}'{' shorter' if only_shorter else ''}"
        self._commit_or_preview(df, desc)

    def _update_group_sum_visibility(self):
        g_on = self.rb_group.isChecked(); s_on = self.rb_sum.isChecked(); b_on = self.rb_both.isChecked()
        show_g = g_on or b_on; show_s = s_on or b_on
        for w in (self.lbl_group_by, self.grp_cols): w.setVisible(show_g)
        for w in (self.lbl_sum_cols, self.sum_cols, self.lbl_aggs, self.agg_funcs): w.setVisible(show_s)
        if show_g and not show_s:
            self.sum_cols.clear_checks(); self.agg_funcs.clear_checks()
        if show_s and not show_g:
            self.grp_cols.clear_checks()
        self.grp_cols._update_display_text(); self.sum_cols._update_display_text(); self.agg_funcs._update_display_text()

    def _do_group_sum(self):
        if self.df_out is None or self.df_out.empty:
            return
        grp = [c for c in self.grp_cols.checked_items() if c]
        cols = [c for c in self.sum_cols.checked_items() if c]
        funcs = [f for f in self.agg_funcs.checked_items() if f]
        mode = "Group only" if self.rb_group.isChecked() else ("Agg only" if self.rb_sum.isChecked() else "Group + Agg")
        with _Busy(self, f"Running {mode}", self.status):
            df = self.df_out.copy()
            def auto_numeric(exclude=None):
                exclude = set(exclude or [])
                out = []
                for c in df.columns:
                    if c in exclude: continue
                    s = pd.to_numeric(df[c], errors="coerce")
                    if len(s) and s.notna().mean() >= 0.5:
                        out.append(c)
                return out

            agg_map: Dict[str, Callable] = {
                "sum": "sum",
                "avg": "mean",
                "min": "min",
                "max": "max",
                "count_distinct": pd.Series.nunique,
            }

            if mode == "Group only":
                if not grp:
                    QMessageBox.information(self, "Group only", "กรุณาเลือก Group by อย่างน้อย 1 คอลัมน์"); return
                g = df.groupby(grp, dropna=False).size().reset_index(name="count")
            elif mode == "Agg only":
                if not cols:
                    cols = auto_numeric()
                    if not cols:
                        QMessageBox.information(self, "Agg only", "ไม่พบคอลัมน์ตัวเลขสำหรับ aggregate"); return
                if not funcs:
                    funcs = ["sum"]
                agg_spec = {c: [agg_map[f] for f in funcs] for c in cols}
                g = df.assign(**{c: pd.to_numeric(df[c], errors="coerce") for c in cols}).agg(agg_spec)
                g.columns = [f"{c}_{f}" for c, f in g.columns]
                g = g.to_frame().T
            else:  # Group + Agg
                if not grp:
                    QMessageBox.information(self, "Group + Agg", "กรุณาเลือก Group by อย่างน้อย 1 คอลัมน์"); return
                if not cols:
                    cols = auto_numeric(exclude=grp)
                    if not cols:
                        QMessageBox.information(self, "Group + Agg", "ไม่พบคอลัมน์ตัวเลขสำหรับ aggregate"); return
                if not funcs:
                    funcs = ["sum"]
                agg_spec = {c: [agg_map[f] for f in funcs] for c in cols}
                g = (
                    df.assign(**{c: pd.to_numeric(df[c], errors="coerce") for c in cols})
                      .groupby(grp, dropna=False)
                      .agg(agg_spec)
                )
                # flatten columns
                g.columns = [f"{c}_{f}" for c, f in g.columns]
                g = g.reset_index()
        desc = f"group/agg:{mode}"
        self._commit_or_preview(g, desc)

    def _do_calc(self):
        if self.df_out is None or self.df_out.empty:
            return
        a = self.cal_a.currentText(); b = self.cal_b.currentText(); op = self.cal_op.currentText()
        outname = (self.cal_out.text().strip() or "result")
        use_left = self.cal_use_const_left.isChecked()
        use_right = self.cal_use_const_right.isChecked()
        const_txt = self.cal_const.text().strip()
        if use_left and use_right:
            QMessageBox.information(self, "Calculation", "เลือก const ได้เพียงด้านเดียว (ซ้ายหรือขวา)"); return
        if (not use_left and not a) or (not use_right and not b):
            return
        with _Busy(self, "Computing", self.status):
            df = self.df_out.copy()
            def to_num(x):
                return pd.to_numeric(x, errors="coerce")
            if use_left:
                s1 = to_num(const_txt)
            else:
                s1 = to_num(df[a])
            if use_right:
                s2 = to_num(const_txt)
            else:
                s2 = to_num(df[b])
            # handle division by zero
            z = s2.replace(0, pd.NA) if isinstance(s2, pd.Series) else (pd.NA if s2 == 0 else s2)
            try:
                if op == "+":    res = (s1 + s2)
                elif op == "-":  res = (s1 - s2)
                elif op == "*":  res = (s1 * s2)
                elif op == "/":  res = (s1 / z)
                elif op == "//": res = (s1 // z)
                elif op == "%":  res = (s1 % z)
                else:              res = pd.Series([pd.NA]*len(df), dtype="Float64") if isinstance(s1, pd.Series) else pd.NA
            except Exception:
                res = pd.Series([pd.NA]*len(df), dtype="Float64") if isinstance(s1, pd.Series) else pd.NA
            if not isinstance(res, pd.Series):
                res = pd.Series([res]*len(df), dtype="Float64")
            res = pd.to_numeric(res, errors="coerce").astype("Float64")
            new_df = df.copy()
            new_df[outname] = res.astype(str).where(~res.isna(), "")
        desc = f"calc:{outname}={("const" if use_left else a)}{op}{("const" if use_right else b)}"
        self._commit_or_preview(new_df, desc)

# ------------------------------
# Entrypoint
# ------------------------------
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    # Style polish
    QtWidgets.QApplication.setStyle("Fusion")
    pal = app.palette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor(248, 249, 251))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor(255, 255, 255))
    pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(246, 247, 249))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor(244, 246, 250))
    pal.setColor(QtGui.QPalette.ButtonText, QtCore.Qt.black)
    pal.setColor(QtGui.QPalette.Text, QtCore.Qt.black)
    app.setPalette(pal)
    app.setStyleSheet(
        "QGroupBox{font-weight:600;margin-top:8px;border:1px solid #e5e7eb;border-radius:8px;padding:12px;}"
        "QGroupBox::title{top:-6px;left:8px;background:transparent;padding:0 4px;color:#111827;}"
        "QLabel{color:#111827;} QTabBar::tab{padding:8px 14px;} QTableView{gridline-color:#e5e7eb;}"
    )
    w = EditDataView(); w.show()
    sys.exit(app.exec_())
