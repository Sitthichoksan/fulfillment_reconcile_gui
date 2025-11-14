import sys
import pandas as pd
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import QFileDialog, QMessageBox


class LookupApp(QtWidgets.QWidget): #comment
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
        self.setLayout(layout)

    def load_file(self, file_type):
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "Excel/CSV (*.xlsx *.csv)")
        if not path:
            return
        try:
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
            QMessageBox.information(self, "Loaded", f"✅ Loaded {file_type} file successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")

    def lookup_data(self):
        if self.target_df is None or self.master_df is None:
            QMessageBox.warning(self, "Missing File", "Please load both Target and Master files first.")
            return

        target_key = self.target_key_combo.currentText()
        master_key = self.master_key_combo.currentText()
        master_value = self.master_value_combo.currentText()
        result_col = self.result_name.text().strip() or f"{master_value}_mapped"

        try:
            # เพิ่ม suffix เพื่อบอกว่ามาจากไฟล์ไหน
            target_renamed = self.target_df.add_suffix("_target")
            master_subset = self.master_df[[master_key, master_value]].copy()
            master_subset = master_subset.rename(
                columns={
                    master_key: f"{master_key}_master",
                    master_value: f"{master_value}_master"
                }
            )

            # merge โดยใช้ key target/master
            merged = pd.merge(
                target_renamed,
                master_subset,
                how="left",
                left_on=f"{target_key}_target",
                right_on=f"{master_key}_master"
            )

            # เพิ่ม column เก็บค่า lookup (master_value)
            merged[result_col] = merged[f"{master_value}_master"]

            self.merged_df = merged
            self.show_table(merged)

            QMessageBox.information(
                self,
                "Done",
                f"✅ Lookup complete! Now showing columns with '_target' and '_master' suffixes"
            )

        except Exception as e:
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
            self.merged_df.to_excel(path, index=False)
            QMessageBox.information(self, "Exported", f"💾 Exported successfully to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed: {e}")


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = LookupApp()
    window.show()
    sys.exit(app.exec_())
