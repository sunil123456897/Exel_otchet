import sys
import os
import tkinter as tk

# Ensure the root folder containing 'src' is in sys.path
app_root = os.path.dirname(os.path.abspath(__file__))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

# Correctly import from the src package
from src.gui_master import GuiMaster

if __name__ == "__main__":
    print(f"--- APP STARTING AT: {app_root} ---")
    root = tk.Tk()
    
    # Locate config.yaml relative to this main.py file
    config_path = os.path.join(app_root, "config.yaml")
    
    app = GuiMaster(root, config_path=config_path)
    root.mainloop()
