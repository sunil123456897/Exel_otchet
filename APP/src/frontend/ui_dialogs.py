import tkinter as tk
from tkinter import ttk, filedialog, simpledialog
from typing import List, Callable

def show_attach_file_dialog(parent, employees: List[str], on_attach: Callable[[str, List[str], bool], None]):
    dialog = tk.Toplevel(parent)
    dialog.title("Привязать файлы")
    dialog.geometry("450x400")
    dialog.transient(parent)
    dialog.grab_set()
    
    ttk.Label(dialog, text="Выберите сотрудника:", padding=10).pack()
    lb = tk.Listbox(dialog)
    for e in employees: lb.insert(tk.END, e)
    lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    append_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(dialog, text="Добавить к существующим", variable=append_var).pack(pady=5)
    
    def pick():
        sel = lb.curselection()
        if not sel: return
        emp_name = lb.get(sel[0])
        file_paths = filedialog.askopenfilenames(title=f"Файлы для {emp_name}")
        if file_paths:
            on_attach(emp_name, list(file_paths), append_var.get())
            dialog.destroy()
    
    btn_frame = ttk.Frame(dialog, padding=10)
    btn_frame.pack(fill=tk.X)
    ttk.Button(btn_frame, text="Выбрать файлы", command=pick).pack(side=tk.RIGHT)
    ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

def ask_employee_name() -> str:
    return simpledialog.askstring("Добавить", "Имя сотрудника:")
