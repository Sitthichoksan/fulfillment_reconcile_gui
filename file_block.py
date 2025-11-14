# =============================
# file_block.py (robust CSV reader) – FIXED VERSION
# =============================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Optional, List, Tuple

import pandas as pd
from PyQt5 import QtCore, QtGui, QtWidgets

SUPPORTED_EXT = (".csv", ".tsv", ".txt", ".xlsx", ".xls")
OPS = ["=", "!=", ">", ">=", "<", "<=", "contains", "in", "not in"]


# ---------- IO helpers ----------
def read_any(path: str, delimiter: Optional[str] = None) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)

    # Excel
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p)

    encodings = ["utf-8", "utf-8-sig", "cp874", "cp1252", "latin1"]
    read_kwargs = dict(low_memory=False)

    try:
        import pandas as _pd
        if hasattr(_pd, "options"):
            read_kwargs["dtype_backend"] = "numpy_nullable"
    except Exception:
        pass

    def try_read(delim, engine=None):
        last_err = None
        for enc in encodings:
            try:
                df = pd.read_csv(
                    p,
                    delimiter=delim,
                    encoding=enc,
                    engine=engine,
                    **read_kwargs
                )
                if delim is not None and df.shape[1] == 1:
                    continue
                return df
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err

    if delimiter is None or delimiter == "auto":
        for d in [",", "|", "\t", ";"]:
            try:
                df = try_read(d)
                if df.shape[1] >= 2:
                    return df
            except Exception:
                continue
        return try_read(None, engine="python")
    else:
        if delimiter in ["\\t", "\t"]:
            delimiter = "\t"
        return try_read(delimiter)


# ---------- Filters ----------
def apply_conditions(df: pd.DataFrame, conds: List[Tuple[str, str, str]]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for col, op, raw in conds:
        if not col or not op:
            continue
        if op in {"in", "not in"}:
            parts = [x.strip() for x in str(raw).split(",") if x.strip()]
            if op == "in":
                out = out[out[col].astype(str).isin(parts)]
            else:
                out = out[~out[col].astype(str).isin(parts)]
        elif op == "contains":
            out = out[out[col].astype(str).str.contains(str(raw), na=False, regex=False)]
        else:
            left = out[col]
            try:
                left_num = pd.to_numeric(left, errors="coerce")
                right_num = pd.to_numeric(pd.Series([raw] * len(out)), errors="coerce").iloc[0]
                both_num = not pd.isna(right_num)
            except Exception:
                both_num = False

            if both_num and op in ["=", "!=", ">", ">=", "<", "<="]:
                if op == "=":
                    out = out[left_num == right_num]
                elif op == "!=":
                    out = out[left_num != right_num]
                elif op == ">":
                    out = out[left_num > right_num]
                elif op == ">=":
                    out = out[left_num >= right_num]
                elif op == "<":
                    out = out[left_num < right_num]
                elif op == "<=":
                    out = out[left_num <= right_num]
            else:
                left_s = left.astype(str)
                right = str(raw)
                if op == "=":
                    out = out[left_s == right]
                elif op == "!=":
                    out = out[left_s != right]
                elif op == ">":
                    out = out[left_s > right]
                elif op == ">=":
                    out = out[left_s >= right]
                elif op == "<":
                    out = out[left_s < right]
                elif op == "<=":
                    out = out[left_s <= right]
    return out


# ---------- Pandas Model ----------
class PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df: Optional[pd.DataFrame] = None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._df)

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
            return str(self._df.columns[section])
        return str(section)

    def set_df(self, df: pd.DataFrame):
        self.beginResetModel()
        self._df = df.copy() if df is not None else pd.DataFrame()
        self.endResetModel()


# ---------- FileBlock Widget ----------
class FileBlock(QtWidgets.QGroupBox):
    dataChanged = QtCore.pyqtSignal()

    def __init__(self, title: str):
        super().__init__(title)
        self.path_edit = QtWidgets.QLineEdit()
        self.browse_btn = QtWidgets.QPushButton("Browse…")
        self.delim_edit = QtWidgets.QComboBox()
        self.delim_edit.addItems(["auto", ",", "|", "\t", ";"])

        self.preview_btn = QtWidgets.QPushButton("Preview")
        self.clear_btn = QtWidgets.QPushButton("Clear")

        self.key1 = QtWidgets.QComboBox()
        self.key2 = QtWidgets.QComboBox()
        self.key3 = QtWidgets.QComboBox()

        for cb in (self.key1, self.key2, self.key3):
            cb.setEditable(False)

        self.cond_rows = []
        for _ in range(3):
            c_col = QtWidgets.QComboBox()
            c_op = QtWidgets.QComboBox()
            c_val = QtWidgets.QLineEdit()
            c_op.addItems(OPS)
            self.cond_rows.append((c_col, c_op, c_val))

        self.table = QtWidgets.QTableView()
        self.table.setModel(PandasModel(pd.DataFrame()))
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)

        form = QtWidgets.QGridLayout()
        self.setLayout(form)

        form.addWidget(QtWidgets.QLabel("File:"), 0, 0)
        form.addWidget(self.path_edit, 0, 1, 1, 4)
        form.add.addWidget(self.browse_btn, 0, 5)

        form.addWidget(QtWidgets.QLabel("Delimiter:"), 1, 0)
        form.addWidget(self.delim_edit, 1, 1)
        form.addWidget(self.preview_btn, 1, 4)
        form.addWidget(self.clear_btn, 1, 5)

        form.addWidget(QtWidgets.QLabel("Key 1:"), 2, 0)
        form.addWidget(self.key1, 2, 1)
        form.addWidget(QtWidgets.QLabel("Key 2:"), 2, 2)
        form.addWidget(self.key2, 2, 3)
        form.addWidget(QtWidgets.QLabel("Key 3:"), 2, 4)
        form.addWidget(self.key3, 2, 5)

        for i, (c_col, c_op, c_val) in enumerate(self.cond_rows):
            form.addWidget(QtWidgets.QLabel(f"Condition {i+1}"), 3 + i, 0)
            form.addWidget(c_col, 3 + i, 1)
            form.addWidget(c_op, 3 + i, 2)
            form.addWidget(c_val, 3 + i, 3, 1, 3)

        form.addWidget(self.table, 6, 0, 1, 6)

        self.df_raw = None
        self.df_filtered = None

        # ==== FIXED ====
        self.browse_btn.clicked.connect(self._on_browse)
        # macOS FIX → ไม่ใช้ editingFinished เพราะถูก trigger อัตโนมัติหลังโหลดไฟล์
        # self.path_edit.editingFinished.connect(self.on_path_changed)   # ❌ ลบ
        self.path_edit.returnPressed.connect(self.on_path_changed)       # ✔ FIX

        self.preview_btn.clicked.connect(self.refresh_preview)
        self.clear_btn.clicked.connect(self.on_clear)

        for cb in (self.key1, self.key2, self.key3):
            cb.currentIndexChanged.connect(self._emit_changed)

        for (c_col, c_op, c_val) in self.cond_rows:
            c_col.currentIndexChanged.connect(self._emit_changed)
            c_op.currentIndexChanged.connect(self._emit_changed)
            c_val.textChanged.connect(self._emit_changed)

    # ---------- FIXED: QFileDialog ----------
    def _on_browse(self):
        dlg = QtWidgets.QFileDialog(self)
        dlg.setWindowTitle("เลือกไฟล์ข้อมูล")
        dlg.setNameFilter("Data files (*.csv *.tsv *.txt *.xlsx *.xls);;All files (*.*)")
        dlg.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        dlg.setOptions(
            QtWidgets.QFileDialog.DontUseNativeDialog |
            QtWidgets.QFileDialog.ReadOnly
        )

        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            path = dlg.selectedFiles()[0]
            dlg.close()
            self.set_path(path)

    # ---------- FIXED: set_path ----------
    def set_path(self, path: str):
        self.path_edit.setText(path)
        self.on_path_changed()

    # ---------- rest of methods ----------
    def on_path_changed(self):
        path = self.path_edit.text().strip()
        if not path:
            return
        delim_text = self.delim_edit.currentText()
        delim = None if delim_text == "auto" else ("\t" if delim_text in ["\\t", "\t"] else delim_text)

        try:
            df = read_any(path, delimiter=delim)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Load error", f"{e}")
            return

        self.df_raw = df
        self.populate_columns(df.columns.tolist())
        self.refresh_preview()
        self.dataChanged.emit()

    def _emit_changed(self):
        self.dataChanged.emit()

    def on_clear(self):
        for cb in (self.key1, self.key2, self.key3):
            cb.setCurrentIndex(0)
        for (c_col, c_op, c_val) in self.cond_rows:
            c_col.setCurrentIndex(0)
            c_op.setCurrentIndex(0)
            c_val.clear()
        self.refresh_preview()
        self.dataChanged.emit()

    def populate_columns(self, cols):
        for cb in (self.key1, self.key2, self.key3):
            cb.clear()
            cb.addItem("")
            cb.addItems(cols)
        for (c_col, _, _) in self.cond_rows:
            c_col.clear()
            c_col.addItem("")
            c_col.addItems(cols)

    def conditions(self):
        return [(c_col.currentText(), c_op.currentText(), c_val.text())
                for (c_col, c_op, c_val) in self.cond_rows]

    def keys(self):
        return [self.key1.currentText(), self.key2.currentText(), self.key3.currentText()]

    def refresh_preview(self):
        if self.df_raw is None:
            return
        self.df_filtered = apply_conditions(self.df_raw, self.conditions())
        prev = self.df_filtered.head(5000)

        model = self.table.model()
        if isinstance(model, PandasModel):
            model.set_df(prev)
        else:
            self.table.setModel(PandasModel(prev))

    def current_df_or_none(self):
        return self.df_filtered if self.df_filtered is not None else self.df_raw

    def set_keys(self, keys):
        ks = keys + ["", "", ""]
        self.key1.setCurrentText(ks[0])
        self.key2.setCurrentText(ks[1])
        self.key3.setCurrentText(ks[2])

    def clear_all(self):
        self.path_edit.clear()
        self.df_raw = None
        self.df_filtered = None
        self.on_clear()

    def reload(self):
        self.on_path_changed()
