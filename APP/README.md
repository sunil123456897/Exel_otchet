# Master-Report v4.0: Financial Automation System

## 🚀 Overview
Professional-grade desktop application designed to automate daily financial consolidation for distributed teams (40+ employees). It transforms raw data from diverse sources (Template 1) into a centralized Master Report (Template 2) with integrated data validation and business analytics.

## 🛠 Tech Stack
- **Language**: Python 3.12+
- **Data Processing**: Pandas (Vectorized transformations), Openpyxl (Excel engine)
- **Math**: `decimal` module (100% financial precision, rounding protection)
- **GUI**: Tkinter + tkcalendar (Modern desktop interface)
- **Testing**: Pytest (Full suite for core logic & IO)
- **Distribution**: PyInstaller (Portable standalone distribution)

## ✨ Key Features
- **Smart Consolidation**: Automated discovery and processing of 40+ employee reports based on dynamic date filtering.
- **Enterprise-Grade Validation**: 
    - Mathematical verification (`Amount - Commission == Total`).
    - Duplicate transaction detection using hashing.
    - Missing data flagging (essential fields).
    - Visual alerting: automatic red-cell highlighting in Excel for erroneous rows.
- **Business Intelligence**:
    - Automatic generation of "ANALYTICS" dashboard.
    - Dynamic Excel Charts (Daily revenue dynamics, Top-5 Customers).
    - Summary tables for intermediaries and turnovers.
- **Robustness & UX**:
    - Automated backup system (rotational, timestamped).
    - Smart Error Interceptor: User-friendly alerts for common issues (e.g., file locks, missing configs).
    - Portable executable: Runs out-of-the-box on Windows without Python installation.

## 📁 Architecture
- `src/consolidator.py`: Transformation engine and validation logic.
- `src/writer.py`: Excel generation, styling, and analytics module.
- `src/gui_master.py`: Threaded UI with real-time status tracking.
- `tests/`: Comprehensive test suite for CI/CD readiness.
- `config.yaml`: Fully externalized business logic and path mapping.

## 📈 Quality Assurance
The project follows professional software engineering standards:
- **Accuracy**: Guaranteed by `Decimal` arithmetic.
- **Reliability**: Verified by automated unit tests.
- **Portability**: Configurable paths and standalone bundling.
- **Safety**: Fail-safe file operations and automated backups.
