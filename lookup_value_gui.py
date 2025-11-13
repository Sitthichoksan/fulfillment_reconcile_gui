import sys
import time
import pandas as pd
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFileDialog, QMessageBox


class LookupApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Reconcile – Lookup Value (PyQt5)")
        self.resize(900, 600)
        self.target_df = None
        self.master_df = None
        self.merged_df = None

        layout = QtWidgets.QVBoxLayout()

        # File selection
        file_layout = QtWidgets.QHBoxLayout()
        self.target_path = QtWidgets.QLineEdit()
        self.master_path = QtWidgets.QLineEdit()
        self.target_btn = QtWidgets.QPushButton("Browse Target")
        self.master_btn = QtWidgets.QPushButton("Browse Master")
        self.target_btn.clicked.connect(lambda: self.load_file("target"))
        self.master_btn.clicked.connect(lambda: self.load_file("master"))
        file_layout.addWidget(QtWidgets.QLabel("Target File:"))
        file_layout.addWidget(self.target_path)
        file_layout.addWidget(self.target_btn)
        file_layout.addWidget(QtWidgets.QLabel("Master File:"))
        file_layout.addWidget(self.master_path)
        file_layout.addWidget(self.master_btn)

        # Lookup form
        form = QtWidgets.QFormLayout()
        self.target_key_combo = QtWidgets.QComboBox()
        self.master_key_combo = QtWidgets.QComboBox()
        self.master_value_combo = QtWidgets.QComboBox()
        self.result_name = QtWidgets.QLineEdit()
        self.result_name.setPlaceholderText("Result column name (e.g. LOOKUP_RESULT)")

        form.addRow("Target Key Column:", self.target_key_combo)
        form.addRow("Master Key Column:", self.master_key_combo)
        form.addRow("Value to Lookup (from master):", self.master_value_combo)
        form.addRow("Result Column Name:", self.result_name)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.lookup_btn = QtWidgets.QPushButton("🔍 Lookup")
        self.lookup_btn.clicked.connect(self.lookup_data)
        self.export_btn = QtWidgets.QPushButton("💾 Export")
        self.export_btn.clicked.connect(self.export_data)
        btn_layout.addStretch()
        btn_layout.addWidget(self.lookup_btn)
        btn_layout.addWidget(self.export_btn)

        # Output table
        self.table = QtWidgets.QTableWidget()

        layout.addLayout(file_layout)
        layout.addLayout(form)
        layout.addLayout(btn_layout)
        layout.addWidget(QtWidgets.QLabel("📊 Preview:"))
        layout.addWidget(self.table)

        # status / progress controls
        self.status_label = QtWidgets.QLabel("Ready")
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress)

        self.setLayout(layout)

        # progress internals
        self._prog_task = None
        self._prog_total = 0
        self._prog_step = 0
        self._prog_t0 = 0.0

    # ---------- progress helpers (Thai) ----------
    def _start_progress(self, task: str, total_steps: int = 100):
        try:
            self._prog_task = task
            self._prog_total = max(1, int(total_steps))
            self._prog_step = 0
            self._prog_t0 = time.time()
            self.status_label.setText(f"กำลังทำงาน: {task} 0%")
            self.progress.setValue(0)
            self.progress.setVisible(True)
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

    def _update_progress(self, step_inc: int = 1, note: str = ""):
        try:
            if not self._prog_task:
                return
            self._prog_step = min(self._prog_total, self._prog_step + int(step_inc))
            pct = int((self._prog_step / self._prog_total) * 100)
            note_text = f" • {note}" if note else ""
            self.status_label.setText(f"กำลังทำงาน: {self._prog_task} {pct}%{note_text}")
            self.progress.setValue(pct)
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

    def _finish_progress(self, done_text: str = "เสร็จแล้ว"):
        try:
            dt = time.time() - (self._prog_t0 or time.time())
            self.status_label.setText(f"{done_text} ({dt:.2f}s)")
            self.progress.setValue(100)
            QtWidgets.QApplication.processEvents()
            self.progress.setVisible(False)
            # reset
            self._prog_task = None
            self._prog_total = 0
            self._prog_step = 0
            self._prog_t0 = 0.0
        except Exception:
            pass

    def load_file(self, file_type):
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "Excel/CSV (*.xlsx *.csv)")
        if not path:
            return
        # show progress for loading
        try:
            self._start_progress(f"โหลด {file_type}", total_steps=1)
            df = pd.read_excel(path) if path.endswith(".xlsx") else pd.read_csv(path)
            if file_type == "target":
                self.target_df = df
                self.target_path.setText(path)
                self.target_key_combo.clear()
                self.target_key_combo.addItems(df.columns)
            else:
                self.master_df = df
                self.master_path.setText(path)
                self.master_key_combo.clear()
                self.master_key_combo.addItems(df.columns)
                self.master_value_combo.clear()
                self.master_value_combo.addItems(df.columns)
            # update progress and finish
            self._update_progress(step_inc=1, note="loaded")
            self._finish_progress("โหลดเรียบร้อย")
            QMessageBox.information(self, "Loaded", f"✅ Loaded {file_type} file successfully")
        except Exception as e:
            # finish with failure
            try:
                self._finish_progress("โหลดล้มเหลว")
            except Exception:
                pass
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")

    def lookup_data(self):
        if self.target_df is None or self.master_df is None:
            QMessageBox.warning(self, "Missing File", "Please load both Target and Master files first.")
            return

        target_key = self.target_key_combo.currentText()
        master_key = self.master_key_combo.currentText()
        master_value = self.master_value_combo.currentText()
        result_col = self.result_name.text().strip() or f"{master_value}_mapped"
        # provide progress updates: prepare -> merge -> done
        try:
            self._start_progress("Lookup", total_steps=3)

            # เพิ่ม suffix เพื่อบอกว่ามาจากไฟล์ไหน (step 1)
            target_renamed = self.target_df.add_suffix("_target")
            master_subset = self.master_df[[master_key, master_value]].copy()
            master_subset = master_subset.rename(
                columns={
                    master_key: f"{master_key}_master",
                    master_value: f"{master_value}_master"
                }
            )
            self._update_progress(step_inc=1, note="prepared")

            # merge โดยใช้ key target/master (step 2)
            merged = pd.merge(
                target_renamed,
                master_subset,
                how="left",
                left_on=f"{target_key}_target",
                right_on=f"{master_key}_master"
            )
            self._update_progress(step_inc=1, note="merged")

            # เพิ่ม column เก็บค่า lookup (master_value) (step 3)
            merged[result_col] = merged[f"{master_value}_master"]

            self.merged_df = merged
            self.show_table(merged)

            self._update_progress(step_inc=1, note="displayed")
            self._finish_progress("Lookup เสร็จแล้ว")

            QMessageBox.information(
                self,
                "Done",
                f"✅ Lookup complete! Now showing columns with '_target' and '_master' suffixes"
            )

        except Exception as e:
            try:
                self._finish_progress("Lookup ล้มเหลว")
            except Exception:
                pass
            QMessageBox.critical(self, "Error", str(e))

    def show_table(self, df):
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels(df.columns)
        for i, row in enumerate(df.itertuples(index=False)):
            for j, val in enumerate(row):
                self.table.setItem(i, j, QtWidgets.QTableWidgetItem(str(val)))

    def export_data(self):
        if self.merged_df is None:
            QMessageBox.warning(self, "No Data", "Please run lookup first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export File", "", "Excel Files (*.xlsx)")
        if not path:
            return
        try:
            self._start_progress("Exporting", total_steps=1)
            self.merged_df.to_excel(path, index=False)
            self._update_progress(step_inc=1, note="saved")
            self._finish_progress("Export เสร็จแล้ว")
            QMessageBox.information(self, "Exported", f"💾 Exported successfully to:\n{path}")
        except Exception as e:
            try:
                self._finish_progress("Export ล้มเหลว")
            except Exception:
                pass
            QMessageBox.critical(self, "Error", f"Export failed: {e}")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = LookupApp()
    window.show()
    sys.exit(app.exec_())
