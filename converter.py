import sys
import pandas as pd
from PyQt5 import QtWidgets
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
    QTableWidget, QTableWidgetItem, QPushButton, QLineEdit, QLabel,
    QMessageBox, QComboBox
)

# ---------- Core Conversion ----------
def try_read_csv(file_path, nrows_preview=100):
    encodings = ['utf-8', 'windows-874', 'tis-620']
    for enc in encodings:
        try:
            df_preview = pd.read_csv(file_path, encoding=enc, nrows=nrows_preview)
            df_full = pd.read_csv(file_path, encoding=enc)
            print(f"✅ Loaded with encoding: {enc}")
            return df_preview, df_full, enc
        except Exception as e:
            print(f"❌ {enc}: {e}")
    raise ValueError("ไม่สามารถอ่านไฟล์นี้ได้ด้วย encoding ทั่วไป")

def convert_text_thai(series):
    def _convert(val):
        try:
            return val.encode('latin1').decode('tis-620')
        except Exception:
            return val
    return series.astype(str).map(_convert)

def convert_text_generic(series, fmt_type):
    series = series.astype(str)
    if fmt_type == "Thai Encoding Fix (TIS-620 → UTF-8)":
        return convert_text_thai(series)
    elif fmt_type == "Uppercase":
        return series.str.upper()
    elif fmt_type == "Lowercase":
        return series.str.lower()
    elif fmt_type == "Trim Whitespace":
        return series.str.strip()
    elif fmt_type == "Capitalize Words":
        return series.str.title()
    else:
        return series

# ---------- GUI ----------
class ThaiEncodingConverter(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🇹🇭 Thai Encoding Converter (v6 - Single Table)")
        self.resize(950, 600)

        main_layout = QVBoxLayout(self)

        # Row 1: File & Load
        file_layout = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("เลือกไฟล์ CSV ที่ต้องการแปลง...")
        self.btn_browse = QPushButton("Browse File")
        self.btn_load = QPushButton("Load")
        self.btn_browse.clicked.connect(self.browse_file)
        self.btn_load.clicked.connect(self.load_file)
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(self.btn_browse)
        file_layout.addWidget(self.btn_load)
        main_layout.addLayout(file_layout)

        # Row 2: Column + Format + Preview + Apply
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("เลือก Column:"))
        self.column_dropdown = QComboBox()
        control_layout.addWidget(self.column_dropdown)

        control_layout.addWidget(QLabel("Format Type:"))
        self.format_dropdown = QComboBox()
        self.format_dropdown.addItems([
            "Thai Encoding Fix (TIS-620 → UTF-8)",
            "Uppercase",
            "Lowercase",
            "Trim Whitespace",
            "Capitalize Words"
        ])
        control_layout.addWidget(self.format_dropdown)

        self.btn_preview = QPushButton("Preview")
        self.btn_preview.clicked.connect(self.preview_conversion)
        control_layout.addWidget(self.btn_preview)

        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self.apply_conversion)
        control_layout.addWidget(self.btn_apply)

        main_layout.addLayout(control_layout)

        # Single Table Display
        self.table = QTableWidget()
        main_layout.addWidget(self.table)

        # Export Button
        self.btn_export = QPushButton("💾 Export (.csv / .xlsx)")
        self.btn_export.clicked.connect(self.export_file)
        main_layout.addWidget(self.btn_export)

        # Data storage
        self.df_full = None
        self.df_preview = None
        self.encoding_used = None
        self.file_loaded = False
        self.last_selected_col = None
        self.last_selected_format = None

    # ---------- Functions ----------
    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์ CSV", "", "CSV Files (*.csv)")
        if path:
            self.file_path.setText(path)

    def load_file(self):
        path = self.file_path.text()
        if not path:
            QMessageBox.warning(self, "Error", "กรุณาเลือกไฟล์ก่อน")
            return
        try:
            self.df_preview, self.df_full, self.encoding_used = try_read_csv(path)
            self.file_loaded = True
            self.column_dropdown.clear()
            self.column_dropdown.addItems(self.df_full.columns)
            self.show_table(self.df_preview)
            QMessageBox.information(self, "สำเร็จ", "โหลดข้อมูลสำเร็จ (แสดง 100 แถวแรก)")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"ไม่สามารถโหลดไฟล์ได้:\\n{e}")

    def show_table(self, df):
        self.table.clear()
        self.table.setColumnCount(len(df.columns))
        self.table.setRowCount(len(df))
        self.table.setHorizontalHeaderLabels(df.columns)
        for i in range(len(df)):
            for j, col in enumerate(df.columns):
                self.table.setItem(i, j, QTableWidgetItem(str(df.iloc[i, j])))
        self.table.resizeColumnsToContents()

    def preview_conversion(self):
        if not self.file_loaded or self.df_full is None:
            QMessageBox.warning(self, "Error", "กรุณาโหลดไฟล์ก่อน")
            return

        col = self.column_dropdown.currentText()
        fmt = self.format_dropdown.currentText()
        if not col:
            QMessageBox.warning(self, "Error", "กรุณาเลือกคอลัมน์")
            return

        self.last_selected_col = col
        self.last_selected_format = fmt

        temp_df = self.df_full.head(100).copy()
        temp_df[f"{col}_before"] = temp_df[col]
        temp_df[col] = convert_text_generic(temp_df[col], fmt)
        self.show_table(temp_df[[f"{col}_before", col]])
        QMessageBox.information(self, "Preview", f"Preview การแปลงคอลัมน์ '{col}' ด้วย Format '{fmt}'")

    def apply_conversion(self):
        if self.df_full is None or not self.last_selected_col:
            QMessageBox.warning(self, "Error", "กรุณา Preview ก่อน Apply")
            return

        col = self.last_selected_col
        fmt = self.last_selected_format

        msg = QMessageBox.question(self, "ยืนยันการแปลง",
                                   f"ต้องการ Apply การแปลงคอลัมน์ '{col}' ด้วย Format '{fmt}' หรือไม่?",
                                   QMessageBox.Yes | QMessageBox.No)
        if msg != QMessageBox.Yes:
            return

        self.df_full[f"{col}_before"] = self.df_full[col]
        self.df_full[col] = convert_text_generic(self.df_full[col], fmt)
        self.show_table(self.df_full.head(100))
        QMessageBox.information(self, "Apply สำเร็จ", f"Apply การแปลงคอลัมน์ '{col}' สำเร็จ")

    def export_file(self):
        if not self.file_loaded or self.df_full is None:
            QMessageBox.warning(self, "Error", "ยังไม่มีข้อมูลที่จะแปลงหรือบันทึก")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export File", "converted_output", "CSV Files (*.csv);;Excel Files (*.xlsx)"
        )
        if not path:
            return

        try:
            if path.endswith(".xlsx"):
                self.df_full.to_excel(path, index=False)
            else:
                self.df_full.to_csv(path, index=False, encoding='utf-8-sig')
            QMessageBox.information(self, "สำเร็จ", f"Export เรียบร้อยแล้ว:\\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"ไม่สามารถ export ได้:\\n{e}")

# ---------- Main ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ThaiEncodingConverter()
    window.show()
    sys.exit(app.exec_())
