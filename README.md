# 🧮 Reconcile GUI – Enrich • Filter • Aggregate • Compare (PyQt5)

**Reconcile GUI** คือเครื่องมือที่ใช้สำหรับ “เปรียบเทียบข้อมูลสองฝั่ง (A/B)”  
โดยมีแนวคิดหลักคือ **Enrich → Filter → Aggregate → Compare → Export**  
ออกแบบมาเพื่อช่วยทีม QA / Accounting / Data ตรวจสอบความถูกต้องของไฟล์รายงาน  
รองรับทั้ง `.csv`, `.tsv`, `.txt`, `.xlsx`, `.xls`  

---

## 🧠 Concept Overview

### Main Flow
1. **Load File A/B**
   - รองรับ CSV/TSV/TXT/XLS/XLSX
   - Auto delimiter, Auto encoding
2. **Set Keys (1–3)**  
   ตั้งคีย์จับคู่ระหว่างไฟล์ A ↔ B
3. **Filter**  
   กรองข้อมูลได้สูงสุด 3 เงื่อนไขต่อฝั่ง (เช่น `SUPPLIER = 60010`, `QTY > 0`)
4. **Aggregate (optional)**  
   Group/Sum ต่อฝั่งก่อนเปรียบเทียบ
5. **Compare**  
   แสดงผล Only in A / Only in B / Both / Duplicate / Summary (Coverage %, Jaccard %)
6. **Export**  
   บันทึกผลเป็น HTML/CSV/Excel

---

## 🏗️ Folder & File Structure

```
reconcile_gui/
├─ main.py               # Entrypoint / Router / Plugin Loader
├─ theme.py              # Global Theme (Fusion + Soft QSS)
├─ edit_data_view.py     # Edit Data tools (Trim, Delete, Pad, Group/Sum, Calc)
├─ compare_view.py       # Compare Wizard (2-page: Setup ↔ Results)
├─ file_block.py         # Loader + Filter widget (ใช้ใน Compare)
├─ sum_dialog.py         # Aggregate dialog (เรียกจาก Compare)
├─ lookup_value_gui.py   # Lookup mapping tool (Target ↔ Master)
├─ plugins.json          # Plugin registry (autoload when restart)
└─ docs/
   ├─ ReconcileGuiConcept.pdf
   └─ Reconcile Gui – Menu Split Plan.pdf
```

---

## ⚙️ Features Summary

### 🧩 Main Menu (`main.py`)
- หน้า Home มีปุ่ม:
  - **Edit Data** → เปิดหน้าแก้ไข/ปรับข้อมูล (Trim/Delete/Pad/Group/Sum/Calc)
  - **Compare Files** → เปิด Compare Wizard
  - **Lookup Values** → เปิด Lookup Tool
  - **Load Feature (.py)** → โหลดปลั๊กอินเพิ่มได้แบบ runtime
- ระบบปลั๊กอินเก็บไว้ใน `plugins.json` (relative path เมื่ออยู่ในโฟลเดอร์แอป)
- Autoload plugin ทุกครั้งที่เปิดโปรแกรม

---

### ✂️ Edit Data (`edit_data_view.py`)
**รวมเครื่องมือจัดการข้อมูลในหน้าเดียว**
| Tab | Description |
|------|-------------|
| **Trim** | ตัดข้อความซ้าย/ขวา ตามจำนวนตัวอักษร |
| **Delete** | ลบแถวตาม pattern (`%wildcard%`, equals/contains) |
| **Pad** | เติมอักขระซ้าย/ขวาให้ครบความยาว |
| **Group / Sum** | Group only / Sum only / Group+Sum (เลือกหลายคอลัมน์ได้) |
| **Calculation** | สร้างคอลัมน์ใหม่จากสูตร (+, -, *, /, //, %) |
| **Lookup (optional)** | ฝัง Lookup Tool ถ้ามี lookup_value_gui.py |

- Export ได้ทั้ง CSV และ Excel
- Preview top 5,000 rows
- มีสถานะ “Processing… / Done ✅” และ busy cursor ระหว่างทำงาน

---

### ⚖️ Compare (`compare_view.py`)
**Compare Wizard 2 หน้าหลัก:**
1. **Setup Page**
   - โหลดไฟล์ A/B ผ่าน `FileBlock`
   - ตั้งคีย์ 1–3, Filter, Aggregate (ผ่าน `SumDialog`)
2. **Results Page**
   - แสดงผล Coverage, Duplicates, Summary (HTML-style)
   - Export ผลออกเป็น Excel หรือ CSV

**การคำนวณสำคัญ**
- Coverage A↔B (%)
- Jaccard Match (%)
- Status: ✅ MATCHED / ⚠️ PARTIAL / ❌ NO MATCH

---

### 📚 Lookup (`lookup_value_gui.py`)
**Mapping Tool (Target ↔ Master file)**
- เลือกไฟล์ Target / Master
- ตั้งคีย์แมป (target_key ↔ master_key)
- เลือกคอลัมน์ value จาก master
- Merge และ export เป็น Excel ได้

---

### 🎨 Theme (`theme.py`)
**Fusion Style (Light) + Thai font friendly**
- HiDPI scaling เปิดอัตโนมัติ
- Soft QSS: สีขาว เทา ฟ้าอ่อน อ่านง่าย
- Helper:
  ```python
  apply_theme(app)
  set_table_defaults(view)
  polish_widget_tree(root)
  ```

---

## 🚀 How to Run

### 1️⃣ เตรียม Environment
```bash
pip install PyQt5 pandas openpyxl
```

### 2️⃣ รันโปรแกรม
```bash
python main.py
```

(แนะนำให้รันด้วย Python 3.9+)

### 3️⃣ สร้างเป็น .exe (optional)
```bash
pyinstaller --onefile --windowed main.py ^
  --name ReconcileGUI ^
  --add-data "edit_data_view.py;." ^
  --add-data "compare_view.py;." ^
  --add-data "file_block.py;." ^
  --add-data "sum_dialog.py;." ^
  --hidden-import PyQt5 --hidden-import pandas
```

ไฟล์ `.exe` จะอยู่ใน `dist/ReconcileGUI.exe`

---

## 🔌 Plugins System

### โหลดฟีเจอร์ใหม่ (.py)
1. ไปที่หน้า Home → คลิก **“Load Feature (.py)”**
2. เลือกไฟล์ Python ที่มี QWidget subclass เช่น `LookupWindow` หรือ `MainFeature`
3. ระบบจะเพิ่มปุ่มใหม่ในหน้า Home ให้อัตโนมัติ
4. รายการปลั๊กอินจะถูกเก็บใน `plugins.json`

**ตัวอย่างโครงปลั๊กอิน**
```python
from PyQt5 import QtWidgets

class MyFeature(QtWidgets.QWidget):
    WINDOW_TITLE = "My Custom Feature"
    def __init__(self):
        super().__init__()
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().addWidget(QtWidgets.QLabel("Hello Plugin"))
```

---

## 🧰 Developer Notes

- โครงสร้างรองรับ HiDPI / Windows / macOS
- ใช้ **pandas** สำหรับ data manipulation
- UI ทุกหน้าใช้ QVBoxLayout/QHBoxLayout (ไม่มี Qt Designer)
- Preview จำกัดที่ 5,000 rows เพื่อความเร็ว
- Theme และ font ปรับอัตโนมัติให้เหมาะกับภาษาไทย

---

## 📈 Backlog / Next Steps

| Feature | Status | Plan |
|----------|--------|------|
| Enrich step (expression builder) | ⏳ | เพิ่มใน Calculation tab |
| Multi-file join (3+ files) | ⏳ | เพิ่มใน Compare |
| Export preset templates | ⏳ | JSON config per use-case |
| Batch mode / CLI run | ⏳ | เพิ่ม command line interface |
| Report Builder (logo, header) | ⏳ | Export HTML+PDF reports |

---

## 👥 Contributors

| Name | Role |
|------|------|
| Control System | Lead Developer / QA Reconcile |
| ChatGPT (GPT-5) | Co-developer & Documentation Assistant |

---

## 📄 License

MIT License © 2025 Control System  
Free to use and modify for internal QA automation projects.
