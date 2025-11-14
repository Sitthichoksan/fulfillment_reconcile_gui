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
        
        # Check for duplicate keys (causes data explosion)
        target_dup = self.target_df[target_key].duplicated().sum()
        master_dup = self.master_df[master_key].duplicated().sum()
        
        join_type = "left"
        if target_dup > 0 or master_dup > 0:
            msg = f"⚠️ Duplicate keys detected:\n"
            if target_dup > 0:
                msg += f"  • Target: {target_dup} duplicates\n"
            if master_dup > 0:
                msg += f"  • Master: {master_dup} duplicates\n"
            msg += f"\nUsing INNER join (safer) instead of LEFT join.\nContinue?"
            reply = QMessageBox.warning(self, "Duplicate Keys", msg, QMessageBox.Ok | QMessageBox.Cancel)
            if reply != QMessageBox.Ok:
                return
            join_type = "inner"
        
        # provide progress updates: chunk merge with memory-safe concat
        try:
            chunk_size = 5000  # Reduced from 10000 for safety
            num_chunks = (len(self.target_df) + chunk_size - 1) // chunk_size
            self._start_progress("Lookup (streaming)", total_steps=num_chunks + 2)

            # Prepare data
            target_renamed = self.target_df.add_suffix("_target")
            master_subset = self.master_df[[master_key, master_value]].copy()
            master_subset = master_subset.rename(
                columns={
                    master_key: f"{master_key}_master",
                    master_value: f"{master_value}_master"
                }
            )
            self._update_progress(step_inc=1, note="prepared")

            # Merge in chunks and store only preview (first 1000 rows for display)
            preview_rows = []
            total_rows = 0
            
            for chunk_idx in range(0, len(target_renamed), chunk_size):
                chunk = target_renamed.iloc[chunk_idx:chunk_idx+chunk_size]
                merged_chunk = pd.merge(
                    chunk,
                    master_subset,
                    how=join_type,
                    left_on=f"{target_key}_target",
                    right_on=f"{master_key}_master"
                )
                
                # Add result column
                merged_chunk[result_col] = merged_chunk[f"{master_value}_master"]
                
                # Keep first 1000 rows for preview display
                if len(preview_rows) < 1000:
                    preview_rows.extend(merged_chunk.head(1000 - len(preview_rows)).values.tolist())
                
                total_rows += len(merged_chunk)
                self._update_progress(step_inc=1, note=f"chunk {(chunk_idx // chunk_size) + 1}/{num_chunks}")
                QtWidgets.QApplication.processEvents()
            
            # Create merged_df with just preview for display
            if preview_rows and len(target_renamed.columns) > 0:
                # Get column names from first chunk
                chunk = target_renamed.iloc[0:chunk_size]
                merged_chunk = pd.merge(
                    chunk,
                    master_subset,
                    how=join_type,
                    left_on=f"{target_key}_target",
                    right_on=f"{master_key}_master"
                )
                merged_chunk[result_col] = merged_chunk[f"{master_value}_master"]
                cols = merged_chunk.columns.tolist()
                
                self.merged_df = pd.DataFrame(preview_rows, columns=cols)
            else:
                self.merged_df = pd.DataFrame()
            
            self._update_progress(step_inc=1, note="prepared preview")
            
            # Show preview
            self.show_table(self.merged_df.head(1000) if len(self.merged_df) > 1000 else self.merged_df)
            
            self._finish_progress("Lookup เสร็จแล้ว")

            QMessageBox.information(
                self,
                "Done",
                f"✅ Lookup complete!\n"
                f"Total rows processed: {total_rows:,}\n"
                f"Showing first {len(self.merged_df)} rows in preview\n"
                f"(Full result will be saved on export)"
            )

        except MemoryError as e:
            try:
                self._finish_progress("Lookup ล้มเหลว (ไม่มีหน่วยความจำ)")
            except Exception:
                pass
            QMessageBox.critical(
                self, 
                "Memory Error", 
                f"Out of memory even with streaming.\n\n"
                f"Master file or key duplicates are too large.\n"
                f"Try filtering Master file first.\n\n{str(e)}"
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
        if self.target_df is None or self.master_df is None:
            QMessageBox.warning(self, "No Data", "Please run lookup first.")
            return
        
        path, _ = QFileDialog.getSaveFileName(self, "Export File", "", "Excel Files (*.xlsx);;CSV Files (*.csv)")
        if not path:
            return
        
        # Get current settings from UI
        target_key = self.target_key_combo.currentText()
        master_key = self.master_key_combo.currentText()
        master_value = self.master_value_combo.currentText()
        result_col = self.result_name.text().strip() or f"{master_value}_mapped"
        
        # Determine join type from last lookup
        target_dup = self.target_df[target_key].duplicated().sum()
        master_dup = self.master_df[master_key].duplicated().sum()
        join_type = "inner" if (target_dup > 0 or master_dup > 0) else "left"
        
        try:
            chunk_size = 5000
            num_chunks = (len(self.target_df) + chunk_size - 1) // chunk_size
            self._start_progress("Exporting (streaming)", total_steps=num_chunks + 1)
            
            target_renamed = self.target_df.add_suffix("_target")
            master_subset = self.master_df[[master_key, master_value]].copy()
            master_subset = master_subset.rename(
                columns={
                    master_key: f"{master_key}_master",
                    master_value: f"{master_value}_master"
                }
            )
            
            is_first_chunk = True
            is_xlsx = path.lower().endswith('.xlsx')
            
            if is_xlsx:
                writer = pd.ExcelWriter(path, engine='openpyxl')
            else:
                writer = None
            
            try:
                for chunk_idx in range(0, len(target_renamed), chunk_size):
                    chunk = target_renamed.iloc[chunk_idx:chunk_idx+chunk_size]
                    merged_chunk = pd.merge(
                        chunk,
                        master_subset,
                        how=join_type,
                        left_on=f"{target_key}_target",
                        right_on=f"{master_key}_master"
                    )
                    
                    # Add result column
                    merged_chunk[result_col] = merged_chunk[f"{master_value}_master"]
                    
                    # Write to file
                    if is_xlsx:
                        merged_chunk.to_excel(
                            writer,
                            sheet_name='Result',
                            index=False,
                            startrow=0 if is_first_chunk else writer.sheets['Result'].max_row
                        )
                    else:
                        # CSV mode: append
                        if is_first_chunk:
                            merged_chunk.to_csv(path, index=False, mode='w')
                        else:
                            merged_chunk.to_csv(path, index=False, mode='a', header=False)
                    
                    is_first_chunk = False
                    self._update_progress(step_inc=1, note=f"chunk {(chunk_idx // chunk_size) + 1}/{num_chunks}")
                    QtWidgets.QApplication.processEvents()
            finally:
                if is_xlsx and writer:
                    writer.close()
            
            self._update_progress(step_inc=1, note="finalized")
            self._finish_progress("Export เสร็จแล้ว")
            QMessageBox.information(
                self,
                "Exported",
                f"💾 Exported successfully to:\n{path}\n\n"
                f"Total rows: {len(self.target_df):,}\n"
                f"Processed in {num_chunks} chunks"
            )
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
