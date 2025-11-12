#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Edit Data View (PyQt5)
รวม Trim / Delete / Pad / Group-Sum + Calculation
- Load (CSV/TSV/TXT/XLS/XLSX) + Auto delimiter (+ auto encoding)
- Preview (limit เลือกได้: 1k/5k/20k/All)
- Trim: left/right keep N chars
- Delete: contains/equals (+ %wildcard%)
- Pad: เติมอักขระซ้าย/ขวาให้ครบความยาวที่กำหนด
- Group/Sum: Group only / Sum only / Group+Sum (UI: Radio + dynamic show/hide + เลือก Source)
- Calculation: (+, -, *, /, //, %) ป้องกันหารด้วยศูนย์
- Export: CSV/Excel
- UX: Busy cursor + StatusBar, Reset Output, Preview limit, คีย์ลัด (Ctrl+O/F5/Ctrl+S/Ctrl+Shift+S)
"""

from pathlib import Path
from typing import Optional, List
import io, contextlib, csv

import pandas as pd
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QPushButton, QLabel, QLineEdit,
    QComboBox, QFileDialog, QMessageBox, QSpinBox, QStatusBar, QSizePolicy, QShortcut
)

# --- HiDPI: ตั้งก่อนสร้าง QApplication เท่านั้น ---
try:
    if QtWidgets.QApplication.instance() is None:
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
except Exception:
    pass


# =======================
# Helpers: busy cursor
# =======================
class _Busy:
    def __init__(self, widget: QWidget, msg: str, status: QStatusBar):
        self.widget = widget
        self.msg = msg
        self.status = status
    def __enter__(self):
        try:
            self.widget.setCursor(QtCore.Qt.BusyCursor)
            self.status.showMessage(f"{self.msg}…")
        except Exception:
            pass
        return self
    def __exit__(self, exc_type, exc, tb):
        try:
            self.widget.unsetCursor()
            self.status.showMessage("Done ✓" if exc_type is None else "Error ✗", 2500)
        except Exception:
            pass
        return False


# =======================
# Pandas → Qt Model
# =======================
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
                val = self._df.iat[index.row(), index.column()]
                return "" if pd.isna(val) else str(val)
            except Exception:
                return ""
        return None
    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if self._df is None:
            return None
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                try:
                    return str(self._df.columns[section])
                except Exception:
                    return ""
            else:
                return str(section)
        return None


def set_table_defaults(tv: QTableView):
    tv.setAlternatingRowColors(True)
    tv.setSortingEnabled(True)
    tv.setSelectionBehavior(QTableView.SelectRows)
    tv.setSelectionMode(QTableView.ExtendedSelection)
    tv.setWordWrap(False)
    tv.horizontalHeader().setStretchLastSection(True)
    tv.horizontalHeader().setDefaultAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
    tv.verticalHeader().setVisible(False)
    tv.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)


def _copy_selection_as_csv(view: QTableView):
    sel = view.selectionModel().selectedRows()
    if not sel:
        return
    model = view.model()
    cols = model.columnCount()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([model.headerData(c, QtCore.Qt.Horizontal) for c in range(cols)])
    for idx in sel:
        r = idx.row()
        writer.writerow([model.data(model.index(r, c), QtCore.Qt.DisplayRole) for c in range(cols)])
    QtWidgets.QApplication.clipboard().setText(out.getvalue())


# =======================
# Checkable Combo
# =======================
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
        self.setView(lv)
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
        super().showPopup()
        view = self.view()
        if isinstance(view, QtWidgets.QListView):
            w = max(self.view().sizeHintForColumn(0) + 48, self.width())
            view.setMinimumWidth(w)


# =======================
# Main Widget
# =======================
class EditDataView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Data")
        self.resize(1260, 720)

        # Data
        self.df_raw: Optional[pd.DataFrame] = None
        self.df_out: Optional[pd.DataFrame] = None
        self.preview_limit = 5000
        self._current_path: Optional[Path] = None

        # Status
        self.status = QStatusBar(self)
        self.status.setSizeGripEnabled(False)

        # Toolbar
        self.btn_open = QPushButton("Open…")
        self.btn_reload = QPushButton("Reload")
        self.btn_reset_out = QPushButton("Reset Output")
        self.cmb_limit = QComboBox()
        self.cmb_limit.addItems(["1000", "5000", "20000", "All"])
        self.cmb_limit.setCurrentText("5000")
        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_xlsx = QPushButton("Export Excel")

        # layout
        root = QVBoxLayout(self); root.setContentsMargins(10, 10, 10, 10); root.setSpacing(6)

        # --- Top bar ---
        top = QHBoxLayout()
        top.addWidget(self.btn_open); top.addWidget(self.btn_reload); top.addWidget(self.btn_reset_out)
        top.addStretch(1)
        top.addWidget(QLabel("Preview limit:")); top.addWidget(self.cmb_limit)
        top.addStretch(1)
        top.addWidget(self.btn_export_csv); top.addWidget(self.btn_export_xlsx)
        root.addLayout(top)

        mid = QHBoxLayout(); mid.setSpacing(8); root.addLayout(mid, 1)

        # ---- Left: Tools (Tabs) ----
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabPosition(QtWidgets.QTabWidget.North)
        self.tabs.setElideMode(QtCore.Qt.ElideNone)
        self.tabs.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self._init_tab_trim()
        self._init_tab_delete()
        self._init_tab_pad()
        self._init_tab_group()
        self._init_tab_calc()

        # ---- Right: Preview ----
        right = QtWidgets.QGroupBox("Preview")
        rv = QVBoxLayout(right); rv.setContentsMargins(12, 12, 12, 12); rv.setSpacing(8)

        self.view_raw = QTableView(); self.view_out = QTableView()
        self.model_raw = _PandasModel(); self.model_out = _PandasModel()
        self.view_raw.setModel(self.model_raw); self.view_out.setModel(self.model_out)
        set_table_defaults(self.view_raw); set_table_defaults(self.view_out)
        self.view_raw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view_out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.view_raw.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view_out.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view_raw.customContextMenuRequested.connect(lambda p: self._table_menu(self.view_raw, p))
        self.view_out.customContextMenuRequested.connect(lambda p: self._table_menu(self.view_out, p))

        rv.addWidget(QLabel("Raw input")); rv.addWidget(self.view_raw, 1)
        rv.addWidget(QLabel("Output")); rv.addWidget(self.view_out, 1)

        mid.addWidget(self.tabs, 0); mid.addWidget(right, 1)
        root.addWidget(self.status)

        # shortcuts
        QShortcut(QtGui.QKeySequence("Ctrl+O"), self, self._open)
        QShortcut(QtGui.QKeySequence("F5"), self, self._reload)
        QShortcut(QtGui.QKeySequence("Ctrl+S"), self, self._export_csv)
        QShortcut(QtGui.QKeySequence("Ctrl+Shift+S"), self, self._export_xlsx)

        # wire top bar
        self.btn_open.clicked.connect(self._open)
        self.btn_reload.clicked.connect(self._reload)
        self.btn_reset_out.clicked.connect(self._reset_output)
        self.cmb_limit.currentTextChanged.connect(self._on_limit_changed)
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_export_xlsx.clicked.connect(self._export_xlsx)

    # =============================
    # Tabs
    # =============================
    def _init_tab_trim(self):
        w = QtWidgets.QGroupBox("Trim"); lay = QVBoxLayout(w)
        r1 = QHBoxLayout()
        self.trim_col = QComboBox(); self.trim_side = QComboBox(); self.trim_side.addItems(["Left", "Right"])
        self.trim_keep = QSpinBox(); self.trim_keep.setRange(0, 10_000); self.trim_keep.setValue(0)
        self.btn_trim_apply = QPushButton("Apply")
        r1.addWidget(QLabel("Column")); r1.addWidget(self.trim_col, 2)
        r1.addWidget(QLabel("Side")); r1.addWidget(self.trim_side)
        r1.addWidget(QLabel("Keep")); r1.addWidget(self.trim_keep)
        r1.addWidget(self.btn_trim_apply); lay.addLayout(r1)
        note = QLabel("หมายเหตุ: Keep=0 จะได้ค่าว่าง"); note.setStyleSheet("color:#6b7280;"); lay.addWidget(note)
        self.btn_trim_apply.clicked.connect(self._do_trim)
        self._top_align(w, lay); self.tabs.addTab(w, "Trim")

    def _init_tab_delete(self):
        w = QtWidgets.QGroupBox("Delete"); lay = QVBoxLayout(w)
        r1 = QHBoxLayout()
        self.del_col = QComboBox(); self.del_mode = QComboBox(); self.del_mode.addItems(["contains", "equals"])
        self.del_q = QLineEdit(); self.btn_del_apply = QPushButton("Apply")
        r1.addWidget(QLabel("Column")); r1.addWidget(self.del_col, 2)
        r1.addWidget(QLabel("Mode")); r1.addWidget(self.del_mode)
        r1.addWidget(QLabel("Query")); r1.addWidget(self.del_q, 2)
        r1.addWidget(self.btn_del_apply); lay.addLayout(r1)
        note = QLabel("รองรับ wildcard แบบ %ABC% เมื่อเลือก contains"); note.setStyleSheet("color:#6b7280;"); lay.addWidget(note)
        self.btn_del_apply.clicked.connect(self._do_delete)
        self._top_align(w, lay); self.tabs.addTab(w, "Delete")

    def _init_tab_pad(self):
        w = QtWidgets.QGroupBox("Pad"); lay = QVBoxLayout(w)
        r1 = QHBoxLayout()
        self.pad_col = QComboBox(); self.pad_side = QComboBox(); self.pad_side.addItems(["Left", "Right"])
        self.pad_len = QSpinBox(); self.pad_len.setRange(1, 10_000); self.pad_len.setValue(8)
        self.pad_char = QLineEdit(); self.pad_char.setMaxLength(1); self.pad_char.setText("0")
        self.btn_pad_apply = QPushButton("Apply")
        r1.addWidget(QLabel("Column")); r1.addWidget(self.pad_col, 2)
        r1.addWidget(QLabel("Side")); r1.addWidget(self.pad_side)
        r1.addWidget(QLabel("Length")); r1.addWidget(self.pad_len)
        r1.addWidget(QLabel("Fill char")); r1.addWidget(self.pad_char)
        r1.addWidget(self.btn_pad_apply); lay.addLayout(r1)
        note = QLabel("เมื่อ Fill char = 0 และ Side = Left จะใช้ zfill() อัตโนมัติ"); note.setStyleSheet("color:#6b7280;"); lay.addWidget(note)
        self.btn_pad_apply.clicked.connect(self._do_pad)
        self._top_align(w, lay); self.tabs.addTab(w, "Pad")

    def _init_tab_group(self):
        w = QtWidgets.QGroupBox("Group / Sum"); lay = QVBoxLayout(w)

        # --- Mode ---
        mode_box = QtWidgets.QGroupBox("Mode"); mode_layout = QtWidgets.QHBoxLayout(mode_box)
        self.radio_group = QtWidgets.QRadioButton("Group only")
        self.radio_sum = QtWidgets.QRadioButton("Sum only")
        self.radio_both = QtWidgets.QRadioButton("Group + Sum"); self.radio_both.setChecked(True)
        for rb in (self.radio_group, self.radio_sum, self.radio_both):
            mode_layout.addWidget(rb)
        lay.addWidget(mode_box)

        # --- Source selector ---
        src_layout = QtWidgets.QHBoxLayout()
        src_layout.addWidget(QLabel("Source:"))
        self.cmb_source = QComboBox()
        self.cmb_source.addItems(["Raw input", "Current output"])
        self.cmb_source.setCurrentText("Raw input")  # ค่าเริ่มต้นใช้ข้อมูลดิบ
        src_layout.addWidget(self.cmb_source)
        src_layout.addStretch(1)
        lay.addLayout(src_layout)

        # --- Selectors ---
        r1 = QtWidgets.QHBoxLayout()
        self.lbl_group_by = QLabel("Group by"); r1.addWidget(self.lbl_group_by)
        self.grp_cols_cb = CheckableComboBox(); self.grp_cols_cb.setMinimumWidth(280); r1.addWidget(self.grp_cols_cb, 2)
        self.lbl_sum_cols = QLabel("Sum columns"); r1.addWidget(self.lbl_sum_cols)
        self.sum_cols_cb = CheckableComboBox(); self.sum_cols_cb.setMinimumWidth(280); r1.addWidget(self.sum_cols_cb, 2)
        self.btn_group_apply = QPushButton("Run"); r1.addWidget(self.btn_group_apply)
        lay.addLayout(r1)

        note = QLabel(
            "หมายเหตุ:\n"
            "• Group only → แสดง count ต่อกลุ่ม\n"
            "• Sum only → ถ้าไม่เลือก ระบบจะลองตรวจคอลัมน์ตัวเลขให้อัตโนมัติ\n"
            "• Group + Sum → ถ้าไม่เลือก Sum columns จะ auto-detect ตัวเลข (ยกเว้น Group by)"
        )
        note.setStyleSheet("color:#6b7280;"); note.setWordWrap(True); lay.addWidget(note)

        self.btn_group_apply.clicked.connect(self._do_group_sum)
        self.radio_group.toggled.connect(self._update_group_sum_visibility)
        self.radio_sum.toggled.connect(self._update_group_sum_visibility)
        self.radio_both.toggled.connect(self._update_group_sum_visibility)
        self._update_group_sum_visibility()

        self._top_align(w, lay); self.tabs.addTab(w, "Group / Sum")

    def _init_tab_calc(self):
        w = QtWidgets.QGroupBox("Calculation"); lay = QVBoxLayout(w)
        r1 = QHBoxLayout()
        self.cal_c1 = QComboBox(); self.cal_op = QComboBox(); self.cal_op.addItems(["+", "-", "*", "/", "//", "%"])
        self.cal_c2 = QComboBox(); self.cal_out = QLineEdit(); self.cal_out.setPlaceholderText("result column name")
        self.btn_calc = QPushButton("Compute")
        r1.addWidget(QLabel("Col A")); r1.addWidget(self.cal_c1, 2)
        r1.addWidget(QLabel("Op")); r1.addWidget(self.cal_op)
        r1.addWidget(QLabel("Col B")); r1.addWidget(self.cal_c2, 2)
        r1.addWidget(QLabel("Output name")); r1.addWidget(self.cal_out)
        r1.addWidget(self.btn_calc); lay.addLayout(r1)
        note = QLabel("รองรับ +, -, *, /, //, % (หารด้วยศูนย์จะให้ค่าเป็นว่าง)"); note.setStyleSheet("color:#6b7280;"); lay.addWidget(note)
        self.btn_calc.clicked.connect(self._do_calc)
        self._top_align(w, lay); self.tabs.addTab(w, "Calculation")

    # =============================
    # Menus
    # =============================
    def _table_menu(self, view: QTableView, pos: QtCore.QPoint):
        m = QtWidgets.QMenu(view)
        act_copy = m.addAction("Copy selected as CSV")
        if m.exec_(view.viewport().mapToGlobal(pos)) == act_copy:
            _copy_selection_as_csv(view)

    # =============================
    # Top bar actions
    # =============================
    def _open(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open file", str(Path.home()),
                                              "Data files (*.csv *.tsv *.txt *.xls *.xlsx);;All files (*.*)")
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
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "output.csv", "CSV (*.csv)")
        if not path:
            return
        with self._busy("Exporting CSV"):
            self.df_out.to_csv(path, index=False, encoding="utf-8-sig")

    def _export_xlsx(self):
        if self.df_out is None or self.df_out.empty:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Excel", "output.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        with self._busy("Exporting Excel"):
            self.df_out.to_excel(path, index=False)

    # =============================
    # Load & Preview
    # =============================
    def _load_file(self, path: Path):
        self._current_path = path
        with self._busy(f"Loading {path.name}"):
            try:
                df = self._read_any(path)
            except Exception as e:
                QMessageBox.warning(self, "Open file", f"เปิดไฟล์ไม่สำเร็จ: {e}")
                return
        self.df_raw = df.copy(); self.df_out = df.copy()
        self._set_preview(self.df_raw, raw=True)
        self._set_preview(self.df_out)
        self._refresh_comboboxes()

    def _read_any(self, path: Path) -> pd.DataFrame:
        p = str(path).lower()
        if p.endswith((".xls", ".xlsx")):
            df = pd.read_excel(str(path))
        else:
            # delimiter & encoding
            delim = "," if not p.endswith(".tsv") else "\t"
            if p.endswith(".txt"):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        head = f.read(2048)
                    if "\t" in head: delim = "\t"
                    elif "|" in head: delim = "|"
                except Exception:
                    pass
            try:
                df = pd.read_csv(str(path), sep=delim, dtype=str, encoding="utf-8")
            except Exception:
                for enc in ("utf-8-sig", "cp874", "tis-620", "latin1"):
                    try:
                        df = pd.read_csv(str(path), sep=delim, dtype=str, encoding=enc)
                        break
                    except Exception:
                        df = None  # type: ignore
                if df is None:
                    raise
        return self._df_to_str(df)

    def _df_to_str(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for c in out.columns:
            out[c] = out[c].astype(str).where(~out[c].isna(), "")
        return out

    def _set_preview(self, df: pd.DataFrame, raw: bool = False):
        show = df if (self.preview_limit == 0 or len(df) <= self.preview_limit) else df.head(self.preview_limit)
        (self.model_raw if raw else self.model_out).set_df(show)

    def _refresh_comboboxes(self):
        cols = list(self.df_out.columns) if (self.df_out is not None and not self.df_out.empty) else []
        for cb in (self.trim_col, self.del_col, self.pad_col, self.cal_c1, self.cal_c2):
            cb.clear(); cb.addItems(cols)
        self.grp_cols_cb.set_items(cols)
        self.sum_cols_cb.set_items(cols)

    def _top_align(self, w: QWidget, lay: QVBoxLayout):
        lay.addStretch(1); w.setLayout(lay)

    @contextlib.contextmanager
    def _busy(self, msg: str):
        b = _Busy(self, msg, self.status)
        with b:
            yield

    # =============================
    # Actions
    # =============================
    def _do_trim(self):
        if self.df_out is None or self.df_out.empty:
            return
        col = self.trim_col.currentText()
        keep = int(self.trim_keep.value())
        side = self.trim_side.currentText()
        if not col or col not in self.df_out.columns:
            return
        with self._busy(f"Trimming '{col}'"):
            df = self.df_out.copy(); s = df[col].astype(str)
            if keep <= 0:
                df[col] = ""
            else:
                df[col] = s.str.slice(0, keep) if side == "Left" else s.str.slice(-keep)
            self.df_out = df; self._set_preview(self.df_out); self._refresh_comboboxes()

    def _do_delete(self):
        if self.df_out is None or self.df_out.empty:
            return
        col = self.del_col.currentText(); mode = self.del_mode.currentText(); q = self.del_q.text().strip()
        if not col or col not in self.df_out.columns or not q:
            return
        with self._busy(f"Deleting rows in '{col}'"):
            df = self.df_out.copy(); s = df[col].astype(str)
            if mode == "contains":
                pattern = q.replace("%", ".*")
                mask = ~s.str.contains(pattern, na=False, regex=True)
            else:
                mask = s != q
            self.df_out = df[mask].copy(); self._set_preview(self.df_out); self._refresh_comboboxes()

    def _do_pad(self):
        if self.df_out is None or self.df_out.empty:
            return
        col = self.pad_col.currentText(); n = int(self.pad_len.value())
        ch = (self.pad_char.text() or " ")[0]; side = self.pad_side.currentText()
        if not col or col not in self.df_out.columns or n <= 0:
            return
        with self._busy(f"Padding '{col}'"):
            df = self.df_out.copy(); s = df[col].astype(str)
            if side == "Left":
                df[col] = s.str.zfill(n) if ch == "0" else s.str.pad(n, side="left", fillchar=ch)
            else:
                df[col] = s.str.pad(n, side="right", fillchar=ch)
            self.df_out = df; self._set_preview(self.df_out); self._refresh_comboboxes()

    def _unique_name(self, base: str, existing: List[str]) -> str:
        """สร้างชื่อคอลัมน์ที่ไม่ชนใน existing"""
        name = base; i = 2
        while name in existing:
            name = f"{base}_{i}"; i += 1
        return name

    def _update_group_sum_visibility(self):
        group_on = self.radio_group.isChecked()
        sum_on = self.radio_sum.isChecked()
        both_on = self.radio_both.isChecked()
        show_group = group_on or both_on
        show_sum = sum_on or both_on
        for w in (self.lbl_group_by, self.grp_cols_cb):
            w.setVisible(show_group)
        for w in (self.lbl_sum_cols, self.sum_cols_cb):
            w.setVisible(show_sum)
        # ล้างฝั่งที่ซ่อน เพื่อกันค่าเก่าปนผล
        if show_group and not show_sum:
            self.sum_cols_cb.clear_checks()
        if show_sum and not show_group:
            self.grp_cols_cb.clear_checks()
        # อัปเดตข้อความบน combo
        self.grp_cols_cb._update_display_text(); self.sum_cols_cb._update_display_text()

    def _do_group_sum(self):
        # เลือกฐานข้อมูลตาม Source
        source_choice = self.cmb_source.currentText()
        base_df = self.df_raw if source_choice == "Raw input" else self.df_out
        if base_df is None or base_df.empty:
            QMessageBox.warning(self, "Group/Sum", "ไม่พบข้อมูลในแหล่งที่เลือก")
            return

        grp = [c for c in self.grp_cols_cb.checked_items() if c]
        sums = [c for c in self.sum_cols_cb.checked_items() if c]
        mode = "Group only" if self.radio_group.isChecked() else ("Sum only" if self.radio_sum.isChecked() else "Group + Sum")

        with self._busy(f"Running {mode} on {source_choice}"):
            df = base_df.copy()

            def _auto_numeric(exclude=None):
                exclude = set(exclude or [])
                out = []
                for c in df.columns:
                    if c in exclude: continue
                    s = pd.to_numeric(df[c], errors="coerce")
                    if len(s) and s.notna().mean() >= 0.5:
                        out.append(c)
                return out

            if mode == "Group only":
                if not grp:
                    QMessageBox.information(self, "Group only", "กรุณาเลือก Group by อย่างน้อย 1 คอลัมน์"); return
                count_name = self._unique_name("count", existing=list(df.columns) + grp)
                g = df.groupby(grp, dropna=False).size().reset_index(name=count_name)
                self.df_out = self._df_to_str(g)

            elif mode == "Sum only":
                if not sums:
                    sums = _auto_numeric()
                    if not sums:
                        QMessageBox.information(self, "Sum only", "ไม่พบคอลัมน์ตัวเลขสำหรับ sum"); return
                g = df[sums].apply(pd.to_numeric, errors="coerce").sum().to_frame().T
                self.df_out = self._df_to_str(g)

            else:  # Group + Sum
                if not grp:
                    QMessageBox.information(self, "Group + Sum", "กรุณาเลือก Group by อย่างน้อย 1 คอลัมน์"); return
                if not sums:
                    sums = _auto_numeric(exclude=grp)
                    if not sums:
                        QMessageBox.information(self, "Group + Sum", "ไม่พบคอลัมน์ตัวเลขสำหรับ sum"); return
                g = (
                    df.assign(**{c: pd.to_numeric(df[c], errors="coerce") for c in sums})
                      .groupby(grp, dropna=False)[sums]
                      .sum()
                      .reset_index()
                )
                self.df_out = self._df_to_str(g)

            # แสดงผลใหม่ใน Output และรีเฟรชตัวเลือกคอลัมน์
            self._set_preview(self.df_out); self._refresh_comboboxes()

    def _do_calc(self):
        if self.df_out is None or self.df_out.empty:
            return
        c1 = self.cal_c1.currentText(); c2 = self.cal_c2.currentText()
        op = self.cal_op.currentText(); outname = (self.cal_out.text().strip() or "result")
        if not (c1 and c2) or c1 not in self.df_out.columns or c2 not in self.df_out.columns:
            return
        with self._busy("Computing"):
            df = self.df_out.copy()
            s1 = pd.to_numeric(df[c1], errors="coerce")
            s2 = pd.to_numeric(df[c2], errors="coerce")
            try:
                if op == "+": res = s1 + s2
                elif op == "-": res = s1 - s2
                elif op == "*": res = s1 * s2
                elif op == "/": res = s1 / s2.replace(0, pd.NA)
                elif op == "//": res = (s1 // s2.replace(0, pd.NA))
                elif op == "%": res = s1 % s2.replace(0, pd.NA)
                else: res = pd.NA
            except Exception:
                res = pd.NA
            # แปลง preview-friendly
            if op in ("/", "//", "%"):
                try:
                    df[outname] = res.astype("Float64")
                except Exception:
                    df[outname] = pd.to_numeric(res, errors="coerce")
            else:
                df[outname] = res
            df[outname] = df[outname].astype(str).where(~df[outname].isna(), "")
            self.df_out = df; self._set_preview(self.df_out); self._refresh_comboboxes()


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = EditDataView(); w.show()
    sys.exit(app.exec_())
