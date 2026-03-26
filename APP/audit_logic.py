import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

class AuditLogger:
    def __init__(self, audit_file=None):
        if audit_file is None:
            audit_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "DEEP_AUDIT_REPORT.txt"
            )
        self.audit_file = audit_file
        self.buffer = []
        self.start_time = datetime.now()
        
        # FIXED: 8 - Add RotatingFileHandler
        self.logger = logging.getLogger("AuditLogger")
        self.logger.setLevel(logging.INFO)
        # Check if handler already exists to prevent duplicate logs
        if not self.logger.handlers:
            audit_dir = os.path.dirname(os.path.abspath(self.audit_file))
            if audit_dir and not os.path.exists(audit_dir):
                os.makedirs(audit_dir, exist_ok=True)
            # maxBytes=5MB, backupCount=3
            handler = RotatingFileHandler(self.audit_file, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)

    # FIXED: 8 - Add clear_old_sessions
    def clear_old_sessions(self, keep_last_n=100):
        if not os.path.exists(self.audit_file):
            return
        try:
            with open(self.audit_file, 'r', encoding='utf-8') as f:
                content = f.read()
            sessions = content.split('NEW CONSOLIDATION SESSION\n')

            # The prompt says: "truncates the file if it exceeds 1000 entries."
            # Which means if len(sessions) > 1000, truncate to keep_last_n
            if len(sessions) > 1000:
                # Keep the part before the first session and the last N sessions
                kept_sessions = [sessions[0]] + sessions[-(keep_last_n):]

                # Close handlers temporarily to allow file rewriting on Windows without PermissionError
                for h in list(self.logger.handlers):
                    h.close()
                    self.logger.removeHandler(h)

                with open(self.audit_file, 'w', encoding='utf-8') as f:
                    f.write('NEW CONSOLIDATION SESSION\n'.join(kept_sessions))

                # Restore the handler
                handler = RotatingFileHandler(self.audit_file, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
                handler.setFormatter(logging.Formatter('%(message)s'))
                self.logger.addHandler(handler)
        except Exception as e:
            print(f"Failed to clear old sessions: {e}")

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
        audit_dir = os.path.dirname(os.path.abspath(self.audit_file))
        if audit_dir and not os.path.exists(audit_dir):
            os.makedirs(audit_dir, exist_ok=True)

        log_str = []
        log_str.append(f"\n{'='*60}")
        log_str.append(f"NEW CONSOLIDATION SESSION")
        log_str.append(f"Started:  {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        log_str.append(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_str.append(f"{'='*60}\n")
        
        if not self.buffer:
            log_str.append("No operations recorded in this session.")
        else:
            for entry in self.buffer:
                line = f"[{entry['time']}] [{entry['emp']}][{entry['sheet']}] "
                line += f"CUST: {entry['cust']} | STATUS: {entry['status']} | {entry['reason']}"
                if entry['data']:
                    line += f"\n   ORIGINAL: {entry['data']}"
                log_str.append(line)
        
        log_str.append("\n")

        self.logger.info("\n".join(log_str))
                
        print(f"Audit report appended to {self.audit_file}")
        # Clear buffer after saving to avoid duplicate appends if called again in same process
        self.buffer = []
        self.start_time = datetime.now()

# Global singleton for easier access
audit = AuditLogger()
import atexit
atexit.register(lambda: audit.save() if audit.buffer else None)
