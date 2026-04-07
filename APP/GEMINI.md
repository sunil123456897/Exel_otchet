# Module: APP

This module contains the core application logic, GUI, and infrastructure for the consolidation and reporting system.

## Directory Structure
- `core/` - Internal core logic.
    - `domain/` - Business logic, data schemas, and interfaces.
    - `infra/` - Infrastructure services: configuration, discovery, persistence, ingestion, and export.
    - `ui/` - GUI components using PyQt (gui_master, themes, dialogs).
- `view_models/` - ViewModel implementation for the GUI-Logic binding.
- `main.py` - Application entry point.
- `headless_run.py` - Headless execution mode for CI/CD or automation.
- `toxic_run.py` - Execution mode for stress/chaos testing with toxic data.

## Key Logic & Ingestion
- [Ingestion Engine](core/infra/ingestion_engine.py) - Main logic for parsing and processing incoming data.
- [Logic Service](core/domain/logic_service.py) - Financial and business rules engine.
- [App Controller](core/app_controller.py) - Main orchestrator for the application flow.

## Conventions
- UI and logic are strictly separated via ViewModels.
- All configuration is managed through `config_controller`.
- Export styles and writers are abstracted for modularity.
- **Ecosystem First Protocol**: ALWAYS use `gitnexus` for core logic exploration and `sentrux` for structural health/complexity auditing.
- Always batch UI-bound log updates with a delay (e.g., 50 logs/100ms) to prevent GUI event loop saturation.
