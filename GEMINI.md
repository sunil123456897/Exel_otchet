# Project: Version5

Project for consolidation and reporting with advanced testing and ingestion pipelines.

## Architecture & Context
- [Main Architecture](docs/knowledge_base/ARCHITECTURE.md) - Overview of the system structure.
- [App Module Context](APP/GEMINI.md) - Detailed logic, GUI, and infrastructure overview.
- [Documentation Index](docs/GEMINI.md) - Detailed project documentation and report index.
- [Financial Logic](docs/knowledge_base/FINANCIAL_LOGIC.md) - Domain-specific calculation rules.
- [Ingestion Pipeline](docs/knowledge_base/INGESTION_PIPELINE.md) - Details on data ingestion logic.
- [Testing Infrastructure](docs/knowledge_base/TESTING_INFRASTRUCTURE.md) - Description of the testing framework.

## Key Reports
- [Testing Report Elite](TESTING_REPORT_ELITE.md) - Latest testing results and coverage.
- [Destabilization Report](DESTABILIZATION_REPORT.md) - Stress and chaos testing analysis.
- [Refactoring Report](docs/REFACTORING_REPORT.md) - History of structural improvements.

## Conventions
- Always use specialized skills (xlsx) for Excel operations.
- Prioritize MCP servers (GitNexus, Sentrux, etc.) per Ecosystem First Protocol.
- **Subagent Priority**: ALWAYS prefer delegating tasks to specialized subagents (coder, tester, architect, etc.) for complex, multi-file, or repetitive work to maintain context efficiency and session speed.
- Maintain comprehensive testing (edge cases, stress tests) as per global preference.
- Always use a two-pass iterator approach with python-calamine for Excel ingestion to prevent OOM on large files.
- Always implement a 'Pre-flight lock check' for any master report files before starting the consolidation process.
- Always use explicit transaction blocks (BEGIN TRANSACTION / COMMIT / ROLLBACK) for SQLite operations to ensure data integrity during crashes.
- Always mark data integrity issues (like numeric parse errors) with a specific flag (is_critical) and highlight them in red in the final report.
- Always use '01.01.1900' as a sentinel for invalid dates and group them in an 'UNKNOWN_DATE' sheet.
