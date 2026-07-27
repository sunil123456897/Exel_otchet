import sys
import os
import difflib

ws1 = r"e:\Dlia Dashi\Version5\APP"
ws2 = r"C:\Users\vanya\Desktop\workspace-25b6a0ab-0a35-4c0a-aa7c-abe7168cc6fa\upload\extracted\APP"

files = [
    r"core/infra/staging_repo.py",
    r"core/infra/ingestion_reader.py",
    r"core/domain/logic_service.py",
    r"core/domain/data_loss_log.py"
]

for rel_path in files:
    p1 = os.path.join(ws1, rel_path.replace("/", "\\"))
    p2 = os.path.join(ws2, rel_path.replace("/", "\\"))
    
    if not os.path.exists(p1):
        print(f"File missing in ws1: {p1}")
        continue
    if not os.path.exists(p2):
        print(f"File missing in ws2: {p2}")
        continue
        
    with open(p1, "r", encoding="utf-8") as f1, open(p2, "r", encoding="utf-8") as f2:
        lines1 = f1.readlines()
        lines2 = f2.readlines()
        
    diff = list(difflib.unified_diff(
        lines1, lines2,
        fromfile=f"ws1/{rel_path}",
        tofile=f"ws2/{rel_path}",
        n=2
    ))
    
    if diff:
        print(f"=== DIFF FOR {rel_path} ===")
        sys.stdout.writelines(diff)
        print("\n" + "="*50 + "\n")
    else:
        print(f"No diff for {rel_path}")
