"""Stage 1 / MR-0103 — verify the 14 synthetic fixture scenarios.

Three properties must hold for the fixtures to be usable as golden inputs:

1. **Buildability** — every scenario builder produces a non-empty
   Workbook with at least one sheet.
2. **Determinism** — calling a builder twice and saving both results
   yields byte-identical files. Without this, golden tests would flap.
3. **Shape sanity** — every sheet has a header row, headers are unique,
   data rows follow.

These tests do NOT yet exercise the real consolidation pipeline — that
is MR-0104's job (invariants). They just lock the *inputs*.
"""
from __future__ import annotations

import datetime
import hashlib
import zipfile
from io import BytesIO

import openpyxl
import pytest
from synthetic_fixtures import SCENARIOS  # from tests/golden/, on pythonpath


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS),
                         ids=sorted(SCENARIOS))
def test_scenario_builds_and_has_content(scenario_id: str) -> None:
    """Each scenario must produce a workbook with at least one sheet and row."""
    wb = SCENARIOS[scenario_id]()
    assert wb.sheetnames, f"{scenario_id}: workbook has no sheets"
    for name in wb.sheetnames:
        ws = wb[name]
        assert ws.max_row >= 2, (
            f"{scenario_id}/{name}: sheet must have at least a header + one data row"
        )


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS),
                         ids=sorted(SCENARIOS))
def test_scenario_is_deterministic(scenario_id: str) -> None:
    """Same builder called twice must yield identical *content*.

    We hash a time-normalised form of the xlsx rather than the raw bytes:
    openpyxl stamps BOTH the docProps timestamps (``datetime.now()``) AND
    every zip entry (current time at 2 s DOS granularity), so raw bytes
    differ across a clock tick even when the workbook CONTENT is identical
    — which made this determinism test flap under load. Pinning the docProps
    and re-packing the zip with fixed entry dates makes the hash reflect
    content only, which is the property golden tests actually rely on.
    """
    fixed = datetime.datetime(2020, 1, 1)

    def _content_bytes(wb: openpyxl.Workbook) -> bytes:
        wb.properties.created = fixed
        wb.properties.modified = fixed
        raw = BytesIO()
        wb.save(raw)
        raw.seek(0)
        out = BytesIO()
        with zipfile.ZipFile(raw) as src, zipfile.ZipFile(
            out, "w", zipfile.ZIP_DEFLATED
        ) as dst:
            for item in src.infolist():
                item.date_time = (2020, 1, 1, 0, 0, 0)
                dst.writestr(item, src.read(item.filename))
        return out.getvalue()

    wb1 = SCENARIOS[scenario_id]()
    wb2 = SCENARIOS[scenario_id]()
    h1 = hashlib.sha256(_content_bytes(wb1)).hexdigest()
    h2 = hashlib.sha256(_content_bytes(wb2)).hexdigest()
    assert h1 == h2, (
        f"{scenario_id}: builder is non-deterministic "
        f"(sha256 #{1}={h1[:12]}…, #{2}={h2[:12]}…). "
        f"Golden tests require byte-identical reproduction."
    )


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS),
                         ids=sorted(SCENARIOS))
def test_scenario_has_unique_headers(scenario_id: str) -> None:
    """First-row headers in every sheet must be unique.

    Non-unique headers would make column-name-based ingestion ambiguous.
    """
    wb = SCENARIOS[scenario_id]()
    for name in wb.sheetnames:
        ws = wb[name]
        header_cells = [ws.cell(row=1, column=c).value
                        for c in range(1, (ws.max_column or 0) + 1)]
        header_cells = [str(h).strip() for h in header_cells if h is not None]
        if not header_cells:
            continue  # scenarios like empty_partial start with headers anyway
        dupes = {h for h in header_cells if header_cells.count(h) > 1}
        assert not dupes, (
            f"{scenario_id}/{name}: duplicate headers {dupes}"
        )


def test_at_least_14_scenarios_registered() -> None:
    """TZ MR-0103 mandates coverage of 14 scenarios."""
    assert len(SCENARIOS) >= 14, (
        f"expected ≥14 scenarios, got {len(SCENARIOS)}: {sorted(SCENARIOS)}"
    )


def test_no_real_pii_in_any_fixture() -> None:
    """Sanity scan: none of the fixtures should contain real-looking data.

    We reject a small blocklist of patterns that would indicate a real
    firm's data leaked into a synthetic fixture. The fixtures use
    deliberately generic tokens like "Клиент А", "Подрядчик 1".

    This is a belt-and-braces check; the fixtures are committed and can
    be eyeballed, but an automated guard makes accidental future
    contamination fail loudly.
    """
    forbidden_patterns = [
        # Russian firm legal-form prefixes that would precede a real name
        "ООО ", "ОАО ", "ЗАО ", "АО ", "ИП ",
        # Real-looking account / INN numbers
        "ИНН", "КПП", "ОГРН",
        # Real-looking phone numbers
        "+7 ", "8 (",
        # USD/EUR amounts that look like real transactions (>1M)
        # — synthetic amounts are deliberately small (≤10 000)
    ]
    for scenario_id, builder in SCENARIOS.items():
        wb = builder()
        for name in wb.sheetnames:
            ws = wb[name]
            for row in ws.iter_rows(values_only=True):
                for cell in row:
                    if cell is None:
                        continue
                    s = str(cell)
                    for pat in forbidden_patterns:
                        assert pat not in s, (
                            f"{scenario_id}/{name}: cell matches forbidden PII pattern "
                            f"{pat!r}: {s!r}"
                        )
