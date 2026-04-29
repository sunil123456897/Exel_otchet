from tkinter import ttk
from typing import ClassVar

class ThemeManager:
    COLORS: ClassVar[dict[str, str]] = {
        'primary': '#1f4e79',
        'success': '#28a745',
        'danger': '#dc3545',
        'warning': '#ffc107',
        'info': '#17a2b8',
        'bg_light': '#f8f9fa',
        'sidebar': '#ffffff',
        'text': '#212529'
    }

    @classmethod
    def apply_styles(cls):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Main.TFrame', background='#f0f2f5')
        style.configure('Sidebar.TFrame', background=cls.COLORS['sidebar'], relief='flat')
        style.configure('TLabel', background='#f0f2f5', foreground=cls.COLORS['text'], font=('Segoe UI', 10))
        style.configure('Sidebar.TLabel', background=cls.COLORS['sidebar'], font=('Segoe UI', 10))
        style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'), foreground=cls.COLORS['primary'])
        style.configure('TButton', font=('Segoe UI', 10), padding=5)
        style.configure('Action.TButton', background=cls.COLORS['primary'], foreground='white')
        style.map('Action.TButton', background=[('active', '#153654')])
        style.configure('Success.TButton', background=cls.COLORS['success'], foreground='white')
        style.map('Success.TButton', background=[('active', '#218838')])
        style.configure('Audit.TButton', background=cls.COLORS['info'], foreground='white')
        style.map('Audit.TButton', background=[('active', '#138496')])
        style.configure('TLabelframe', background=cls.COLORS['sidebar'], relief='groove', borderwidth=1)
        style.configure('TLabelframe.Label', background=cls.COLORS['sidebar'], foreground=cls.COLORS['primary'], font=('Segoe UI', 9, 'bold'))
        style.configure('Treeview', font=('Segoe UI', 10), rowheight=30)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), background='#e9ecef')
        style.map('Treeview', background=[('selected', cls.COLORS['primary'])], foreground=[('selected', 'white')])
        style.configure('TProgressbar', thickness=15, troughcolor='#e9ecef', background=cls.COLORS['primary'])

