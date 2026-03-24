import os
from datetime import datetime

class AuditLogger:
    def __init__(self, audit_file="DEEP_AUDIT_REPORT.txt"):
        self.audit_file = audit_file
        self.buffer = []
        self.start_time = datetime.now()
        
    def log_action(self, employee, sheet, customer, status, reason, original_data=None):
        """
        Records a single decision for audit purposes.
        """
        entry = {
            'time': datetime.now().strftime("%H:%M:%S"),
            'emp': employee,
            'sheet': sheet,
            'cust': customer,
            'status': status,
            'reason': reason,
            'data': str(original_data) if original_data else ""
        }
        self.buffer.append(entry)
        
    def save(self):
        """
        Appends the buffer to the audit file to preserve history across sessions.
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.audit_file)), exist_ok=True)
        
        file_exists = os.path.exists(self.audit_file)
        
        with open(self.audit_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"NEW CONSOLIDATION SESSION\n")
            f.write(f"Started:  {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")
            
            if not self.buffer:
                f.write("No operations recorded in this session.\n")
            else:
                for entry in self.buffer:
                    line = f"[{entry['time']}] [{entry['emp']}][{entry['sheet']}] "
                    line += f"CUST: {entry['cust']} | STATUS: {entry['status']} | {entry['reason']}\n"
                    if entry['data']:
                        line += f"   ORIGINAL: {entry['data']}\n"
                    f.write(line)
            
            f.write("\n")
                
        print(f"Audit report appended to {self.audit_file}")
        # Clear buffer after saving to avoid duplicate appends if called again in same process
        self.buffer = []
        self.start_time = datetime.now()

# Global singleton for easier access
audit = AuditLogger()
