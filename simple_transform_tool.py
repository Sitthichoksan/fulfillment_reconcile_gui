
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Transform Tool (PyQt5) – Trim / Delete / Pad / Group-Sum / Calculation
Standalone widget that can be used as a plugin in Reconcile GUI.
Features
- Load CSV/TSV/TXT/XLS/XLSX with simple auto-delimiter & encoding
- Preview: left = original, right = current output (single operation from original)
- Trim: filter rows (optional) then trim values in a column
- Delete: filter rows and delete matching rows
- Pad: pad left/right with chosen character up to fixed length (only-shorter option)
- Group / Sum: Group only, Sum only, Group + Sum (dropdown)
- Calculation: (column|constant) <op> (column|constant) → new column
- Export: CSV / Excel from current output
"""
from pathlib import Path
from typing import Optional
import pandas as pd
from PyQt5 import QtCore, QtGui, QtWidgets

# ---------- small helpers ----------
def _read_any(path: Path) -> pd.DataFrame:
    """Tiny reader with delimiter+encoding guess, always returns all columns as string."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    suf = p.suffix.lower()
    if suf in [".xlsx", ".xls"]:
        df = pd.read_excel(p, dtype=str)
    else:
        # sniff first line to guess delimiter
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                head = f.readline()
        except Exception:
            head = ""
        cand = {",": head.count(","), "|": head.count("|"), "\t": head.count("\t"), ";": head.count(";")}
        order = [",", "|", "\t", ";"]
        sep = max(order, key=lambda k: (cand.get(k, 0), -order.index(k)))
        encodings = ["utf-8-sig", "utf-8", "cp874", "cp1252", "latin1"]
        last_err = None
        for enc in encodings:
            try:
                df = pd.read_csv(
                    p,
                    sep=sep,
                    dtype=str,
                    na_filter=False,
                    low_memory=False,
                    encoding=enc,
                )
                break
            except Exception as e:
                last_err = e
                df = None  # type: ignore
        if df is None:
            raise last_err or RuntimeError("Cannot read file")
    # ensure string columns
    for c in df.columns:
        df[c] = df[c].astype(str)
    return df

def _safe_numeric(s: pd.Series) -> pd.Series:
    s2 = s.astype(str).str.replace(",", "", regex=False)
    s2 = s2.str.replace("(", "-", regex=False).str.replace(")", "", regex=False)
    return pd.to_numeric(s2, errors="coerce")

class _PandasModel(QtCore.QAbstractTableModel):
    def __init__(self, df: Optional[pd.DataFrame] = None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()
    def set_df(self, df: Optional[pd.DataFrame]):
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()
    def rowCount(self, parent=QtCore.QModelIndex()):  # type: ignore[override]
        return 0 if self._df is None else len(self._df)
    def columnCount(self, parent=QtCore.QModelIndex()):  # type: ignore[override]
        return 0 if self._df is None else self._df.shape[1]
    def data(self, index, role=QtCore.Qt.DisplayRole):  # type: ignore[override]
        if not index.isValid() or self._df is None:
            return None
        if role in (QtCore.Qt.DisplayRole, QtCore.Qt.EditRole):
            val = self._df.iat[index.row(), index.column()]
            return "" if pd.isna(val) else str(val)
        return None
    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):  # type: ignore[override]
        if self._df is None:
            return None
        if role == QtCore.Qt.DisplayRole:
            if orientation == QtCore.Qt.Horizontal:
                try:
                    return str(self._df.columns[section])
                except Exception:
                    return ""
            else:
                return section + 1
        return None

# ---------- main widget ----------
class SimpleTransformTool(QtWidgets.QWidget):
    WINDOW_TITLE = "Reconcile – Simple Transform Tool"
    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: Optional[Path] = None
        self.df_orig: pd.DataFrame = pd.DataFrame()
        self.df_out: pd.DataFrame = pd.DataFrame()
        # try theme helpers if available
        try:
            from theme import set_table_defaults  # type: ignore
            self._set_table_defaults = set_table_defaults
        except Exception:
            def _fallback(view: QtWidgets.QTableView):
                view.setAlternatingRowColors(True)
                view.setSortingEnabled(True)
                view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
                view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
                view.verticalHeader().setVisible(False)
                view.verticalHeader().setDefaultSectionSize(22)
                hh = view.horizontalHeader()
                hh.setStretchLastSection(True)
                hh.setMinimumSectionSize(80)
            self._set_table_defaults = _fallback
        self._build_ui()
    # ----- UI -----
    def _build_ui(self):
        self.setWindowTitle(self.WINDOW_TITLE)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)
        # -------------------------------
        # TOP BAR
        # -------------------------------
        top = QtWidgets.QHBoxLayout()
        self.btn_load = QtWidgets.QPushButton("📂 Load file")
        self.btn_reset = QtWidgets.QPushButton("↺ Reset output")
        self.lbl_file = QtWidgets.QLabel("No file loaded")
        self.lbl_rows = QtWidgets.QLabel("Rows: 0")
        self.cmb_preview = QtWidgets.QComboBox()
        self.cmb_preview.addItems(["1,000", "5,000", "20,000", "All"])
        self.cmb_preview.setCurrentIndex(1)
        self.btn_export_csv = QtWidgets.QPushButton("💾 Export CSV")
        self.btn_export_xlsx = QtWidgets.QPushButton("💾 Export Excel")
        for lab in (self.lbl_file, self.lbl_rows):
            lab.setStyleSheet("color:#6b7280; font-size:12px;")
        top.addWidget(self.btn_load)
        top.addWidget(self.btn_reset)
        top.addStretch()
        top.addWidget(QtWidgets.QLabel("Preview limit:"))
        top.addWidget(self.cmb_preview)
        top.addSpacing(8)
        top.addWidget(self.lbl_file)
        top.addSpacing(8)
        top.addWidget(self.lbl_rows)
        top.addSpacing(8)
        top.addWidget(self.btn_export_csv)
        top.addWidget(self.btn_export_xlsx)
        root.addLayout(top)
        # ------------------------------------------------------
        # MAIN SPLITTER (TOP = calculation panel, BOTTOM = tables)
        # ------------------------------------------------------
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        # ------------------------------------------------------
        # TOP PART — CALCULATION PANEL ONLY
        # ------------------------------------------------------
        calc_panel = QtWidgets.QWidget()
        calc_layout = QtWidgets.QVBoxLayout(calc_panel)
        calc_layout.setContentsMargins(12, 12, 12, 12)
        calc_layout.setSpacing(10)
        # Tabs (Trim / Delete / Pad / Group / Calc)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabPosition(QtWidgets.QTabWidget.North)
        self.tabs.setMinimumHeight(230)
        self._init_tab_trim()
        self._init_tab_delete()
        self._init_tab_pad()
        self._init_tab_group()
        self._init_tab_calc()
        calc_layout.addWidget(self.tabs)
        main_splitter.addWidget(calc_panel)
        # ------------------------------------------------------
        # BOTTOM PART — 2 PREVIEW TABLES SIDE BY SIDE
        # ------------------------------------------------------
        preview_widget = QtWidgets.QWidget()
        pv = QtWidgets.QHBoxLayout(preview_widget)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(8)
        # LEFT: Input Preview
        left_box = QtWidgets.QVBoxLayout()
        lab_in = QtWidgets.QLabel("Input preview (Original file)")
        lab_in.setStyleSheet("font-weight:600; color:#374151;")
        self.table_orig = QtWidgets.QTableView()
        self.model_orig = _PandasModel()
        self.table_orig.setModel(self.model_orig)
        self._set_table_defaults(self.table_orig)
        left_box.addWidget(lab_in)
        left_box.addWidget(self.table_orig)
        # RIGHT: Output Preview
        right_box = QtWidgets.QVBoxLayout()
        lab_out = QtWidgets.QLabel("Output preview (After operation)")
        lab_out.setStyleSheet("font-weight:600; color:#374151;")
        self.table_out = QtWidgets.QTableView()
        self.model_out = _PandasModel()
        self.table_out.setModel(self.model_out)
        self._set_table_defaults(self.table_out)
        right_box.addWidget(lab_out)
        right_box.addWidget(self.table_out)
        pv.addLayout(left_box, 1)
        pv.addLayout(right_box, 1)
        main_splitter.addWidget(preview_widget)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 7)
        root.addWidget(main_splitter)
        # STATUS BAR
        self.status = QtWidgets.QStatusBar()
        self.status.showMessage("Ready")
        root.addWidget(self.status)
        # SIGNALS
        self.btn_load.clicked.connect(self._on_load)
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_export_csv.clicked.connect(lambda: self._export("csv"))
        self.btn_export_xlsx.clicked.connect(lambda: self._export("xlsx"))
        self.cmb_preview.currentIndexChanged.connect(lambda *_: self._refresh_tables())
        # wire signals
        self.btn_load.clicked.connect(self._on_load)
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_export_csv.clicked.connect(lambda: self._export("csv"))
        self.btn_export_xlsx.clicked.connect(lambda: self._export("xlsx"))
        self.cmb_preview.currentIndexChanged.connect(lambda *_: self._refresh_tables())
    # ----- helpers -----
    def _preview_limit(self) -> Optional[int]:
        txt = self.cmb_preview.currentText()
        if "All" in txt:
            return None
        return int(txt.replace(",", ""))
    def _preview_df(self, df: Optional[pd.DataFrame]) -> pd.DataFrame:
        if df is None:
            return pd.DataFrame()
        limit = self._preview_limit()
        if limit is None:
            out = df.copy()
        else:
            out = df.head(limit).copy()
        # ----- เพิ่มคอลัมน์ Row Number -----
        out.insert(0, "Row", range(1, len(out) + 1))
        return out
    def _refresh_tables(self):
        self.model_orig.set_df(self._preview_df(self.df_orig))
        self.model_out.set_df(self._preview_df(self.df_out))
        self.lbl_rows.setText(f"Rows: {len(self.df_orig) if self.df_orig is not None else 0}")
        self.table_orig.resizeColumnsToContents()
        self.table_out.resizeColumnsToContents()
    def _set_status(self, msg: str):
        self.status.showMessage(msg)
    def _busy(self, msg: str):
        """Context manager for busy cursor + status."""
        class _Ctx:
            def __init__(self, outer, text):
                self.outer = outer
                self.text = text
            def __enter__(self):
                QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
                self.outer._set_status(self.text + "…")
            def __exit__(self, exc_type, exc, tb):
                QtWidgets.QApplication.restoreOverrideCursor()
                if exc is None:
                    self.outer._set_status(self.text + " ✅")
                else:
                    self.outer._set_status(str(exc))
        return _Ctx(self, msg)
    # ----- tabs -----
    def _init_tab_trim(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        # filter row
        f1 = QtWidgets.QHBoxLayout()
        f1.addWidget(QtWidgets.QLabel("Column"))
        self.trim_col = QtWidgets.QComboBox()
        f1.addWidget(self.trim_col, 1)
        self.trim_filter_op = QtWidgets.QComboBox()
        self.trim_filter_op.addItems(["(ทุกแถว)", "equals", "contains", "starts with", "ends with"])
        f1.addWidget(self.trim_filter_op)
        self.trim_filter_val = QtWidgets.QLineEdit()
        self.trim_filter_val.setPlaceholderText("ค่าที่ต้องการ filter (ถ้าเลือก '(ทุกแถว)' จะไม่ใช้ filter)")
        f1.addWidget(self.trim_filter_val, 2)
        lay.addLayout(f1)
        # trim options
        f2 = QtWidgets.QHBoxLayout()
        self.trim_mode = QtWidgets.QComboBox()
        self.trim_mode.addItems([
            "strip spaces (ซ้าย+ขวา)",
            "lstrip spaces (ซ้าย)",
            "rstrip spaces (ขวา)",
            "remove substring",
            "keep first N chars",
            "keep last N chars",
        ])
        f2.addWidget(QtWidgets.QLabel("Trim mode"))
        f2.addWidget(self.trim_mode, 2)
        self.trim_arg = QtWidgets.QSpinBox()
        self.trim_arg.setRange(0, 999)
        self.trim_arg.setValue(5)
        f2.addWidget(QtWidgets.QLabel("N"))
        f2.addWidget(self.trim_arg)
        self.trim_substr = QtWidgets.QLineEdit()
        self.trim_substr.setPlaceholderText("substring ที่ต้องการลบ (ใช้กับ 'remove substring')")
        f2.addWidget(self.trim_substr, 2)
        self.btn_trim_apply = QtWidgets.QPushButton("Apply")
        f2.addWidget(self.btn_trim_apply)
        lay.addLayout(f2)
        note = QtWidgets.QLabel(
            "ตัวอย่าง: เลือก Column = SUPPLIER, Filter = contains 'CS1', Trim mode = keep last 4 chars\n"
            "ระบบจะ trim เฉพาะแถวที่ SUPPLIER มี 'CS1' เท่านั้น (ใช้ข้อมูลจาก original file)"
        )
        note.setStyleSheet("color:#6b7280;")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        self.btn_trim_apply.clicked.connect(self._do_trim)
        self.tabs.addTab(w, "Trim")
    def _init_tab_delete(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        r1 = QtWidgets.QHBoxLayout()
        r1.addWidget(QtWidgets.QLabel("Column"))
        self.del_col = QtWidgets.QComboBox()
        r1.addWidget(self.del_col, 1)
        self.del_op = QtWidgets.QComboBox()
        self.del_op.addItems(["equals", "not equals", "contains", "not contains", "starts with", "ends with"])
        r1.addWidget(self.del_op)
        self.del_val = QtWidgets.QLineEdit()
        self.del_val.setPlaceholderText("ค่าที่ใช้หาแถวที่จะลบ เช่น CS1")
        r1.addWidget(self.del_val, 2)
        self.btn_delete_apply = QtWidgets.QPushButton("Delete rows")
        r1.addWidget(self.btn_delete_apply)
        lay.addLayout(r1)
        note = QtWidgets.QLabel(
            "หมายเหตุ: การลบคือการลบทั้งแถวจาก original file (ผลลัพธ์ไปแสดงใน Output preview)"
        )
        note.setStyleSheet("color:#6b7280;")
        lay.addWidget(note)
        lay.addStretch(1)
        self.btn_delete_apply.clicked.connect(self._do_delete)
        self.tabs.addTab(w, "Delete")
    def _init_tab_pad(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        r1 = QtWidgets.QHBoxLayout()
        r1.addWidget(QtWidgets.QLabel("Column"))
        self.pad_col = QtWidgets.QComboBox()
        r1.addWidget(self.pad_col, 1)
        r1.addWidget(QtWidgets.QLabel("Length"))
        self.pad_len = QtWidgets.QSpinBox()
        self.pad_len.setRange(1, 500)
        self.pad_len.setValue(8)
        r1.addWidget(self.pad_len)
        r1.addWidget(QtWidgets.QLabel("Fill char"))
        self.pad_char = QtWidgets.QLineEdit("0")
        self.pad_char.setMaxLength(1)
        self.pad_char.setFixedWidth(40)
        r1.addWidget(self.pad_char)
        self.pad_side = QtWidgets.QComboBox()
        self.pad_side.addItems(["Left", "Right"])
        r1.addWidget(self.pad_side)
        self.btn_pad_apply = QtWidgets.QPushButton("Apply")
        r1.addWidget(self.btn_pad_apply)
        lay.addLayout(r1)
        self.chk_pad_only_shorter = QtWidgets.QCheckBox("ทำเฉพาะค่าที่สั้นกว่าความยาวที่กำหนด (ไม่ตัดค่าที่ยาวเกิน)")
        self.chk_pad_only_shorter.setChecked(True)
        lay.addWidget(self.chk_pad_only_shorter)
        note = QtWidgets.QLabel("ตัวอย่าง: Column=STORE, Length=8, Char='0', Side=Left → 6417 → 00006417")
        note.setStyleSheet("color:#6b7280;")
        lay.addWidget(note)
        lay.addStretch(1)
        self.btn_pad_apply.clicked.connect(self._do_pad)
        self.tabs.addTab(w, "Pad")
    def _init_tab_group(self):
        """Group/Sum tab – dropdown version with mode toggle."""
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        # mode
        mode_box = QtWidgets.QGroupBox("Mode")
        ml = QtWidgets.QHBoxLayout(mode_box)
        self.radio_group_only = QtWidgets.QRadioButton("Group only")
        self.radio_sum_only = QtWidgets.QRadioButton("Sum only")
        self.radio_group_sum = QtWidgets.QRadioButton("Group + Sum")
        self.radio_group_sum.setChecked(True)
        ml.addWidget(self.radio_group_only)
        ml.addWidget(self.radio_sum_only)
        ml.addWidget(self.radio_group_sum)
        lay.addWidget(mode_box)
        # dropdowns (single select)
        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignRight)
        self.ddl_group_by = QtWidgets.QComboBox()
        self.ddl_sum_col = QtWidgets.QComboBox()
        form.addRow("Group by column:", self.ddl_group_by)
        form.addRow("Sum column:", self.ddl_sum_col)
        lay.addLayout(form)
        bottom = QtWidgets.QHBoxLayout()
        self.btn_group_apply = QtWidgets.QPushButton("Run Group / Sum")
        bottom.addStretch(1)
        bottom.addWidget(self.btn_group_apply)
        lay.addLayout(bottom)
        note = QtWidgets.QLabel(
            "กติกา:\n"
            "• Group only → ใช้ Group by column จาก original แล้วคืน count ต่อกลุ่ม\n"
            "• Sum only → ใช้ Sum column จาก original → ได้ผลรวม 1 แถว\n"
            "• Group + Sum → Group ตาม Group by column แล้ว sum ตาม Sum column"
        )
        note.setStyleSheet("color:#6b7280;")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        # dynamic visibility
        def update_group_sum_visibility():
            if self.radio_group_only.isChecked():
                # show only group
                self.ddl_group_by.setVisible(True)
                form.labelForField(self.ddl_group_by).setVisible(True)
                self.ddl_sum_col.setVisible(False)
                form.labelForField(self.ddl_sum_col).setVisible(False)
            elif self.radio_sum_only.isChecked():
                # show only sum
                self.ddl_group_by.setVisible(False)
                form.labelForField(self.ddl_group_by).setVisible(False)
                self.ddl_sum_col.setVisible(True)
                form.labelForField(self.ddl_sum_col).setVisible(True)
            else:
                # show both
                self.ddl_group_by.setVisible(True)
                form.labelForField(self.ddl_group_by).setVisible(True)
                self.ddl_sum_col.setVisible(True)
                form.labelForField(self.ddl_sum_col).setVisible(True)
        self.radio_group_only.toggled.connect(update_group_sum_visibility)
        self.radio_sum_only.toggled.connect(update_group_sum_visibility)
        self.radio_group_sum.toggled.connect(update_group_sum_visibility)
        update_group_sum_visibility()
        self.btn_group_apply.clicked.connect(self._do_group_sum)
        self.tabs.addTab(w, "Group / Sum")
    def _init_tab_calc(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        # row: left operand
        r1 = QtWidgets.QHBoxLayout()
        r1.addWidget(QtWidgets.QLabel("Left"))
        self.cal_left_mode_col = QtWidgets.QRadioButton("Column")
        self.cal_left_mode_const = QtWidgets.QRadioButton("Constant")
        self.cal_left_mode_col.setChecked(True)
        self.cal_left_col = QtWidgets.QComboBox()
        self.cal_left_const = QtWidgets.QLineEdit("0")
        r1.addWidget(self.cal_left_mode_col)
        r1.addWidget(self.cal_left_col, 1)
        r1.addWidget(self.cal_left_mode_const)
        r1.addWidget(self.cal_left_const, 1)
        lay.addLayout(r1)
        # row: operator & right operand
        r2 = QtWidgets.QHBoxLayout()
        r2.addWidget(QtWidgets.QLabel("Operator"))
        self.cal_op = QtWidgets.QComboBox()
        self.cal_op.addItems(["+", "-", "*", "/", "//", "%"])
        r2.addWidget(self.cal_op)
        r2.addSpacing(12)
        r2.addWidget(QtWidgets.QLabel("Right"))
        self.cal_right_mode_col = QtWidgets.QRadioButton("Column")
        self.cal_right_mode_const = QtWidgets.QRadioButton("Constant")
        self.cal_right_mode_col.setChecked(True)
        self.cal_right_col = QtWidgets.QComboBox()
        self.cal_right_const = QtWidgets.QLineEdit("0")
        r2.addWidget(self.cal_right_mode_col)
        r2.addWidget(self.cal_right_col, 1)
        r2.addWidget(self.cal_right_mode_const)
        r2.addWidget(self.cal_right_const, 1)
        lay.addLayout(r2)
        # row: result name + button
        r3 = QtWidgets.QHBoxLayout()
        r3.addWidget(QtWidgets.QLabel("Result column name"))
        self.cal_result_name = QtWidgets.QLineEdit("result")
        r3.addWidget(self.cal_result_name, 1)
        self.btn_cal_apply = QtWidgets.QPushButton("Compute")
        r3.addWidget(self.btn_cal_apply)
        lay.addLayout(r3)
        note = QtWidgets.QLabel(
            "ตัวอย่าง: Left=Column QTY, Operator=*, Right=Constant 7 → result = QTY*7\n"
            "ใช้ข้อมูลจาก original file ทุกครั้ง (ไม่ chain จาก Output เดิม)"
        )
        note.setStyleSheet("color:#6b7280;")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addStretch(1)
        # mode toggles
        self.cal_left_mode_col.toggled.connect(self._update_calc_enabled)
        self.cal_right_mode_col.toggled.connect(self._update_calc_enabled)
        self._update_calc_enabled()
        self.btn_cal_apply.clicked.connect(self._do_calc)
        self.tabs.addTab(w, "Calculation")
    def _update_calc_enabled(self):
        self.cal_left_col.setEnabled(self.cal_left_mode_col.isChecked())
        self.cal_left_const.setEnabled(self.cal_left_mode_const.isChecked())
        self.cal_right_col.setEnabled(self.cal_right_mode_col.isChecked())
        self.cal_right_const.setEnabled(self.cal_right_mode_const.isChecked())
    # ----- top actions -----
    def _on_load(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "เลือกไฟล์ข้อมูล", "", "Data files (*.csv *.tsv *.txt *.xlsx *.xls);;All files (*.*)"
        )
        if not path:
            return
        try:
            with self._busy("Loading file"):
                df = _read_any(Path(path))
                self._path = Path(path)
                self.df_orig = df
                self.df_out = df.copy()
                self.lbl_file.setText(self._path.name)
                self._refresh_column_widgets()
                self._refresh_tables()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load error", str(e))
    def _on_reset(self):
        if self.df_orig is None or self.df_orig.empty:
            return
        with self._busy("Resetting output"):
            self.df_out = self.df_orig.copy()
            self._refresh_column_widgets()
            self._refresh_tables()
    def _export(self, kind: str):
        if self.df_out is None or self.df_out.empty:
            QtWidgets.QMessageBox.information(self, "Export", "ยังไม่มีข้อมูล Output")
            return
        if kind == "csv":
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save CSV", "output.csv", "CSV files (*.csv)"
            )
        else:
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self, "Save Excel", "output.xlsx", "Excel files (*.xlsx)"
            )
        if not path:
            return
        try:
            with self._busy("Exporting"):
                if kind == "csv":
                    self.df_out.to_csv(path, index=False, encoding="utf-8-sig")
                else:
                    self.df_out.to_excel(path, index=False)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export error", str(e))
    def _refresh_column_widgets(self):
        """
        Refresh combobox/dropdown columns.
        ใช้ column จาก original file (df_orig) เสมอ ตาม Option 2
        """
        cols = list(self.df_orig.columns) if isinstance(self.df_orig, pd.DataFrame) else []
        # combobox ทั่วไป
        for cb in [
            getattr(self, "trim_col", None),
            getattr(self, "del_col", None),
            getattr(self, "pad_col", None),
            getattr(self, "cal_left_col", None),
            getattr(self, "cal_right_col", None),
        ]:
            if cb is None:
                continue
            prev = cb.currentText()
            cb.clear()
            cb.addItems(cols)
            if prev in cols:
                cb.setCurrentText(prev)
        # dropdown group / sum
        if hasattr(self, "ddl_group_by") and hasattr(self, "ddl_sum_col"):
            prev_group = self.ddl_group_by.currentText()
            prev_sum = self.ddl_sum_col.currentText()
            self.ddl_group_by.clear()
            self.ddl_sum_col.clear()
            self.ddl_group_by.addItems(cols)
            self.ddl_sum_col.addItems(cols)
            if prev_group in cols:
                self.ddl_group_by.setCurrentText(prev_group)
            if prev_sum in cols:
                self.ddl_sum_col.setCurrentText(prev_sum)
    # ----- operations -----
    def _filter_mask(self, series: pd.Series, op: str, val: str) -> pd.Series:
        s = series.astype(str)
        if op == "equals":
            return s == val
        if op == "not equals":
            return s != val
        if op == "contains":
            return s.str.contains(val, na=False, regex=False)
        if op == "not contains":
            return ~s.str.contains(val, na=False, regex=False)
        if op == "starts with":
            return s.str.startswith(val, na=False)
        if op == "ends with":
            return s.str.endswith(val, na=False)
        return s == val
    def _do_trim(self):
        if self.df_orig is None or self.df_orig.empty:
            return
        col = self.trim_col.currentText()
        if not col or col not in self.df_orig.columns:
            return
        with self._busy(f"Trimming '{col}'"):
            df = self.df_orig.copy()
            s = df[col].astype(str)
            # filter
            op = self.trim_filter_op.currentText()
            val = self.trim_filter_val.text().strip()
            if op == "(ทุกแถว)" or not val:
                mask = pd.Series([True] * len(df), index=df.index)
            else:
                mask = self._filter_mask(s, op, val)
            mode = self.trim_mode.currentText()
            n = int(self.trim_arg.value())
            substr = self.trim_substr.text()
            s_new = s.copy()
            if mode == "strip spaces (ซ้าย+ขวา)":
                s_new[mask] = s_new[mask].str.strip()
            elif mode == "lstrip spaces (ซ้าย)":
                s_new[mask] = s_new[mask].str.lstrip()
            elif mode == "rstrip spaces (ขวา)":
                s_new[mask] = s_new[mask].str.rstrip()
            elif mode == "remove substring":
                if substr:
                    s_new[mask] = s_new[mask].str.replace(substr, "", regex=False)
            elif mode == "keep first N chars":
                s_new[mask] = s_new[mask].str.slice(0, n)
            elif mode == "keep last N chars":
                s_new[mask] = s_new[mask].str.slice(-n if n > 0 else None)
            df[col] = s_new
            self.df_out = df
            self._refresh_tables()
            self._refresh_column_widgets()
    def _do_delete(self):
        if self.df_orig is None or self.df_orig.empty:
            return
        col = self.del_col.currentText()
        if not col or col not in self.df_orig.columns:
            return
        val = self.del_val.text().strip()
        if not val:
            return
        op = self.del_op.currentText()
        with self._busy(f"Deleting rows from '{col}'"):
            df = self.df_orig.copy()
            m = self._filter_mask(df[col], op, val)
            before = len(df)
            df = df.loc[~m].copy()
            removed = before - len(df)
            self.df_out = df
            self._refresh_tables()
        QtWidgets.QMessageBox.information(self, "Delete", f"ลบ {removed} แถวเรียบร้อยแล้ว")
    def _do_pad(self):
        if self.df_orig is None or self.df_orig.empty:
            return
        col = self.pad_col.currentText()
        if not col or col not in self.df_orig.columns:
            return
        n = int(self.pad_len.value())
        if n <= 0:
            return
        ch = (self.pad_char.text() or "0")[0]
        side = self.pad_side.currentText()
        only_shorter = self.chk_pad_only_shorter.isChecked()
        with self._busy(f"Padding '{col}'"):
            df = self.df_orig.copy()
            s = df[col].astype(str)
            if only_shorter:
                mask = s.str.len() < n
            else:
                mask = pd.Series([True] * len(df), index=df.index)
            if side == "Left":
                if ch == "0":
                    s_pad = s.str.zfill(n)
                else:
                    s_pad = s.str.pad(n, side="left", fillchar=ch)
            else:
                s_pad = s.str.pad(n, side="right", fillchar=ch)
            s.loc[mask] = s_pad.loc[mask]
            df[col] = s
            self.df_out = df
            self._refresh_tables()
            self._refresh_column_widgets()
    def _do_group_sum(self):
        if self.df_orig is None or self.df_orig.empty:
            return
        # Determine mode
        if self.radio_group_only.isChecked():
            mode = "group"
        elif self.radio_sum_only.isChecked():
            mode = "sum"
        else:
            mode = "group+sum"
        # Read selected columns from dropdowns
        grp_col = self.ddl_group_by.currentText().strip()
        sum_col = self.ddl_sum_col.currentText().strip()
        with self._busy("Running Group / Sum"):
            df = self.df_orig.copy()
            if mode == "group":
                if not grp_col or grp_col not in df.columns:
                    QtWidgets.QMessageBox.information(self, "Group", "โปรดเลือก Group by column")
                    return
                out = df.groupby([grp_col], dropna=False).size().reset_index(name="count")
            elif mode == "sum":
                if not sum_col or sum_col not in df.columns:
                    QtWidgets.QMessageBox.information(self, "Sum", "โปรดเลือก Sum column")
                    return
                out_val = _safe_numeric(df[sum_col]).sum()
                out = pd.DataFrame([{sum_col: out_val}])
            else:  # group+sum
                if not grp_col or grp_col not in df.columns:
                    QtWidgets.QMessageBox.information(self, "Group + Sum", "โปรดเลือก Group by column")
                    return
                if not sum_col or sum_col not in df.columns:
                    QtWidgets.QMessageBox.information(self, "Group + Sum", "โปรดเลือก Sum column")
                    return
                df2 = df.copy()
                df2[sum_col] = _safe_numeric(df2[sum_col])
                out = df2.groupby([grp_col], dropna=False)[sum_col].sum().reset_index()
            self.df_out = out
            self._refresh_tables()
            self._refresh_column_widgets()
    def _do_calc(self):
        if self.df_orig is None or self.df_orig.empty:
            return
        outname = self.cal_result_name.text().strip() or "result"
        def _get_operand(is_col: bool, col_cb: QtWidgets.QComboBox, const_edit: QtWidgets.QLineEdit) -> pd.Series:
            if is_col:
                col = col_cb.currentText()
                if not col or col not in self.df_orig.columns:
                    raise ValueError("กรุณาเลือกคอลัมน์ให้ครบ")
                return _safe_numeric(self.df_orig[col])
            else:
                txt = const_edit.text().strip()
                if txt == "":
                    val = 0.0
                else:
                    try:
                        val = float(txt)
                    except Exception:
                        raise ValueError(f"ค่า constant ไม่ใช่ตัวเลข: {txt}")
                return pd.Series([val] * len(self.df_orig), index=self.df_orig.index)
        try:
            with self._busy("Computing"):
                s_left = _get_operand(self.cal_left_mode_col.isChecked(), self.cal_left_col, self.cal_left_const)
                s_right = _get_operand(self.cal_right_mode_col.isChecked(), self.cal_right_col, self.cal_right_const)
                op = self.cal_op.currentText()
                if op == "+":
                    res = s_left + s_right
                elif op == "-":
                    res = s_left - s_right
                elif op == "*":
                    res = s_left * s_right
                elif op == "/":
                    s_right2 = s_right.replace(0, pd.NA)
                    res = s_left / s_right2
                elif op == "//":
                    s_right2 = s_right.replace(0, pd.NA)
                    res = (s_left // s_right2).astype("Float64")
                elif op == "%":
                    s_right2 = s_right.replace(0, pd.NA)
                    res = s_left % s_right2
                else:
                    res = pd.Series([pd.NA] * len(s_left), index=s_left.index)
                # clean inf/NaN -> empty string for display
                res = pd.to_numeric(res, errors="coerce")
                res = res.replace([pd.NA, float("inf"), float("-inf")], pd.NA)
                out_col = res.astype(object).where(~pd.isna(res), "")
                df = self.df_orig.copy()
                df[outname] = out_col
                self.df_out = df
                self._refresh_tables()
                self._refresh_column_widgets()
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Calculation", str(e))
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Calculation error", str(e))

# entrypoint for standalone run
EXPORTED_WIDGET = SimpleTransformTool
if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    try:
        from theme import apply_theme  # type: ignore
        apply_theme(app)
    except Exception:
        pass
    w = SimpleTransformTool()
    w.show()
    sys.exit(app.exec_())
