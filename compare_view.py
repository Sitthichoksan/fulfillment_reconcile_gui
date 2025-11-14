#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from contextlib import contextmanager
import time
from typing import List, Optional, Dict, Iterable, Tuple
import pandas as pd
from PyQt5 import QtCore, QtWidgets
from pandas.util import hash_pandas_object

from file_block import FileBlock
from sum_dialog import SumDialog

try:
    from theme import set_table_defaults
except Exception:
    def set_table_defaults(view: QtWidgets.QTableView):
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


# =============================
# Small helpers
# =============================
class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df: Optional[pd.DataFrame] = None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()

    def set_df(self, df: Optional[pd.DataFrame]):
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if self._df is None else len(self._df)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if self._df is None else self._df.shape[1]

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid() or self._df is None:
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            val = self._df.iat[index.row(), index.column()]
            return "" if pd.isna(val) else str(val)
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if self._df is None or role != QtCore.Qt.DisplayRole:
            return None
        if orientation == QtCore.Qt.Horizontal:
            try:
                return str(self._df.columns[section])
            except Exception:
                return ""
        else:
            return section + 1


def build_key_hash(df: pd.DataFrame, keys: List[str]) -> pd.Series:
    ks = [k for k in keys if k]
    if not ks:
        return pd.Series(pd.NA, index=df.index, dtype="UInt64")
    h = None
    for k in ks:
        s = df[k].astype("string[python]").fillna("")
        hv = hash_pandas_object(s, index=False).astype("uint64").values
        h = hv if h is None else (h ^ hv)
    return pd.Series(h, index=df.index, dtype="UInt64")


def safe_numeric(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.replace(",", "", regex=False)
    s = s.str.replace("(", "-", regex=False).str.replace(")", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def hash_to_keyrows(df: pd.DataFrame, keys: List[str], key_hash: pd.Series) -> pd.DataFrame:
    ks = [k for k in keys if k]
    if not ks:
        return pd.DataFrame(columns=["h"])
    tmp = pd.DataFrame({"h": key_hash})
    for k in ks:
        col = df[k]
        def fmt(v):
            if pd.isna(v):
                return pd.NA
            if isinstance(v, float):
                return str(int(v)) if v.is_integer() else str(v)
            return str(v)
        tmp[k] = col.map(fmt)
    tmp = tmp.dropna(subset=["h"]).drop_duplicates(subset=["h"], keep="first")
    tmp["h"] = tmp["h"].astype("uint64")
    return tmp


def df_from_keys_with_keycols(name: str, keys_iter: Iterable[int], keyrows: pd.DataFrame, key_colnames: List[str]) -> pd.DataFrame:
    lst = list(keys_iter)
    if not lst:
        cols = key_colnames + [f"{name}_key"]
        return pd.DataFrame(columns=cols)
    ref = keyrows.set_index("h")
    sel = pd.Index([int(x) for x in lst])
    joined = ref.loc[ref.index.intersection(sel)].copy()
    joined[f"{name}_key"] = joined.index.astype("uint64")
    return joined[key_colnames + [f"{name}_key"]].reset_index(drop=True)


# =============================
# Mapping Dialog (new)
# =============================
class MappingDialog(QtWidgets.QDialog):
    """
    เลือกจับคู่คอลัมน์ A↔B และตั้ง tolerance
    ผลลัพธ์:
      {'pairs': [(a_col, b_col, typ), ...], 'abs_tol': float, 'pct_tol': float}
      typ ∈ {'Numeric','Text'}
    """
    def __init__(self, cols_a: List[str], cols_b: List[str], init_pairs: List[Tuple[str,str,str]] = None,
                 abs_tol: float = 0.0, pct_tol: float = 0.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Column Mapping & Tolerance")
        self.resize(720, 520)

        self._pairs: List[Tuple[str,str,str]] = list(init_pairs or [])
        self._cols_a = cols_a
        self._cols_b = cols_b

        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(16,16,16,16)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # pickers
        self.cmb_a = QtWidgets.QComboBox(); self.cmb_a.addItems(cols_a)
        self.cmb_b = QtWidgets.QComboBox(); self.cmb_b.addItems(cols_b)
        self.cmb_t = QtWidgets.QComboBox(); self.cmb_t.addItems(["Numeric","Text"])
        self.btn_add = QtWidgets.QPushButton("➕ Add")
        self.btn_del = QtWidgets.QPushButton("🗑 Remove selected")

        grid.addWidget(QtWidgets.QLabel("File A column"), 0, 0)
        grid.addWidget(self.cmb_a, 0, 1)
        grid.addWidget(QtWidgets.QLabel("File B column"), 0, 2)
        grid.addWidget(self.cmb_b, 0, 3)
        grid.addWidget(QtWidgets.QLabel("Type"), 0, 4)
        grid.addWidget(self.cmb_t, 0, 5)
        grid.addWidget(self.btn_add, 0, 6)

        # table of pairs
        self.tbl = QtWidgets.QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["A column","B column","Type"])
        self.tbl.horizontalHeader().setStretchLastSection(True)
        grid.addWidget(self.tbl, 1, 0, 1, 7)

        grid.addWidget(self.btn_del, 2, 0, 1, 2)

        # tolerance area
        tolbox = QtWidgets.QGroupBox("Numeric tolerance")
        tl = QtWidgets.QGridLayout(tolbox)
        self.sp_abs = QtWidgets.QDoubleSpinBox(); self.sp_abs.setDecimals(6); self.sp_abs.setRange(0, 1e12); self.sp_abs.setValue(abs_tol)
        self.sp_pct = QtWidgets.QDoubleSpinBox(); self.sp_pct.setDecimals(4); self.sp_pct.setRange(0, 100.0); self.sp_pct.setValue(pct_tol*100.0)
        tl.addWidget(QtWidgets.QLabel("Absolute (≤)"), 0, 0); tl.addWidget(self.sp_abs, 0, 1)
        tl.addWidget(QtWidgets.QLabel("Percent of max(|A|,|B|) (≤ %)"), 0, 2); tl.addWidget(self.sp_pct, 0, 3)
        grid.addWidget(tolbox, 3, 0, 1, 7)

        # buttons
        bb = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        grid.addWidget(bb, 4, 0, 1, 7)

        self.btn_add.clicked.connect(self._on_add)
        self.btn_del.clicked.connect(self._on_del)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

        self._reload_table()

    def _reload_table(self):
        self.tbl.setRowCount(0)
        for a,b,t in self._pairs:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QtWidgets.QTableWidgetItem(a))
            self.tbl.setItem(r, 1, QtWidgets.QTableWidgetItem(b))
            self.tbl.setItem(r, 2, QtWidgets.QTableWidgetItem(t))

    def _on_add(self):
        a = self.cmb_a.currentText().strip()
        b = self.cmb_b.currentText().strip()
        t = self.cmb_t.currentText().strip()
        if not a or not b: return
        pair = (a,b,t)
        if pair not in self._pairs:
            self._pairs.append(pair)
            self._reload_table()

    def _on_del(self):
        rows = sorted(set([idx.row() for idx in self.tbl.selectedIndexes()]), reverse=True)
        for r in rows:
            if 0 <= r < len(self._pairs):
                self._pairs.pop(r)
        self._reload_table()

    def result(self) -> Dict:
        return {
            "pairs": list(self._pairs),
            "abs_tol": float(self.sp_abs.value()),
            "pct_tol": float(self.sp_pct.value())/100.0
        }


# =============================
# Main Window
# =============================
class CompareWindow(QtWidgets.QMainWindow):
    requestHome = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare Files – Reconcile GUI")
        self.resize(1320, 860)

        # data holders
        self.df_a: Optional[pd.DataFrame] = None
        self.df_b: Optional[pd.DataFrame] = None
        self.df_a_agg: Optional[pd.DataFrame] = None
        self.df_b_agg: Optional[pd.DataFrame] = None

        # results
        self._summary_html: str = ""
        self._only_a_df: Optional[pd.DataFrame] = None
        self._only_b_df: Optional[pd.DataFrame] = None
        self._both_df: Optional[pd.DataFrame] = None
        self._dup_a_df: Optional[pd.DataFrame] = None
        self._dup_b_df: Optional[pd.DataFrame] = None
        self._valdiff_df: Optional[pd.DataFrame] = None  # NEW

        # mapping & tolerance (NEW)
        self._map_pairs: List[Tuple[str,str,str]] = []  # (a_col, b_col, 'Numeric'|'Text')
        self._abs_tol: float = 0.0
        self._pct_tol: float = 0.0

        # UI
        self._stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self._stack)
        self._status = self.statusBar()
        self._status.showMessage("Ready – Load A/B and set keys")

        # progress tracking
        self._prog_task: Optional[str] = None
        self._prog_total: int = 0
        self._prog_step: int = 0
        self._prog_t0: float = 0.0

        self._build_page_setup()
        self._build_page_results()
        self._stack.setCurrentWidget(self.page_setup)

    # ------------- busy ctx -------------
    @contextmanager
    def _busy(self, text: str, done: str = "Done ✅"):
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        t0 = time.time()
        self._status.showMessage(f"{text}…")
        QtWidgets.QApplication.processEvents()
        try:
            yield
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
            dt = time.time() - t0
            self._status.showMessage(f"{done} ({dt:.2f}s)")

    # ------------- progress helpers (Thai messages) -------------
    def _start_progress(self, task: str, total_steps: int = 100):
        """Start a simple percent progress in the status bar.

        Shows messages like: "กำลังทำงาน: <task> 12%" and records start time.
        """
        try:
            self._prog_task = task
            self._prog_total = max(1, int(total_steps))
            self._prog_step = 0
            self._prog_t0 = time.time()
            self._status.showMessage(f"กำลังทำงาน: {task} 0%")
            QtWidgets.QApplication.processEvents()
        except Exception:
            # don't let progress helpers break the main flow
            pass

    def _update_progress(self, step_inc: int = 1, note: str = ""):
        """Increment progress by step_inc and update status message.

        note is optional extra text appended to message.
        """
        try:
            if not self._prog_task:
                return
            self._prog_step = min(self._prog_total, self._prog_step + int(step_inc))
            pct = (self._prog_step / self._prog_total) * 100
            note_text = f" • {note}" if note else ""
            self._status.showMessage(f"กำลังทำงาน: {self._prog_task} {pct:.0f}%{note_text}")
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

    def _finish_progress(self, done_text: str = "เสร็จแล้ว"):
        """Finish progress and show elapsed time in status bar."""
        try:
            dt = time.time() - (self._prog_t0 or time.time())
            self._status.showMessage(f"{done_text} ({dt:.2f}s)")
            QtWidgets.QApplication.processEvents()
            # reset
            self._prog_task = None
            self._prog_total = 0
            self._prog_step = 0
            self._prog_t0 = 0.0
        except Exception:
            pass

    # ------------- pages -------------
    def _build_page_setup(self):
        self.page_setup = QtWidgets.QWidget()
        vmain = QtWidgets.QVBoxLayout(self.page_setup)
        vmain.setContentsMargins(16, 16, 16, 16)
        vmain.setSpacing(12)

        # top toolbar
        top = QtWidgets.QHBoxLayout()
        self.btn_home = QtWidgets.QPushButton("← Home")
        self.btn_clear = QtWidgets.QPushButton("🧼 Clear all")
        self.btn_compare = QtWidgets.QPushButton("⚖️  Compare")
        self.btn_sum = QtWidgets.QPushButton("Σ Aggregate…")
        self.btn_reload = QtWidgets.QPushButton("🔄 Reload files")
        self.btn_autokey = QtWidgets.QPushButton("🧠 Auto-detect keys")
        self.btn_mapping = QtWidgets.QPushButton("🔗 Column mapping…")  # NEW

        top.addWidget(self.btn_home)
        top.addSpacing(8)
        top.addWidget(self.btn_clear)
        top.addStretch(1)
        top.addWidget(self.btn_autokey)
        top.addWidget(self.btn_reload)
        top.addSpacing(8)
        top.addWidget(self.btn_mapping)   # NEW
        top.addWidget(self.btn_sum)
        top.addWidget(self.btn_compare)
        vmain.addLayout(top)

        # two file blocks
        hb = QtWidgets.QHBoxLayout()
        hb.setSpacing(12)
        self.block_a = FileBlock(title="File 1 (A)")
        self.block_b = FileBlock(title="File 2 (B)")
        hb.addWidget(self.block_a, 1)
        hb.addWidget(self.block_b, 1)
        vmain.addLayout(hb, 1)

        self._stack.addWidget(self.page_setup)

        # signals
        self.btn_home.clicked.connect(self._go_home)
        self.btn_clear.clicked.connect(self._clear_all)
        self.btn_reload.clicked.connect(self._reload_files)
        self.btn_autokey.clicked.connect(self._auto_detect_keys)
        self.btn_sum.clicked.connect(self._open_sum_dialog)
        self.btn_compare.clicked.connect(self._on_compare_clicked)
        self.btn_mapping.clicked.connect(self._open_mapping_dialog)   # NEW

        self.block_a.dataChanged.connect(lambda: self._status.showMessage("A: updated"))
        self.block_b.dataChanged.connect(lambda: self._status.showMessage("B: updated"))

    def _build_page_results(self):
        self.page_results = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(self.page_results)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        hdr = QtWidgets.QHBoxLayout()
        self.btn_back = QtWidgets.QPushButton("← Back to Setup")
        self.btn_save_report = QtWidgets.QPushButton("📋 Save Summary Report…")
        self.btn_export_cov = QtWidgets.QPushButton("📤 Export coverage…")
        self.btn_export_mm = QtWidgets.QPushButton("📤 Export duplicates…")
        self.btn_export_val = QtWidgets.QPushButton("📤 Export value diff…")  # NEW
        for b in (self.btn_save_report, self.btn_export_cov, self.btn_export_mm, self.btn_export_val):
            b.setEnabled(False)
        hdr.addWidget(self.btn_back)
        hdr.addStretch(1)
        hdr.addWidget(self.btn_save_report)
        hdr.addWidget(self.btn_export_cov)
        hdr.addWidget(self.btn_export_mm)
        hdr.addWidget(self.btn_export_val)
        v.addLayout(hdr)

        # Summary card
        sum_card = QtWidgets.QGroupBox("Summary")
        sum_l = QtWidgets.QVBoxLayout(sum_card)
        sum_l.setContentsMargins(12, 12, 12, 12)
        sum_l.setSpacing(8)
        self.txt_summary = QtWidgets.QTextBrowser()
        self.txt_summary.setOpenExternalLinks(True)
        self.txt_summary.setMinimumHeight(110)
        sum_l.addWidget(self.txt_summary)
        v.addWidget(sum_card)

        # Tabs
        tabs = QtWidgets.QTabWidget()

        # Coverage
        cov = QtWidgets.QWidget()
        cov_l = QtWidgets.QVBoxLayout(cov)
        self.tbl_only_a = QtWidgets.QTableView()
        self.tbl_only_b = QtWidgets.QTableView()
        self.tbl_both = QtWidgets.QTableView()
        for tv in (self.tbl_only_a, self.tbl_only_b, self.tbl_both):
            set_table_defaults(tv)
            tv.setModel(PandasModel(pd.DataFrame()))
        cov_l.addWidget(QtWidgets.QLabel("Only in A (by key)"))
        cov_l.addWidget(self.tbl_only_a, 1)
        cov_l.addWidget(QtWidgets.QLabel("Only in B (by key)"))
        cov_l.addWidget(self.tbl_only_b, 1)
        cov_l.addWidget(QtWidgets.QLabel("In Both (sample keys)"))
        cov_l.addWidget(self.tbl_both, 1)
        tabs.addTab(cov, "Coverage")

        # Duplicate
        dup = QtWidgets.QWidget()
        dup_l = QtWidgets.QVBoxLayout(dup)
        self.tbl_dup_a = QtWidgets.QTableView()
        self.tbl_dup_b = QtWidgets.QTableView()
        for tv in (self.tbl_dup_a, self.tbl_dup_b):
            set_table_defaults(tv)
            tv.setModel(PandasModel(pd.DataFrame()))
        dup_l.addWidget(QtWidgets.QLabel("Duplicate keys – A (key, count)"))
        dup_l.addWidget(self.tbl_dup_a, 1)
        dup_l.addWidget(QtWidgets.QLabel("Duplicate keys – B (key, count)"))
        dup_l.addWidget(self.tbl_dup_b, 1)
        tabs.addTab(dup, "Duplicate Keys")

        # Value Diff (NEW)
        vd = QtWidgets.QWidget()
        vd_l = QtWidgets.QVBoxLayout(vd)
        self.tbl_valdiff = QtWidgets.QTableView()
        set_table_defaults(self.tbl_valdiff)
        self.tbl_valdiff.setModel(PandasModel(pd.DataFrame()))
        vd_l.addWidget(QtWidgets.QLabel("Value mismatches (by mapped columns & tolerance)"))
        vd_l.addWidget(self.tbl_valdiff, 1)
        tabs.addTab(vd, "Value Diff")

        v.addWidget(tabs, 1)

        self._stack.addWidget(self.page_results)

        self.btn_back.clicked.connect(lambda: self._stack.setCurrentWidget(self.page_setup))
        self.btn_save_report.clicked.connect(self._save_summary_report)
        self.btn_export_cov.clicked.connect(self._export_coverage)
        self.btn_export_mm.clicked.connect(self._export_duplicates)
        self.btn_export_val.clicked.connect(self._export_valdiff)  # NEW

    # ------------- routes / actions -------------
    def _go_home(self):
        self.requestHome.emit()
        self.close()  # ✅ ปิดหน้าต่าง Compare เองด้วย เพื่อให้ UX ตรงความคาดหวัง

    def _clear_all(self):
        self.block_a.clear_all()
        self.block_b.clear_all()
        self.df_a = self.df_b = self.df_a_agg = self.df_b_agg = None
        self._summary_html = ""
        self._only_a_df = self._only_b_df = self._both_df = None
        self._dup_a_df = self._dup_b_df = None
        self._valdiff_df = None
        self._map_pairs = []
        self._abs_tol = 0.0
        self._pct_tol = 0.0
        self._status.showMessage("Cleared")

    def _reload_files(self):
        with self._busy("Reloading files"):
            try:
                self.block_a.reload()
                self.block_b.reload()
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Reload error", str(e))

    def _auto_detect_keys(self):
        with self._busy("Auto-detecting keys"):
            df_a = self.block_a.current_df_or_none()
            df_b = self.block_b.current_df_or_none()
            if df_a is None or df_b is None:
                QtWidgets.QMessageBox.information(self, "Auto keys", "โปรดโหลดไฟล์ A/B ให้เรียบร้อยก่อน")
                return
            cols = [c for c in df_a.columns if c in set(df_b.columns)]
            if not cols:
                QtWidgets.QMessageBox.information(self, "Auto keys", "ไม่พบคอลัมน์ร่วมกันระหว่าง A/B")
                return
            keys = cols[:3]
            self.block_a.set_keys(keys)
            self.block_b.set_keys(keys)
        self._status.showMessage(f"Auto keys → {keys}")

    def _open_sum_dialog(self):
        df_a = self.block_a.current_df_or_none()
        df_b = self.block_b.current_df_or_none()
        if df_a is None and df_b is None:
            QtWidgets.QMessageBox.information(self, "Aggregate", "ยังไม่มีข้อมูล A/B")
            return
        cols_a = list(df_a.columns) if df_a is not None else []
        cols_b = list(df_b.columns) if df_b is not None else []
        keys_a = self.block_a.keys()
        keys_b = self.block_b.keys()
        dlg = SumDialog(cols_a, cols_b, keys_a, keys_b, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            opts = dlg.get_options()
            with self._busy("Aggregating"):
                try:
                    self.df_a_agg = self._apply_aggregate(df_a, keys_a, opts['a']) if df_a is not None else None
                    self.df_b_agg = self._apply_aggregate(df_b, keys_b, opts['b']) if df_b is not None else None
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Aggregate error", str(e))

    def _apply_aggregate(self, df: pd.DataFrame, keys: List[str], opt: Dict) -> pd.DataFrame:
        out = df.copy()

        # where
        w_col, w_op, w_val = opt.get('where') or ("", "", "")
        if w_col:
            s = out[w_col]
            left_num = safe_numeric(s)
            right_num = pd.to_numeric(pd.Series([w_val]), errors="coerce").iloc[0]
            both_num = left_num.notna().any() and pd.notna(right_num)
            if both_num and w_op in ["=", "!=", ">", ">=", "<", "<="]:
                if   w_op == "=":  out = out[left_num == right_num]
                elif w_op == "!=": out = out[left_num != right_num]
                elif w_op == ">":  out = out[left_num >  right_num]
                elif w_op == ">=": out = out[left_num >= right_num]
                elif w_op == "<":  out = out[left_num <  right_num]
                elif w_op == "<=": out = out[left_num <= right_num]
            else:
                ls = s.astype(str); rv = str(w_val)
                if   w_op == "=":  out = out[ls == rv]
                elif w_op == "!=": out = out[ls != rv]
                elif w_op == ">":  out = out[ls >  rv]
                elif w_op == ">=": out = out[ls >= rv]
                elif w_op == "<":  out = out[ls <  rv]
                elif w_op == "<=": out = out[ls <= rv]

        # sum
        gb = opt.get('gb', 'None')
        sum_cols = opt.get('sum', []) or []
        for c in sum_cols:
            out[c] = safe_numeric(out[c])

        if gb in ["Key1", "Key2", "Key3"]:
            idx = {"Key1": 0, "Key2": 1, "Key3": 2}[gb]
            gkeys = [k for k in keys[:idx+1] if k]
            if gkeys and sum_cols:
                out = out.groupby(gkeys, dropna=False)[sum_cols].sum().reset_index()
            elif gkeys:
                out = out.groupby(gkeys, dropna=False).size().reset_index(name="count")
        elif sum_cols:
            out = pd.DataFrame(out[sum_cols].sum()).T
        return out

    def _open_mapping_dialog(self):
        df_a = self.df_a_agg if self.df_a_agg is not None else self.block_a.current_df_or_none()
        df_b = self.df_b_agg if self.df_b_agg is not None else self.block_b.current_df_or_none()
        if df_a is None or df_b is None:
            QtWidgets.QMessageBox.information(self, "Mapping", "โปรดโหลดไฟล์ A/B (และ aggregate ถ้าต้องการ) ก่อน")
            return
        cols_a = list(df_a.columns)
        cols_b = list(df_b.columns)
        dlg = MappingDialog(cols_a, cols_b, init_pairs=self._map_pairs,
                            abs_tol=self._abs_tol, pct_tol=self._pct_tol, parent=self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            res = dlg.result()
            self._map_pairs = res["pairs"]
            self._abs_tol = float(res["abs_tol"])
            self._pct_tol = float(res["pct_tol"])
            self._status.showMessage(f"Mapping updated ({len(self._map_pairs)} pairs, abs_tol={self._abs_tol}, pct_tol={self._pct_tol*100:.2f}%)")

    # ------------- core compare -------------
    def _on_compare_clicked(self):
        df_a = self.df_a_agg if self.df_a_agg is not None else self.block_a.current_df_or_none()
        df_b = self.df_b_agg if self.df_b_agg is not None else self.block_b.current_df_or_none()
        if df_a is None or df_b is None:
            QtWidgets.QMessageBox.information(self, "Compare", "โปรดโหลดไฟล์ทั้ง A และ B")
            return

        keys_a = [k for k in self.block_a.keys() if k]
        keys_b = [k for k in self.block_b.keys() if k]
        if not keys_a or not keys_b or len(keys_a) != len(keys_b):
            QtWidgets.QMessageBox.information(self, "Keys", "โปรดตั้งคีย์ให้ครบ (จำนวนคีย์สองฝั่งต้องเท่ากัน)")
            return

        with self._busy("เปรียบเทียบข้อมูล (ประหยัดหน่วยความจำ)"):
            # start progress: chunked hashing, set ops, build tables, optional valdiff per mapping
            chunk_size = 50000
            num_chunks_a = (len(df_a) + chunk_size - 1) // chunk_size
            num_chunks_b = (len(df_b) + chunk_size - 1) // chunk_size
            total_steps = 4 + num_chunks_a + num_chunks_b + (len(self._map_pairs) if self._map_pairs else 0)
            self._start_progress("เปรียบเทียบ (Chunked)", total_steps=total_steps)
            
            # --- coverage / duplicates (chunked hashing) ---
            # Hash in chunks to avoid memory spike on large files
            a_key_parts = []
            for chunk_idx in range(0, len(df_a), chunk_size):
                chunk = df_a.iloc[chunk_idx:chunk_idx+chunk_size]
                a_key_parts.append(build_key_hash(chunk, keys_a))
                self._update_progress(note=f"แฮช A chunk {(chunk_idx // chunk_size) + 1}/{num_chunks_a}")
                QtWidgets.QApplication.processEvents()
            a_key = pd.concat(a_key_parts, ignore_index=False)
            
            b_key_parts = []
            for chunk_idx in range(0, len(df_b), chunk_size):
                chunk = df_b.iloc[chunk_idx:chunk_idx+chunk_size]
                b_key_parts.append(build_key_hash(chunk, keys_b))
                self._update_progress(note=f"แฮช B chunk {(chunk_idx // chunk_size) + 1}/{num_chunks_b}")
                QtWidgets.QApplication.processEvents()
            b_key = pd.concat(b_key_parts, ignore_index=False)

            def dup_df(s: pd.Series, label: str) -> pd.DataFrame:
                vc = s.value_counts(dropna=False)
                vc = vc[vc > 1]
                if vc.empty:
                    return pd.DataFrame(columns=["file", "key", "count"])
                out = vc.rename("count").reset_index().rename(columns={"index": "key"})
                out.insert(0, "file", label)
                out["key"] = out["key"].astype("UInt64")
                return out

            self._dup_a_df = dup_df(a_key, "ไฟล์ 1")
            self._dup_b_df = dup_df(b_key, "ไฟล์ 2")
            self._update_progress(note="คำนวณคีย์ซ้ำแล้ว")

            try:
                a_unique = a_key[~a_key.duplicated(dropna=False)].dropna().astype("uint64")
                b_unique = b_key[~b_key.duplicated(dropna=False)].dropna().astype("uint64")
            except TypeError:
                a_unique = a_key[~a_key.duplicated()].dropna().astype("uint64")
                b_unique = b_key[~b_key.duplicated()].dropna().astype("uint64")

            a_set = set(a_unique.values.tolist())
            b_set = set(b_unique.values.tolist())
            only_a = a_set - b_set
            only_b = b_set - a_set
            both = a_set & b_set

            SAMPLE = 5000
            both_sample = list(both)[:SAMPLE]

            keyrows_a = hash_to_keyrows(df_a, keys_a, a_key)
            keyrows_b = hash_to_keyrows(df_b, keys_b, b_key)
            self._only_a_df = df_from_keys_with_keycols("onlyA", only_a, keyrows_a, [k for k in keys_a if k])
            self._only_b_df = df_from_keys_with_keycols("onlyB", only_b, keyrows_b, [k for k in keys_b if k])

            kr_a = keyrows_a.set_index("h")
            kr_b = keyrows_b.set_index("h")
            keyrows_both = pd.concat([kr_a, kr_b.loc[lambda d: ~d.index.isin(kr_a.index)]], axis=0).reset_index()
            self._both_df = df_from_keys_with_keycols("both", both_sample, keyrows_both, [k for k in keys_a if k] or [k for k in keys_b if k])

            # update progress after building basic tables
            self._update_progress(step_inc=1, note="สร้างตารางครอบคลุมแล้ว")

            inter = len(both)
            total_a = inter + len(only_a)
            total_b = inter + len(only_b)
            union = len(a_set | b_set)
            jacc = (inter / union) if union else 0.0
            
            # Determine status
            if len(only_a) == 0 and len(only_b) == 0:
                status = "✅ ตรงกันทั้งหมด (MATCHED)"
                color = "#10b981"
            elif inter > 0:
                status = "⚠️ ตรงกันบางส่วน (PARTIAL MATCH)"
                color = "#f59e0b"
            else:
                status = "❌ ไม่ตรงกัน (NO MATCH)"
                color = "#ef4444"
            
            key_list_a = ", ".join(keys_a) or "ไม่มี"
            key_list_b = ", ".join(keys_b) or "ไม่มี"

            html = f"""
              <div style='font-family:Segoe UI,Roboto,Arial;line-height:1.6;'>
                <div style='padding:12px 16px;border-radius:10px;background:{color}20;border:2px solid {color};margin-bottom:12px;'>
                  <div style='font-size:18px;font-weight:700;color:{color};'>{status}</div>
                  <div style='margin-top:4px;color:#555;font-size:13px;'>หลังจากใช้ตัวกรอง และการรวมข้อมูล (ถ้ามี)</div>
                </div>
                
                <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px;'>
                  <div style='padding:12px;border:1px solid #ddd;border-radius:8px;background:#f9fafb;'>
                    <div style='font-size:12px;color:#6b7280;font-weight:600;'>ไฟล์ 1 ตรงกับไฟล์ 2</div>
                    <div style='font-size:28px;font-weight:700;color:{color};margin:8px 0;'>{(inter/total_a*100 if total_a else 0):.1f}%</div>
                    <div style='font-size:11px;color:#666;'>คีย์เฉพาะ = {total_a:,} แถว</div>
                  </div>
                  <div style='padding:12px;border:1px solid #ddd;border-radius:8px;background:#f9fafb;'>
                    <div style='font-size:12px;color:#6b7280;font-weight:600;'>ไฟล์ 2 ตรงกับไฟล์ 1</div>
                    <div style='font-size:28px;font-weight:700;color:{color};margin:8px 0;'>{(inter/total_b*100 if total_b else 0):.1f}%</div>
                    <div style='font-size:11px;color:#666;'>คีย์เฉพาะ = {total_b:,} แถว</div>
                  </div>
                  <div style='padding:12px;border:1px solid #ddd;border-radius:8px;background:#f9fafb;'>
                    <div style='font-size:12px;color:#6b7280;font-weight:600;'>ความคล้ายคลึง (Jaccard)</div>
                    <div style='font-size:28px;font-weight:700;color:{color};margin:8px 0;'>{jacc*100:.1f}%</div>
                    <div style='font-size:11px;color:#666;'>ตรงกัน {inter:,} / รวม {union:,}</div>
                  </div>
                </div>
                
                <div style='margin:12px 0;padding:10px;background:#f0f4f8;border-radius:6px;font-size:12px;color:#333;'>
                  <b>คีย์ที่ใช้:</b><br/>
                  📄 ไฟล์ 1: <code style='background:#fff;padding:2px 6px;border-radius:3px;'>{key_list_a}</code><br/>
                  📄 ไฟล์ 2: <code style='background:#fff;padding:2px 6px;border-radius:3px;'>{key_list_b}</code>
                </div>
                
                <div style='margin-top:8px;padding:8px;border-left:3px solid #2563eb;background:#eff6ff;font-size:11px;color:#555;'>
                  💡 ตัวอย่าง "ตรงกัน" จำกัดที่ {SAMPLE:,} คีย์เพื่อให้เร็ว | ใช้ "ส่งออก" เพื่อดูผลเต็ม
                </div>
              </div>
            """
            self._summary_html = html

            # --- value difference (NEW) ---
            self._valdiff_df = None
            if self._map_pairs:
                # reserve remaining steps to value-diff comparisons
                self._update_progress(step_inc=1, note="เริ่มเปรียบเทียบค่า")
                self._valdiff_df = self._compute_value_diff(df_a, df_b, keys_a, keys_b, both)

            # finish progress for compare
            self._finish_progress("เปรียบเทียบเสร็จแล้ว ✅")

        # push to UI
        self.txt_summary.setHtml(self._summary_html)
        self._set_table(self.tbl_only_a, self._only_a_df)
        self._set_table(self.tbl_only_b, self._only_b_df)
        self._set_table(self.tbl_both, self._both_df)
        self._set_table(self.tbl_dup_a, self._dup_a_df)
        self._set_table(self.tbl_dup_b, self._dup_b_df)
        self._set_table(self.tbl_valdiff, self._valdiff_df)

        self.btn_save_report.setEnabled(True)
        self.btn_export_cov.setEnabled(True)
        self.btn_export_mm.setEnabled(True)
        self.btn_export_val.setEnabled(self._valdiff_df is not None and len(self._valdiff_df) > 0)

        self._stack.setCurrentWidget(self.page_results)
        more = f" ค่าไม่ตรง:{len(self._valdiff_df):,}" if isinstance(self._valdiff_df, pd.DataFrame) and len(self._valdiff_df) > 0 else ""
        self._status.showMessage(f"เปรียบเทียบเสร็จ ✅ – เฉพาะไฟล์1:{len(self._only_a_df):,} เฉพาะไฟล์2:{len(self._only_b_df):,} ตรงกัน(ตัวอย่าง):{len(self._both_df):,}{more}")

    def _compute_value_diff(self, df_a: pd.DataFrame, df_b: pd.DataFrame,
                            keys_a: List[str], keys_b: List[str], both_keys: Iterable[int]) -> pd.DataFrame:
        """
        รวม A/B ด้วยคีย์ (คีย์คนละชื่อได้) แล้วเทียบคู่ mapping ที่กำหนด
        คืนเฉพาะแถวที่ 'ไม่ผ่าน' เกณฑ์ tolerance (สำหรับ Numeric) หรือไม่เท่ากัน (Text)
        """
        # เตรียมคีย์: ทำสำเนาพร้อม rename ให้ชื่อคีย์ B ตรงกับฝั่ง A เพื่อ join ง่าย
        b_ren = df_b.copy()
        ren_map = {}
        for a,b in zip(keys_a, keys_b):
            if a != b:
                ren_map[b] = a
        if ren_map:
            b_ren = b_ren.rename(columns=ren_map)

        # join แบบ inner เฉพาะคีย์ที่ intersect (performance)
        # เพื่อเลี่ยง exploding บนชุดใหญ่มาก ให้ set index แล้วเลือกเฉพาะ h in both_keys ก็ได้
        # ตรงนี้เลือกใช้ merge ปกติ (คีย์หลายคอลัมน์)
        on_keys = [k for k in keys_a if k]
        merged = pd.merge(df_a, b_ren, how="inner", on=on_keys, suffixes=("_A","_B"))

        # ถ้า both_keys มีให้จำกัดตามจริง (กันกรณีมี key duplicate แล้วเกิน)
        # สร้าง hash ตามฝั่ง A เพื่อตรวจว่าอยู่ใน both_keys เท่านั้น
        if on_keys:
            hk = build_key_hash(merged, on_keys)
            merged = merged.loc[hk.astype("uint64").isin(list(both_keys))].copy()

        rows = []
        # progress: update per mapping pair when available
        total_maps = len(self._map_pairs) if self._map_pairs else 0
        map_idx = 0
        # ฟังก์ชันช่วยเช็ค numeric tolerance
        def pass_numeric(a, b) -> Tuple[bool, float]:
            a = pd.to_numeric(pd.Series([a]), errors="coerce").iloc[0]
            b = pd.to_numeric(pd.Series([b]), errors="coerce").iloc[0]
            if pd.isna(a) and pd.isna(b):
                return True, 0.0
            if pd.isna(a) or pd.isna(b):
                return False, float('nan')
            diff = float(a) - float(b)
            if abs(diff) <= self._abs_tol:
                return True, diff
            if self._pct_tol > 0:
                mx = max(abs(float(a)), abs(float(b)))
                if mx == 0:
                    # ทั้งคู่เป็นศูนย์แล้วไม่ผ่าน abs_tol → ถือว่าเท่ากัน
                    return True, diff
                if abs(diff) <= self._pct_tol * mx:
                    return True, diff
            return False, diff

        for a_col, b_col, typ in self._map_pairs:
            a_name = a_col if a_col in merged.columns else f"{a_col}_A"
            b_name = b_col
            # b อาจถูก rename ให้ชื่อเหมือนคีย์ A ไปแล้ว แต่คอลัมน์ mapping ไม่ได้ยุ่ง ให้ดึงจากฝั่ง B
            # ถ้าโดนชนกับ A ให้พึ่ง suffix "_B"
            if b_name in on_keys and b_name in merged.columns and f"{b_name}_B" in merged.columns:
                b_name = f"{b_name}_B"
            elif b_name in merged.columns and f"{b_name}_B" in merged.columns:
                # ถ้ามีทั้งสองเวอร์ชัน ให้เลือก _B
                b_name = f"{b_name}_B"

            if a_name not in merged.columns or b_name not in merged.columns:
                # ข้ามคู่ที่หาไม่เจอ
                continue

            sub = merged[on_keys + [a_name, b_name]].copy()
            if typ == "Numeric":
                pa, pb = a_name, b_name
                ok, diff = [], []
                # vectorize แบบง่าย
                va = safe_numeric(sub[pa])
                vb = safe_numeric(sub[pb])
                mx = va.abs().combine(vb.abs(), max)
                diffv = (va - vb)
                cond_abs = diffv.abs() <= self._abs_tol
                cond_pct = pd.Series([False]*len(sub))
                if self._pct_tol > 0:
                    # เลี่ยง divide-by-zero: เมื่อ mx==0 ให้ถือว่า True (0 เท่ากับ 0)
                    ok_zero = mx == 0
                    cond_pct = diffv.abs() <= (self._pct_tol * mx)
                    cond_pct = cond_pct | ok_zero
                okv = cond_abs | cond_pct
                mism = sub.loc[~okv].copy()
                if not mism.empty:
                    mism["mapped_column"] = f"{a_col} ↔ {b_col}"
                    mism["A_value"] = sub.loc[mism.index, a_name].values
                    mism["B_value"] = sub.loc[mism.index, b_name].values
                    mism["diff"] = diffv.loc[mism.index].values
                    mism["rule"] = mism.apply(lambda r: f"abs≤{self._abs_tol} or pct≤{self._pct_tol*100:.2f}%", axis=1)
                    rows.append(mism[on_keys + ["mapped_column","A_value","B_value","diff","rule"]])
            # progress increment for this mapping
            try:
                map_idx += 1
                # note like "colA↔colB"
                self._update_progress(step_inc=1, note=f"{a_col}↔{b_col}")
            except Exception:
                pass
            else:
                # Text compare: เท่ากันแบบตรงตัว (trim)
                sa = sub[a_name].astype(str).str.strip()
                sb = sub[b_name].astype(str).str.strip()
                mism = sub.loc[sa != sb].copy()
                if not mism.empty:
                    mism["mapped_column"] = f"{a_col} ↔ {b_col}"
                    mism["A_value"] = sa.loc[mism.index].values
                    mism["B_value"] = sb.loc[mism.index].values
                    mism["diff"] = ""
                    mism["rule"] = "text_equal"
                    rows.append(mism[on_keys + ["mapped_column","A_value","B_value","diff","rule"]])

            # progress increment for this mapping (after numeric/text compare)
            try:
                map_idx += 1
                self._update_progress(step_inc=1, note=f"{a_col}↔{b_col}")
            except Exception:
                pass

        if not rows:
            # if there was no mismatch, still update progress finish for maps
            try:
                if total_maps and getattr(self, '_prog_task', None):
                    # ensure progress gets to the end of the reserved map steps
                    remaining = max(0, total_maps - map_idx)
                    if remaining:
                        self._update_progress(step_inc=remaining)
            except Exception:
                pass
            return pd.DataFrame(columns=on_keys + ["mapped_column","A_value","B_value","diff","rule"])
        out = pd.concat(rows, ignore_index=True)
        return out

    # ------------- UI helpers -------------
    def _set_table(self, tv: QtWidgets.QTableView, df: Optional[pd.DataFrame]):
        model = tv.model()
        if isinstance(model, PandasModel):
            model.set_df(df)
        else:
            m = PandasModel(df)
            tv.setModel(m)
            set_table_defaults(tv)
        if df is not None:
            for col in range(tv.model().columnCount()):
                tv.setColumnHidden(col, False)
        tv.resizeColumnsToContents()

    # ------------- save summary report (HTML for Lead/PO) -------------
    def _save_summary_report(self):
        """Save a professional HTML report for Lead/PO with all comparison details"""
        import datetime
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "บันทึก Summary Report", "comparison_report.html",
                                                        "HTML (*.html)")
        if not path:
            return
        try:
            with self._busy("บันทึก Summary Report"):
                self._start_progress("บันทึก Summary Report", total_steps=1)
                
                # Generate HTML report
                html = self._generate_summary_report_html()
                
                # Write to file
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(html)
                
                self._update_progress(step_inc=1, note="บันทึกแล้ว")
                self._finish_progress("บันทึกรายงาน ✅")
            
            QtWidgets.QMessageBox.information(self, "บันทึก", f"✅ บันทึก Summary Report สำเร็จที่:\n{path}\n\nสามารถเปิดด้วย Browser เพื่อดูรายงาน")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถบันทึกรายงานได้: {e}")

    def _generate_summary_report_html(self) -> str:
        """Generate professional HTML report"""
        import datetime
        from pathlib import Path
        
        now = datetime.datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # Get file info
        file_a_path = self.block_a.path_edit.text().strip()
        file_b_path = self.block_b.path_edit.text().strip()
        file_a_name = Path(file_a_path).name if file_a_path else "N/A"
        file_b_name = Path(file_b_path).name if file_b_path else "N/A"
        keys_a = self.block_a.keys()
        keys_b = self.block_b.keys()
        
        # Counts
        only_a_count = len(self._only_a_df) if isinstance(self._only_a_df, pd.DataFrame) else 0
        only_b_count = len(self._only_b_df) if isinstance(self._only_b_df, pd.DataFrame) else 0
        both_count = len(self._both_df) if isinstance(self._both_df, pd.DataFrame) else 0
        dup_a_count = len(self._dup_a_df) if isinstance(self._dup_a_df, pd.DataFrame) else 0
        dup_b_count = len(self._dup_b_df) if isinstance(self._dup_b_df, pd.DataFrame) else 0
        valdiff_count = len(self._valdiff_df) if isinstance(self._valdiff_df, pd.DataFrame) else 0
        
        total_keys_a = len(self.df_a) if self.df_a is not None else 0
        total_keys_b = len(self.df_b) if self.df_b is not None else 0
        
        # Calculate coverage %
        cov_a = (both_count / total_keys_a * 100) if total_keys_a > 0 else 0
        cov_b = (both_count / total_keys_b * 100) if total_keys_b > 0 else 0
        
        # Status
        if only_a_count == 0 and only_b_count == 0 and valdiff_count == 0:
            status = "✅ ตรงกันทั้งหมด (FULLY MATCHED)"
            status_color = "#22c55e"
        elif valdiff_count == 0:
            status = "⚠️ ตรงกัน (ไม่มี duplicate/coverage issue ในหลัก key)"
            status_color = "#eab308"
        else:
            status = "⚠️ ตรงกันบางส่วน (มี value mismatch)"
            status_color = "#f97316"
        
        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>เปรียบเทียบข้อมูล – Summary Report</title>
    <style>
        * {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        body {{
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            border-bottom: 3px solid #0066cc;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            color: #0066cc;
            font-size: 28px;
        }}
        .header .timestamp {{
            color: #666;
            margin-top: 10px;
            font-size: 14px;
        }}
        .status-card {{
            background: {status_color};
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            text-align: center;
            font-size: 18px;
            font-weight: bold;
        }}
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: #f9fafb;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 20px;
        }}
        .card h2 {{
            margin-top: 0;
            color: #1f2937;
            font-size: 16px;
            border-bottom: 2px solid #0066cc;
            padding-bottom: 10px;
        }}
        .metric {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e5e7eb;
        }}
        .metric:last-child {{
            border-bottom: none;
        }}
        .metric-label {{
            color: #666;
            font-weight: 500;
        }}
        .metric-value {{
            color: #0066cc;
            font-weight: bold;
            font-size: 14px;
        }}
        .metric-percent {{
            color: #059669;
            font-weight: bold;
        }}
        .section {{
            margin-top: 30px;
            border-top: 2px solid #e5e7eb;
            padding-top: 20px;
        }}
        .section h3 {{
            color: #1f2937;
            margin-top: 0;
            border-bottom: 2px solid #0066cc;
            padding-bottom: 10px;
        }}
        .detail {{
            background: #f0f9ff;
            padding: 12px;
            border-left: 4px solid #0066cc;
            margin: 10px 0;
            border-radius: 4px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 13px;
        }}
        th {{
            background: #0066cc;
            color: white;
            padding: 10px;
            text-align: left;
            font-weight: bold;
        }}
        td {{
            padding: 8px 10px;
            border-bottom: 1px solid #e5e7eb;
        }}
        tr:nth-child(even) {{
            background: #f9fafb;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #e5e7eb;
            color: #666;
            font-size: 12px;
            text-align: center;
        }}
        .signature {{
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 30px;
            margin-top: 30px;
            text-align: center;
        }}
        .sig-line {{
            height: 1px;
            background: #000;
            margin: 5px 0;
        }}
        .warning {{
            background: #fff7ed;
            border-left: 4px solid #ea580c;
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
        }}
        .success {{
            background: #f0fdf4;
            border-left: 4px solid #16a34a;
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reconciliation Comparison Report</h1>
            <div class="timestamp">{timestamp}</div>
        </div>
        
        <div class="status-card">{status}</div>
        
        <div class="grid">
            <div class="card">
                <h2>📄 File 1 (A)</h2>
                <div class="metric">
                    <span class="metric-label">ชื่อไฟล์:</span>
                    <span>{file_a_name}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">จำนวนแถว:</span>
                    <span class="metric-value">{total_keys_a:,}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">ตรงกัน:</span>
                    <span class="metric-value">{both_count:,} <span class="metric-percent">({cov_a:.1f}%)</span></span>
                </div>
                <div class="metric">
                    <span class="metric-label">เฉพาะไฟล์นี้:</span>
                    <span class="metric-value">{only_a_count:,}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">คีย์ซ้ำ:</span>
                    <span class="metric-value">{dup_a_count:,}</span>
                </div>
                <div class="detail">
                    <strong>คีย์:</strong> {', '.join(keys_a) if keys_a else 'N/A'}
                </div>
            </div>
            
            <div class="card">
                <h2>📄 File 2 (B)</h2>
                <div class="metric">
                    <span class="metric-label">ชื่อไฟล์:</span>
                    <span>{file_b_name}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">จำนวนแถว:</span>
                    <span class="metric-value">{total_keys_b:,}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">ตรงกัน:</span>
                    <span class="metric-value">{both_count:,} <span class="metric-percent">({cov_b:.1f}%)</span></span>
                </div>
                <div class="metric">
                    <span class="metric-label">เฉพาะไฟล์นี้:</span>
                    <span class="metric-value">{only_b_count:,}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">คีย์ซ้ำ:</span>
                    <span class="metric-value">{dup_b_count:,}</span>
                </div>
                <div class="detail">
                    <strong>คีย์:</strong> {', '.join(keys_b) if keys_b else 'N/A'}
                </div>
            </div>
        </div>
        
        <div class="section">
            <h3>📈 สรุปผลการเปรียบเทียบ</h3>
            <table>
                <tr>
                    <th>หมวดหมู่</th>
                    <th>จำนวน</th>
                    <th>หมายเหตุ</th>
                </tr>
                <tr>
                    <td>✅ ตรงกัน (ทั้งสองไฟล์)</td>
                    <td style="color: #16a34a; font-weight: bold;">{both_count:,}</td>
                    <td>Data integrity OK</td>
                </tr>
                <tr>
                    <td>⚠️ เฉพาะไฟล์ 1 เท่านั้น</td>
                    <td style="color: #ea580c; font-weight: bold;">{only_a_count:,}</td>
                    <td>Missing in File B</td>
                </tr>
                <tr>
                    <td>⚠️ เฉพาะไฟล์ 2 เท่านั้น</td>
                    <td style="color: #ea580c; font-weight: bold;">{only_b_count:,}</td>
                    <td>Missing in File A</td>
                </tr>
                <tr>
                    <td>❌ ค่าไม่ตรงกัน</td>
                    <td style="color: #dc2626; font-weight: bold;">{valdiff_count:,}</td>
                    <td>Value mismatch in mapped columns</td>
                </tr>
                <tr>
                    <td>🔄 คีย์ซ้ำ (A)</td>
                    <td style="color: #0066cc; font-weight: bold;">{dup_a_count:,}</td>
                    <td>Duplicate keys in File A</td>
                </tr>
                <tr>
                    <td>🔄 คีย์ซ้ำ (B)</td>
                    <td style="color: #0066cc; font-weight: bold;">{dup_b_count:,}</td>
                    <td>Duplicate keys in File B</td>
                </tr>
            </table>
        </div>
        
        <div class="section">
            <h3>✅ ข้อเสนอแนะ</h3>
"""
        
        # Add recommendations
        if only_a_count > 0:
            html += f'<div class="warning">🔍 มีข้อมูลจำนวน {only_a_count:,} แถวใน File 1 ที่ไม่ปรากฏใน File 2 ควรตรวจสอบว่าเป็นข้อมูลใหม่หรือข้อมูลเดิม</div>'
        
        if only_b_count > 0:
            html += f'<div class="warning">🔍 มีข้อมูลจำนวน {only_b_count:,} แถวใน File 2 ที่ไม่ปรากฏใน File 1 ควรตรวจสอบว่าเป็นข้อมูลใหม่หรือข้อมูลเดิม</div>'
        
        if valdiff_count > 0:
            html += f'<div class="warning">❌ พบค่าไม่ตรงกัน {valdiff_count:,} แถว ในส่วนของ mapping columns - ต้องตรวจสอบและแก้ไขต่อ</div>'
        
        if dup_a_count > 0:
            html += f'<div class="warning">⚠️ File 1 มีคีย์ที่ซ้ำกัน {dup_a_count:,} ชุด - ควรทำความเข้าใจเหตุผล</div>'
        
        if dup_b_count > 0:
            html += f'<div class="warning">⚠️ File 2 มีคีย์ที่ซ้ำกัน {dup_b_count:,} ชุด - ควรทำความเข้าใจเหตุผล</div>'
        
        if only_a_count == 0 and only_b_count == 0 and valdiff_count == 0 and dup_a_count == 0 and dup_b_count == 0:
            html += '<div class="success">🎉 ยอดเยี่ยม! ข้อมูลตรงกันทั้งหมด ไม่มีปัญหา</div>'
        
        html += """
        </div>
        
        <div class="footer">
            <p>📋 Report generated by Fulfillment Reconcile GUI</p>
            <p>💡 สำหรับคำถามหรือปัญหา กรุณาติดต่อ Data Team</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    # ------------- exporters -------------
    def _export_coverage(self):
        if self._only_a_df is None and self._only_b_df is None and self._both_df is None:
            QtWidgets.QMessageBox.information(self, "ส่งออก", "ยังไม่มีผลการเปรียบเทียบ")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "บันทึกการครอบคลุม", "coverage.xlsx",
                                                        "Excel (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        try:
            with self._busy("ส่งออกการครอบคลุม"):
                # progress: simple two-step (prepare -> write)
                self._start_progress("ส่งออกการครอบคลุม", total_steps=2)
                if str(path).lower().endswith(".csv"):
                    parts = []
                    if self._only_a_df is not None: parts.append(self._only_a_df.assign(section="เฉพาะไฟล์1"))
                    if self._only_b_df is not None: parts.append(self._only_b_df.assign(section="เฉพาะไฟล์2"))
                    if self._both_df is not None: parts.append(self._both_df.assign(section="ตรงกัน(ตัวอย่าง)"))
                    pd.concat(parts, ignore_index=True).to_csv(path, index=False, encoding="utf-8")
                else:
                    with pd.ExcelWriter(path) as xw:
                        if self._only_a_df is not None: self._only_a_df.to_excel(xw, index=False, sheet_name="เฉพาะไฟล์1")
                        if self._only_b_df is not None: self._only_b_df.to_excel(xw, index=False, sheet_name="เฉพาะไฟล์2")
                        if self._both_df is not None: self._both_df.to_excel(xw, index=False, sheet_name="ตรงกัน_ตัวอย่าง")
                # mark write step
                self._update_progress(step_inc=1, note="บันทึกไฟล์แล้ว")
                self._finish_progress("ส่งออกเสร็จแล้ว ✅")
            QtWidgets.QMessageBox.information(self, "ส่งออก", f"✅ บันทึกสำเร็จที่:\n{path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถส่งออกได้: {e}")

    def _export_duplicates(self):
        if self._dup_a_df is None and self._dup_b_df is None:
            QtWidgets.QMessageBox.information(self, "ส่งออก", "ไม่มีคีย์ที่ซ้ำกัน")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "บันทึกคีย์ที่ซ้ำ", "duplicates.xlsx",
                                                        "Excel (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        try:
            with self._busy("ส่งออกคีย์ที่ซ้ำ"):
                self._start_progress("ส่งออกคีย์ที่ซ้ำ", total_steps=2)
                if str(path).lower().endswith(".csv"):
                    parts = []
                    if self._dup_a_df is not None: parts.append(self._dup_a_df.assign(section="ไฟล์1"))
                    if self._dup_b_df is not None: parts.append(self._dup_b_df.assign(section="ไฟล์2"))
                    pd.concat(parts, ignore_index=True).to_csv(path, index=False, encoding="utf-8")
                else:
                    with pd.ExcelWriter(path) as xw:
                        if self._dup_a_df is not None: self._dup_a_df.to_excel(xw, index=False, sheet_name="ไฟล์1_ซ้ำ")
                        if self._dup_b_df is not None: self._dup_b_df.to_excel(xw, index=False, sheet_name="ไฟล์2_ซ้ำ")
                self._update_progress(step_inc=1, note="บันทึกไฟล์แล้ว")
                self._finish_progress("ส่งออกเสร็จแล้ว ✅")
            QtWidgets.QMessageBox.information(self, "ส่งออก", f"✅ บันทึกสำเร็จที่:\n{path}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถส่งออกได้: {e}")

    def _export_valdiff(self):
        if self._valdiff_df is None or len(self._valdiff_df) == 0:
            QtWidgets.QMessageBox.information(self, "ส่งออก", "ไม่มีค่าที่ไม่ตรงกัน")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "บันทึกค่าที่ไม่ตรงกัน", "value_diff.xlsx",
                                                        "Excel (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        try:
            with self._busy("ส่งออกค่าที่ไม่ตรงกัน"):
                self._start_progress("ส่งออกค่าไม่ตรง", total_steps=2)
                if str(path).lower().endswith(".csv"):
                    self._valdiff_df.to_csv(path, index=False, encoding="utf-8")
                else:
                    with pd.ExcelWriter(path) as xw:
                        self._valdiff_df.to_excel(xw, index=False, sheet_name="ค่าไม่ตรง")
                self._update_progress(step_inc=1, note="บันทึกไฟล์แล้ว")
                self._finish_progress("ส่งออกเสร็จแล้ว ✅")
            QtWidgets.QMessageBox.information(self, "ส่งออก", f"✅ บันทึกสำเร็จที่:\n{path}\n\nจำนวนแถวที่ไม่ตรง: {len(self._valdiff_df):,}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "ข้อผิดพลาด", f"ไม่สามารถส่งออกได้: {e}")


# =============================
# Entrypoint (manual test)
# =============================
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    w = CompareWindow()
    w.show()
    sys.exit(app.exec_())
