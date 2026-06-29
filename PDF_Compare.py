import os
import tempfile
import shutil
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

from tkinterdnd2 import TkinterDnD, DND_FILES

import subprocess
import platform

import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image, ImageTk
import sys

def resource_path(relative_path):
    """ Resolves resource file paths in both dev and PyInstaller environments """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ==========================================
# 1. File Conversion & Image Comparison Logic
# ==========================================
def pdf_page_to_image(doc, page_num, output_png):
    page = doc.load_page(page_num)
    rect = page.rect
    zoom = 4.0  # Ultra high resolution (4x zoom)
    mat = fitz.Matrix(zoom, zoom)
    
    pix = page.get_pixmap(matrix=mat, clip=rect)
    pix.save(output_png)

def run_image_diff(img_path1, img_path2, output_png, sensitivity=5):
    img1 = cv2.imread(img_path1) if img_path1 and os.path.exists(img_path1) else None
    img2 = cv2.imread(img_path2) if img_path2 and os.path.exists(img_path2) else None

    if img1 is None and img2 is not None:
        img1 = np.ones_like(img2) * 255
    elif img2 is None and img1 is not None:
        img2 = np.ones_like(img1) * 255
    elif img1 is None and img2 is None:
        return 0

    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    # Gaussian blur based on sensitivity level
    if sensitivity == 10:
        ksize = 0
    elif sensitivity >= 7:
        ksize = 3
    else:
        ksize = 5
        
    if ksize > 0:
        gray1_blur = cv2.GaussianBlur(gray1, (ksize, ksize), 0)
        gray2_blur = cv2.GaussianBlur(gray2, (ksize, ksize), 0)
    else:
        gray1_blur = gray1
        gray2_blur = gray2

    # Calculate absolute pixel difference between two images
    diff = cv2.absdiff(gray1_blur, gray2_blur)
    
    # Threshold adjustment based on sensitivity
    thresh_val = max(5, 55 - (sensitivity * 5))
    _, change_mask = cv2.threshold(diff, thresh_val, 255, cv2.THRESH_BINARY)

    # Dilate to merge nearby changed regions
    grouping_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    dilated_for_contours = cv2.dilate(change_mask, grouping_kernel, iterations=1)

    # Find contours before applying color highlights
    contours, _ = cv2.findContours(dilated_for_contours, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    check_count = 0
    valid_contours = []
    
    if sensitivity == 10:
        min_area = 100  
        min_wh = 1
    else:
        min_area = max(200, 1000 - (sensitivity * 80))
        min_wh = max(2, 15 - sensitivity)

    # Count significant differences and store their bounding boxes
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
            
        x, y, w, h = cv2.boundingRect(contour)
        if w < min_wh or h < min_wh:
            continue

        check_count += 1
        valid_contours.append((x, y, w, h))

    # ----------------------------------------------------
    # If no differences found, save the revised image as-is and exit
    # ----------------------------------------------------
    if check_count == 0:
        cv2.imwrite(output_png, img2)
        return 0

    # ----------------------------------------------------
    # Only runs when 1 or more differences are detected
    # ----------------------------------------------------
    significant_mask = dilated_for_contours > 0 
    deleted_mask = (cv2.subtract(gray2_blur, gray1_blur) > thresh_val)
    added_mask = (cv2.subtract(gray1_blur, gray2_blur) > thresh_val)

    # Use original image as grayscale background
    combined = cv2.cvtColor(gray1, cv2.COLOR_GRAY2BGR)

    # Color-code deleted vs. added pixels
    combined[deleted_mask & significant_mask] = (255, 140, 80)  # Deleted pixels (original)
    combined[added_mask & significant_mask]   = (120, 20, 255)  # Added pixels (revised)

    # Draw check marks on detected difference regions
    for (x, y, w, h) in valid_contours:
        chk_x = max(10, x - 5)
        chk_y = max(10, y - 5)
        size = 20
        pt1 = (chk_x, chk_y + size // 2)
        pt2 = (chk_x + size // 3, chk_y + size)
        pt3 = (chk_x + size, chk_y)

        cv2.line(combined, pt1, pt2, (0, 0, 255), 4, cv2.LINE_AA)
        cv2.line(combined, pt2, pt3, (0, 0, 255), 4, cv2.LINE_AA)

    cv2.imwrite(output_png, combined)
    return check_count

def convert_image_to_pdf(image_path, pdf_path):
    try:
        img = Image.open(image_path)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(pdf_path, 'PDF', dpi=(300, 300), quality=95)
    except Exception as e:
        print(f"PDF conversion error: {e}")

# ==========================================
# 2. GUI Application
# ==========================================
class PDFCompareApp:
    def __init__(self, root):
        self.root = root
        # Application window icon
        icon_path = resource_path("PDF_Compare_Icon.ico")
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)
        self.root.title("PDF Comparison Tool")
        self.root.geometry("640x420")
        self.root.resizable(False, False)
        
        self.bg_color = "#f8fafc"
        self.root.configure(bg=self.bg_color)
        
        lbl_info = tk.Label(
            root, 
            text="Drag & drop PDF files below, or click to browse", 
            font=("Malgun Gothic", 12, "bold"), 
            fg="#334155", 
            bg=self.bg_color
        )
        lbl_info.pack(pady=(25, 15))

        drop_frame = tk.Frame(root, bg=self.bg_color)
        drop_frame.pack(fill="x", padx=25)
        
        self.box_file1 = tk.Label(
            drop_frame, 
            text="[ Original File ]\n\n📄\n\nDrag & drop or\nclick to select", 
            font=("Malgun Gothic", 10),
            bg="#eff6ff", 
            fg="#1e40af", 
            width=30, 
            height=8, 
            relief="solid", 
            bd=2, 
            highlightbackground="#bfdbfe" 
        )
        self.box_file1.config(highlightthickness=2, highlightcolor="#bfdbfe", bd=0)
        self.box_file1.pack(side="left", expand=True, fill="both", padx=(0, 10))
        
        self.box_file1.drop_target_register(DND_FILES)
        self.box_file1.dnd_bind('<<Drop>>', self.drop_file1)
        self.box_file1.bind("<Button-1>", lambda e: self.select_file1())

        self.box_file2 = tk.Label(
            drop_frame, 
            text="[ Revised File ]\n\n📄\n\nDrag & drop or\nclick to select", 
            font=("Malgun Gothic", 10),
            bg="#fff1f2", 
            fg="#9f1239", 
            width=30, 
            height=8, 
            relief="solid", 
            bd=2
        )
        self.box_file2.config(highlightthickness=2, highlightcolor="#fecdd3", bd=0)
        self.box_file2.pack(side="right", expand=True, fill="both", padx=(10, 0))
        
        self.box_file2.drop_target_register(DND_FILES)
        self.box_file2.dnd_bind('<<Drop>>', self.drop_file2)
        self.box_file2.bind("<Button-1>", lambda e: self.select_file2())
        
        # Sensitivity control UI
        self.sensitivity_var = tk.IntVar(value=5)
        
        sens_frame = tk.Frame(root, bg=self.bg_color)
        sens_frame.pack(fill="x", padx=25, pady=(20, 5))
        
        lbl_sens_title = tk.Label(sens_frame, text="Comparison Sensitivity :", font=("Malgun Gothic", 10, "bold"), fg="#475569", bg=self.bg_color)
        lbl_sens_title.pack(side="left")
        
        self.lbl_sens_val = tk.Label(sens_frame, text="5", font=("Malgun Gothic", 11, "bold"), fg="#10b981", bg=self.bg_color)
        self.lbl_sens_val.pack(side="right", padx=(10, 0))

        self.slider = ttk.Scale(
            sens_frame, 
            from_=0, 
            to=10, 
            orient="horizontal", 
            variable=self.sensitivity_var, 
            command=self.update_sens_label
        )
        self.slider.pack(side="left", fill="x", expand=True, padx=(10, 0))
        
        self.root.bind("<Left>",  lambda e: self.adjust_sensitivity(-1))
        self.root.bind("<Right>", lambda e: self.adjust_sensitivity(1))

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TProgressbar", thickness=8, background="#10b981", troughcolor="#e2e8f0", bordercolor=self.bg_color)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(root, variable=self.progress_var, maximum=100, length=590, style="TProgressbar")
        self.progress_bar.pack(fill="x", padx=25, pady=(15, 5))
        
        self.lbl_progress = tk.Label(root, text="Progress: 0%", font=("Malgun Gothic", 9), fg="#64748b", bg=self.bg_color)
        self.lbl_progress.pack()
        
        # Load search icon for compare button
        icon_path = resource_path("search_icon.png")
        if os.path.exists(icon_path):
            img = Image.open(icon_path)
            img = img.resize((20, 20), Image.Resampling.LANCZOS)
            self.search_icon = ImageTk.PhotoImage(img)
        else:
            self.search_icon = None

        self.btn_compare = tk.Label(
            root, 
            text="Compare Differences ", 
            image=self.search_icon,
            compound="right",
            bg="#10b981", 
            fg="white", 
            font=("Malgun Gothic", 12, "bold"), 
            cursor="hand2"
        )
        self.btn_compare.pack(fill="x", padx=25, pady=(10, 15), ipady=12)
        
        self.btn_compare.bind("<Enter>",    lambda e: self.btn_compare.config(bg="#059669"))
        self.btn_compare.bind("<Leave>",    lambda e: self.btn_compare.config(bg="#10b981"))
        self.btn_compare.bind("<Button-1>", lambda e: self.start_comparison())

        self.file1_path = ""
        self.file2_path = ""

    def update_sens_label(self, val):
        int_val = round(float(val))
        self.sensitivity_var.set(int_val)
        self.lbl_sens_val.config(text=str(int_val))

    def adjust_sensitivity(self, delta):
        new_val = self.sensitivity_var.get() + delta
        if 0 <= new_val <= 10:
            self.sensitivity_var.set(new_val)
            self.slider.set(new_val)
            self.lbl_sens_val.config(text=str(new_val))

    def clean_path(self, path):
        return path.strip('{}').strip('"')

    def drop_file1(self, event):
        file_path = self.clean_path(event.data)
        if file_path.lower().endswith('.pdf'):
            self.set_file1(file_path)
        else:
            messagebox.showerror("Error", "Only PDF files are supported.")

    def select_file1(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if file_path:
            self.set_file1(file_path)

    def set_file1(self, path):
        self.file1_path = path
        self.box_file1.config(
            text=f"[ Original Loaded ]\n\n📄\n\n{os.path.basename(path)}", 
            bg="#dbeafe", 
            fg="#1d4ed8",
            font=("Malgun Gothic", 10, "bold"),
            wraplength=250
        )

    def drop_file2(self, event):
        file_path = self.clean_path(event.data)
        if file_path.lower().endswith('.pdf'):
            self.set_file2(file_path)
        else:
            messagebox.showerror("Error", "Only PDF files are supported.")

    def select_file2(self):
        file_path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if file_path:
            self.set_file2(file_path)

    def set_file2(self, path):
        self.file2_path = path
        self.box_file2.config(
            text=f"[ Revised Loaded ]\n\n📄\n\n{os.path.basename(path)}", 
            bg="#fce7f3", 
            fg="#be123c",
            font=("Malgun Gothic", 10, "bold"),
            wraplength=250
        )
        
    def start_comparison(self):
        if not self.file1_path or not self.file2_path:
            messagebox.showwarning("Warning", "Please load both the original and revised PDF files.")
            return
            
        file2_name = os.path.splitext(os.path.basename(self.file2_path))[0]
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        current_sensitivity = self.sensitivity_var.get()
        default_filename = f"{file2_name}_comparison_sensitivity{current_sensitivity}_{current_time}.pdf"
        
        output_save_path = filedialog.asksaveasfilename(
            title="Save Comparison Result PDF",
            defaultextension=".pdf",
            filetypes=[("PDF Document", "*.pdf")],
            initialfile=default_filename
        )
        if not output_save_path:
            return
            
        temp_dir = tempfile.mkdtemp()
        result_pdfs = []
        total_check_count = 0
        
        current_sensitivity = self.sensitivity_var.get()
        
        try:
            doc1 = fitz.open(self.file1_path)
            doc2 = fitz.open(self.file2_path)
            max_pages = max(len(doc1), len(doc2))
            
            for i in range(max_pages):
                t1   = os.path.join(temp_dir, f"1_page_{i}.png")
                t2   = os.path.join(temp_dir, f"2_page_{i}.png")
                tout = os.path.join(temp_dir, f"out_page_{i}.png")
                tpdf = os.path.join(temp_dir, f"out_page_{i}.pdf")
                
                if i < len(doc1):
                    pdf_page_to_image(doc1, i, t1)
                if i < len(doc2):
                    pdf_page_to_image(doc2, i, t2)
                
                check_count = run_image_diff(t1, t2, tout, sensitivity=current_sensitivity)
                total_check_count += check_count
                
                if os.path.exists(tout):
                    convert_image_to_pdf(tout, tpdf)
                    result_pdfs.append(tpdf)
                
                progress = ((i + 1) / max_pages) * 100
                self.progress_var.set(progress)
                self.lbl_progress.config(text=f"Progress: {int(progress)}% ({i + 1}/{max_pages} pages)")
                self.root.update()
                    
            doc1.close()
            doc2.close()
            
            if result_pdfs:
                out_pdf = fitz.open()
                for pdf_path in result_pdfs:
                    input_pdf = fitz.open(pdf_path)
                    out_pdf.insert_pdf(input_pdf)
                    input_pdf.close()
                out_pdf.save(output_save_path)
                out_pdf.close()
            
            self.progress_var.set(0)
            self.lbl_progress.config(text="Progress: 0%")
            
            messagebox.showinfo("Complete", f"Comparison finished successfully.\n\nDifferences found: {total_check_count}")

            # Attempt to open the result PDF automatically
            if os.path.exists(output_save_path):
                try:
                    if platform.system() == 'Windows':
                        win_path = os.path.normpath(output_save_path)
                        os.startfile(win_path)
                    else:
                        opener = "open" if platform.system() == "Darwin" else "xdg-open"
                        subprocess.call([opener, output_save_path])
                except Exception:
                    # Fall back to opening the containing folder in Explorer
                    win_path = os.path.normpath(output_save_path)
                    subprocess.Popen(f'explorer /select,"{win_path}"')
            
        except Exception as e:
            self.progress_var.set(0)
            self.lbl_progress.config(text="Progress: 0%")
            messagebox.showerror("Error", f"An error occurred during processing:\n{str(e)}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    window = TkinterDnD.Tk()
    app = PDFCompareApp(window)
    window.mainloop()