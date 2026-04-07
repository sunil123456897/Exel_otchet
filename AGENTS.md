# Ecosystem Master Guide — Version5

This project is optimized for an agentic ecosystem. You MUST use specialized MCP tools and skills as your primary interface.

## 1. Code Intelligence & Quality (GitNexus & Sentrux MCP)
- **ALWAYS** run `gitnexus_impact({target: "symbol", direction: "upstream"})` before editing any function/class/method.
- **ALWAYS** run `gitnexus_detect_changes()` before committing to verify scope.
- **ALWAYS** use `gitnexus_query` or `gitnexus_context` instead of grep for exploration.
- **ALWAYS** use `sentrux` tools (`health`, `check_rules`, `dsm`) to ensure architectural integrity.
- **WARNING:** If risk is HIGH or CRITICAL, you must warn the user before proceeding.

## 2. Documentation & Research (Context7 MCP)
- **MANDATORY:** Use `mcp_context7_query-docs` for all library-specific questions (React, FastAPI, Pandas, etc.).
- Do not guess API signatures. Verify against live docs via Context7.

## 3. Orchestration (Maestro Extension)
- Use Maestro for complex features or refactorings.
- Follow the 4-phase workflow: Design -> Plan -> Execute -> Complete.
- Leverage specialized subagents (`architect`, `coder`, `tester`) via their dedicated tools.

## 4. Methodology & Quality (Superpowers Extension)
- Activate skills at the start of every task:
    - `brainstorming`: Before any design or feature work.
    - `systematic-debugging`: Before fixing any bug.
    - `test-driven-development`: Before writing implementation code.
    - `verification-before-completion`: Before claiming a task is done.

## 5. Office & Data (Specialized Skills)
- Use `xlsx` skill for Excel operations (pandas + openpyxl).
- Use `pdf` skill for PDF generation/analysis.
- Use `docx` skill for Word document manipulation.

## 6. Integration (Google Workspace)
- Use `mcp_google-workspace_*` for all interactions with GSuite.

## Never Do
- NEVER perform "blind" edits without impact analysis.
- NEVER ignore lint/type errors — fix them idiomatically.
- NEVER bypass the specialized ecosystem tools for generic ones.

## Self-Check Protocol
1. Is there an MCP tool for this? (Use it)
2. Is there a Superpowers skill for this? (Activate it)
3. Did I check the impact? (GitNexus)
4. Did I verify the docs? (Context7)
