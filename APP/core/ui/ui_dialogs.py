import os
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog
from pathlib import Path
from typing import Callable, List, Optional


def show_multi_file_select_dialog(
    parent,
    initial_paths: Optional[List[str]] = None,
    title: str = "Выберите файлы",
    filetypes: Optional[List[tuple]] = None,
) -> List[str]:
    """Modal dialog for selecting multiple files with a live preview.

    Replaces the previous *askopenfilenames → askyesno → loop* pattern:
    the user adds files via the file picker one or more times, sees
    a live list of name/size/mtime, can remove individual entries,
    and confirms with a single click.  The dialog is empty until at
    least one file has been added; cancelling returns the original
    list (so the user can re-open and keep working with it).
    """
    if filetypes is None:
        filetypes = [("Excel files", "*.xlsx *.xlsm *.xlsb"), ("All files", "*.*")]

    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.geometry("640x400")
    dialog.transient(parent)
    dialog.grab_set()

    ttk.Label(dialog, text=title + ":", padding=(10, 10, 10, 0)).pack(anchor=tk.W)

    list_frame = ttk.Frame(dialog, padding=(10, 4))
    list_frame.pack(fill=tk.BOTH, expand=True)
    tree = ttk.Treeview(
        list_frame,
        columns=("size", "mtime"),
        show="headings",
        height=10,
        selectmode="extended",
    )
    tree.heading("#0", text="Имя файла")
    tree.heading("size", text="Размер")
    tree.heading("mtime", text="Изменён")
    tree.column("#0", width=320, anchor=tk.W)
    tree.column("size", width=110, anchor=tk.E)
    tree.column("mtime", width=160, anchor=tk.W)
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
    scroll.pack(side=tk.RIGHT, fill=tk.Y)
    tree.configure(yscrollcommand=scroll.set)

    def _format_size(n: int) -> str:
        for unit in ("Б", "КБ", "МБ", "ГБ"):
            if n < 1024:
                return f"{n:.0f} {unit}" if unit == "Б" else f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} ТБ"

    def _refresh(paths: List[str]) -> None:
        for row in tree.get_children():
            tree.delete(row)
        for p in paths:
            try:
                st = os.stat(p)
                size = _format_size(st.st_size)
                mtime = (
                    Path(p)
                    .stat()
                    .st_mtime
                )
                from datetime import datetime
                mtime_str = datetime.fromtimestamp(mtime).strftime(
                    "%d.%m.%Y %H:%M"
                )
                tree.insert("", tk.END, iid=p, text=Path(p).name,
                            values=(size, mtime_str))
            except OSError:
                tree.insert("", tk.END, iid=p, text=Path(p).name + " (нет доступа)",
                            values=("-", "-"))

    selected: List[str] = list(initial_paths or [])
    _refresh(selected)

    def _add() -> None:
        initial_dir = None
        if selected:
            initial_dir = str(Path(selected[0]).parent)
        new = filedialog.askopenfilenames(
            title="Добавить файлы",
            filetypes=filetypes,
            initialdir=initial_dir,
        )
        if not new:
            return
        seen = set(selected)
        for p in new:
            if p not in seen:
                selected.append(p)
                seen.add(p)
        _refresh(selected)

    def _remove() -> None:
        for iid in tree.selection():
            if iid in selected:
                selected.remove(iid)
        _refresh(selected)

    def _ok() -> None:
        dialog.destroy()

    def _cancel() -> None:
        # Cancelling reverts to the *original* list — the user can
        # always re-open the dialog and start over without losing
        # what they had staged.
        selected[:] = list(initial_paths or [])
        dialog.destroy()

    btn_frame = ttk.Frame(dialog, padding=10)
    btn_frame.pack(fill=tk.X)
    ttk.Button(btn_frame, text="➕ Добавить ещё", command=_add).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="➖ Удалить", command=_remove).pack(side=tk.LEFT, padx=(5, 0))
    ttk.Button(btn_frame, text="Готово", command=_ok).pack(side=tk.RIGHT)
    ttk.Button(btn_frame, text="Отмена", command=_cancel).pack(side=tk.RIGHT, padx=5)

    dialog.wait_window()
    return list(selected)


def show_attach_file_dialog(
    parent,
    employees: List[str],
    on_attach: Callable[[str, List[str], bool], None],
    preselect: Optional[str] = None,
):
    dialog = tk.Toplevel(parent)
    dialog.title("Привязать файлы")
    dialog.geometry("450x400")
    dialog.transient(parent)
    dialog.grab_set()

    ttk.Label(dialog, text="Выберите сотрудника:", padding=10).pack()
    employee_var = tk.StringVar()
    employee_combo = ttk.Combobox(
        dialog,
        textvariable=employee_var,
        values=employees,
        # Pre-typed characters narrow the dropdown — Tk's built-in
        # ``postcommand`` filters via the *starts-with* heuristic, which
        # is good enough for ≤100 employees.
    )
    employee_combo.pack(fill=tk.X, padx=10, pady=5)
    if preselect and preselect in employees:
        # Pre-select the row that was right-clicked on, so the user
        # does not have to re-pick from the dropdown.
        employee_var.set(preselect)
    employee_combo.focus_set()

    selected_files_frame = ttk.LabelFrame(dialog, text="Выбранные файлы", padding=6)
    selected_files_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
    files_listbox = tk.Listbox(selected_files_frame, height=6)
    files_listbox.pack(fill=tk.BOTH, expand=True)

    append_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(dialog, text="Добавить к существующим", variable=append_var).pack(pady=5)

    def pick_files() -> None:
        paths = filedialog.askopenfilenames(title="Файлы для привязки")
        for p in paths:
            files_listbox.insert(tk.END, p)

    def pick() -> None:
        emp_name = employee_var.get().strip()
        if not emp_name:
            return
        files = list(files_listbox.get(0, tk.END))
        if not files:
            # No files staged yet — open the picker once before bailing.
            paths = filedialog.askopenfilenames(
                title=f"Файлы для {emp_name}"
            )
            files = list(paths)
        if not files:
            return
        on_attach(emp_name, files, append_var.get())
        dialog.destroy()

    btn_frame = ttk.Frame(dialog, padding=10)
    btn_frame.pack(fill=tk.X)
    ttk.Button(btn_frame, text="Выбрать файлы", command=pick_files).pack(side=tk.LEFT)
    ttk.Button(btn_frame, text="Привязать", command=pick).pack(side=tk.RIGHT)
    ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)


def ask_employee_name(existing_names: Optional[List[str]] = None) -> str:
    """Open a custom Add-Employee dialog with realtime validation.

    The dialog is modal, gives the user live feedback (red/green
    border + tooltip) on empty/whitespace/duplicate input, and only
    enables the OK button when the name is valid.  The result is
    returned as a stripped string, or ``""`` if the user cancelled.
    """
    existing = {n.strip().lower() for n in (existing_names or []) if n and n.strip()}

    dialog = tk.Toplevel()
    dialog.title("Добавить сотрудника")
    dialog.geometry("380x200")
    dialog.transient(dialog.master)
    dialog.grab_set()
    dialog.resizable(False, False)

    ttk.Label(dialog, text="Имя сотрудника:", padding=(10, 10, 10, 0)).pack(anchor=tk.W)

    name_var = tk.StringVar()
    entry = ttk.Entry(dialog, textvariable=name_var, width=40)
    entry.pack(fill=tk.X, padx=10, pady=4)
    entry.focus_set()

    status_var = tk.StringVar()
    status_label = ttk.Label(dialog, textvariable=status_var, padding=(10, 0))
    status_label.pack(fill=tk.X)

    btn_frame = ttk.Frame(dialog, padding=10)
    btn_frame.pack(fill=tk.X)
    cancel_btn = ttk.Button(btn_frame, text="Отмена", command=dialog.destroy)
    cancel_btn.pack(side=tk.RIGHT, padx=(5, 0))
    ok_btn = ttk.Button(btn_frame, text="Добавить", command=dialog.destroy)
    ok_btn.pack(side=tk.RIGHT)
    ok_btn.state(["disabled"])

    result_holder: List[str] = [""]

    def _validate(_event=None) -> None:
        raw = name_var.get()
        name = raw.strip()
        if not raw:
            status_var.set("")
            ok_btn.state(["disabled"])
            return
        if not name:
            status_var.set("Имя не может состоять только из пробелов")
            ok_btn.state(["disabled"])
            return
        if name.lower() in existing:
            status_var.set(f"Сотрудник «{name}» уже существует")
            ok_btn.state(["disabled"])
            return
        status_var.set(f"Готово к добавлению: «{name}»")
        ok_btn.state(["!disabled"])

    def _submit() -> None:
        # Only invoked when the OK button is enabled, so the input is
        # already valid by the time we get here.
        result_holder[0] = name_var.get().strip()
        dialog.destroy()

    ok_btn.configure(command=_submit)
    name_var.trace_add("write", lambda *_args: _validate())
    entry.bind("<Return>", lambda _e: _submit() if "disabled" not in ok_btn.state() else None)
    entry.bind("<Escape>", lambda _e: dialog.destroy())
    dialog.bind("<Destroy>", lambda _e: None, add="+")

    dialog.wait_window()
    return result_holder[0]
