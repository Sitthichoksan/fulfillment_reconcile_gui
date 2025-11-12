# =============================
# sum_dialog.py
# =============================
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SumDialog – Aggregate options per side
- Group-by: None / Key1 / Key2 / Key3
- SUM columns: multi-select per side
- Where: (col/op/value) per side
- Buttons: OK / Apply & Close / Cancel

API:
    dlg = SumDialog(cols_a, cols_b, keys_a, keys_b, parent)
    if dlg.exec_() == QDialog.Accepted:
        opts = dlg.get_options()
        # opts = {
        #   'a': {'gb': 'None|Key1|Key2|Key3', 'sum': ['col', ...], 'where': (col, op, value)},
        #   'b': {...}
        # }

หมายเหตุ: ถ้าไม่ต้องการ aggregate ให้กด Cancel หรือเลือก Group-by = None ทั้งสองฝั่ง
"""

from typing import List, Tuple, Dict, Optional
from PyQt5 import QtCore, QtGui, QtWidgets


OPS = ["", "=", "!=", ">", ">=", "<", "<="]


class SumDialog(QtWidgets.QDialog):
    def __init__(self, cols_a: List[str], cols_b: List[str], keys_a: List[str], keys_b: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aggregate Options (A / B)")
        self.resize(860, 520)

        # ---- widgets (A) ----
        self.gb_a = QtWidgets.QComboBox(); self.gb_a.addItems(["None", "Key1", "Key2", "Key3"])
        self.sum_a = QtWidgets.QListWidget(); self.sum_a.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        for c in cols_a: self.sum_a.addItem(c)
        self.where_col_a = QtWidgets.QComboBox(); self.where_col_a.addItem(""); self.where_col_a.addItems(cols_a)
        self.where_op_a  = QtWidgets.QComboBox(); self.where_op_a.addItems(OPS)
        self.where_val_a = QtWidgets.QLineEdit()

        # ---- widgets (B) ----
        self.gb_b = QtWidgets.QComboBox(); self.gb_b.addItems(["None", "Key1", "Key2", "Key3"])
        self.sum_b = QtWidgets.QListWidget(); self.sum_b.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        for c in cols_b: self.sum_b.addItem(c)
        self.where_col_b = QtWidgets.QComboBox(); self.where_col_b.addItem(""); self.where_col_b.addItems(cols_b)
        self.where_op_b  = QtWidgets.QComboBox(); self.where_op_b.addItems(OPS)
        self.where_val_b = QtWidgets.QLineEdit()

        # ปรับขนาด list ให้มองเห็นชัด
        for lw in (self.sum_a, self.sum_b):
            lw.setMinimumHeight(200)
            lw.setAlternatingRowColors(True)

        # ---- layout ----
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        # Headers
        title_a = QtWidgets.QLabel("File A")
        title_b = QtWidgets.QLabel("File B")
        for t in (title_a, title_b):
            f = t.font(); f.setPointSize(12); f.setBold(True); t.setFont(f)
        grid.addWidget(title_a, 0, 0, 1, 2)
        grid.addWidget(title_b, 0, 2, 1, 2)

        # Group-by row
        grid.addWidget(QtWidgets.QLabel("Group by"), 1, 0)
        grid.addWidget(self.gb_a, 1, 1)
        grid.addWidget(QtWidgets.QLabel("Group by"), 1, 2)
        grid.addWidget(self.gb_b, 1, 3)

        # Sum columns
        grid.addWidget(QtWidgets.QLabel("Sum columns"), 2, 0)
        grid.addWidget(self.sum_a, 2, 1)
        grid.addWidget(QtWidgets.QLabel("Sum columns"), 2, 2)
        grid.addWidget(self.sum_b, 2, 3)

        # Where
        grid.addWidget(QtWidgets.QLabel("Where"), 3, 0)
        w_a = QtWidgets.QHBoxLayout()
        w_a.addWidget(self.where_col_a)
        w_a.addWidget(self.where_op_a)
        w_a.addWidget(self.where_val_a, 1)
        grid.addLayout(w_a, 3, 1)

        grid.addWidget(QtWidgets.QLabel("Where"), 3, 2)
        w_b = QtWidgets.QHBoxLayout()
        w_b.addWidget(self.where_col_b)
        w_b.addWidget(self.where_op_b)
        w_b.addWidget(self.where_val_b, 1)
        grid.addLayout(w_b, 3, 3)

        # Hint
        hint = QtWidgets.QLabel("Tip: ถ้าไม่เลือก SUM columns ระบบจะพยายามเดาคอลัมน์ตัวเลขให้ใน CompareWindow")
        hint.setStyleSheet("color:#6b7280;")
        grid.addWidget(hint, 4, 0, 1, 4)

        # Buttons
        btn_box = QtWidgets.QDialogButtonBox()
        self.btn_ok     = btn_box.addButton("OK", QtWidgets.QDialogButtonBox.AcceptRole)
        self.btn_apply  = btn_box.addButton("Apply & Close", QtWidgets.QDialogButtonBox.AcceptRole)
        self.btn_cancel = btn_box.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        for b in (self.btn_ok, self.btn_apply, self.btn_cancel):
            b.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        grid.addWidget(btn_box, 5, 0, 1, 4)

        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        # preload group-by ตาม keys ที่ส่งมา (ถ้ามี)
        self._preselect_gb(keys_a, keys_b)

    # ---------------- helpers ----------------
    def _preselect_gb(self, keys_a: List[str], keys_b: List[str]):
        """ตั้ง group-by เริ่มต้นตามจำนวน keys ที่มี"""
        def guess(keys: List[str]) -> str:
            cnt = len([k for k in keys if k])
            if cnt >= 3: return "Key3"
            if cnt == 2: return "Key2"
            if cnt == 1: return "Key1"
            return "None"
        self.gb_a.setCurrentText(guess(keys_a))
        self.gb_b.setCurrentText(guess(keys_b))

    def _collect_sum(self, lw: QtWidgets.QListWidget) -> List[str]:
        return [lw.item(i).text() for i in range(lw.count()) if lw.item(i).isSelected()]

    # ---------------- public ----------------
    def get_options(self) -> Dict[str, Dict]:
        opts = {
            'a': {
                'gb': self.gb_a.currentText(),
                'sum': self._collect_sum(self.sum_a),
                'where': (self.where_col_a.currentText().strip(),
                          self.where_op_a.currentText().strip(),
                          self.where_val_a.text().strip())
            },
            'b': {
                'gb': self.gb_b.currentText(),
                'sum': self._collect_sum(self.sum_b),
                'where': (self.where_col_b.currentText().strip(),
                          self.where_op_b.currentText().strip(),
                          self.where_val_b.text().strip())
            }
        }
        return opts
