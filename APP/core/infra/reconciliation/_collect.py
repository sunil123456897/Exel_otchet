from __future__ import annotations
from decimal import Decimal
from typing import Any, Optional
from openpyxl.worksheet.worksheet import Worksheet
from core.domain.data_loss_log import record_loss
from core.infra.excel_hyperlinks import extract_hyperlink_formula_parts
from ._types import MasterReconciliationRow, RschReconciliationRow, ReconciliationRow
from ._utils import (
    _to_decimal,
    _normalize_text,
    _is_total_row,
    _is_excluded_customer,
    _is_filter_header,
    _is_excluded_master_filter,
    _is_excluded_master_header,
    _is_excluded_rsch_comment,
    _excel_safe_text,
    STATUS_VERIFIED,
    STATUS_REVIEW,
    STATUS_ERROR,
    REASON_NO_CURATOR,
    REASON_NO_RSCH,
    REASON_CUSTOMER_MISMATCH,
    REASON_EXECUTOR_MISMATCH,
    REASON_AMOUNT_MISMATCH,
    _MASTER_HEADER_ALIASES,
    _text_tokens,
    _compact_text,
    _canonical_match_text,
    _executor_alias_keys,
)
from ._resolve import (
    _executor_matches,
    _row_amount_matches,
)


def _to_decimal_soft(
    value: Any,
    *,
    sheet: str,
    row_index: int,
    field: str,
    source: str,
) -> Decimal:
    """Fail-soft amount parsing for reconciliation row collection.

    Mirrors :func:`_to_decimal` but, instead of raising on a dirty cell,
    logs the loss to ``data_loss.log`` and returns ``Decimal("0")`` so a
    single bad amount never aborts the whole sheet. Returning 0 lets the
    surrounding ``income == 0 and expense == 0`` filter drop the row
    cleanly when both amounts are unusable.
    """
    try:
        return _to_decimal(value)
    except (ValueError, ArithmeticError):
        record_loss(
            source=source,
            kind="reconciliation_amount_parse",
            reason="Некорректное числовое значение в сверке; строка пропущена",
            row_index=row_index,
            sheet=sheet,
            field=field,
            original_value=value,
        )
        return Decimal("0")


def _sheet_source(ws: Worksheet) -> str:
    """Stable source identifier for a worksheet.

    openpyxl does not retain the on-disk file path after ``load_workbook``
    (``Workbook.path`` is the in-archive path ``/xl/workbook.xml``), so we
    key data-loss entries on the sheet title. The reconciliation callers
    already pass the on-disk paths to ``build_*_reconciliation_report``,
    which is where the broader context lives.
    """
    return f"reconciliation:{ws.title}"


def _header_map(ws: Worksheet, *, prefer_last: bool = False) -> dict[str, int]:
    headers: dict[str, int] = {}
    for col_idx in range(1, ws.max_column + 1):
        value = ws.cell(1, col_idx).value
        if value in (None, ""):
            continue
        header = str(value).strip()
        if prefer_last or header not in headers:
            headers[header] = col_idx
    return headers


def _master_output_headers(ws: Worksheet) -> list[str]:
    headers: list[str] = []
    for col_idx in range(1, ws.max_column + 1):
        value = ws.cell(1, col_idx).value
        if value in (None, "") or _is_filter_header(value) or _is_excluded_master_header(value):
            continue
        headers.append(_excel_safe_text(str(value).strip()))
    return headers


def _header_index(
    headers: dict[str, int],
    header: str,
    *,
    required: bool = True,
) -> int | None:
    aliases = _MASTER_HEADER_ALIASES.get(header, (header,))
    for alias in aliases:
        if alias in headers:
            return headers[alias]

    normalized_headers = {_normalize_text(key): value for key, value in headers.items()}
    for alias in aliases:
        normalized_alias = _normalize_text(alias)
        if normalized_alias in normalized_headers:
            return normalized_headers[normalized_alias]

    if required:
        raise KeyError(header)
    return None


def _master_cell_value(
    ws: Worksheet,
    row_idx: int,
    headers: dict[str, int],
    header: str,
) -> Any:
    col_idx = _header_index(headers, header, required=False)
    if col_idx is None:
        return None
    return _cell_display_value(ws, row_idx, col_idx)


def _cell_hyperlink_target(ws: Worksheet, row_idx: int, col_idx: int) -> str | None:
    formula_parts = extract_hyperlink_formula_parts(ws.cell(row_idx, col_idx).value)
    if formula_parts is not None:
        return formula_parts[0]
    hyperlink = ws.cell(row_idx, col_idx).hyperlink
    if hyperlink is None:
        return None
    target = hyperlink.target or hyperlink.location
    if target is None:
        return None
    return target.split("#", 1)[0]


def _cell_display_value(ws: Worksheet, row_idx: int, col_idx: int) -> Any:
    value = ws.cell(row_idx, col_idx).value
    formula_parts = extract_hyperlink_formula_parts(value)
    if formula_parts is not None:
        return formula_parts[1]
    return value


def _collect_master_rows(
    ws: Worksheet,
) -> tuple[list[str], list[MasterReconciliationRow], list[MasterReconciliationRow]]:
    headers = _header_map(ws)
    output_headers = _master_output_headers(ws)
    source_col = _header_index(headers, "Источник")
    customer_col = _header_index(headers, "ЗАКАЗЧИК")
    executor_col = _header_index(headers, "ИСПОЛНИТЕЛЬ")
    income_col = _header_index(headers, "Приход")
    expense_col = _header_index(headers, "Расход")
    filter_col = _header_index(headers, "Фильтры", required=False)
    rows: list[MasterReconciliationRow] = []
    excluded_rows: list[MasterReconciliationRow] = []
    for row_idx in range(2, ws.max_row + 1):
        source = _cell_display_value(ws, row_idx, source_col)
        if _is_total_row(source):
            continue
        customer = str(ws.cell(row_idx, customer_col).value or "").strip()
        executor = str(ws.cell(row_idx, executor_col).value or "").strip()
        if not customer and not executor:
            continue
        income = _to_decimal_soft(
            ws.cell(row_idx, income_col).value,
            sheet=ws.title,
            row_index=row_idx,
            field="Приход",
            source=_sheet_source(ws),
        )
        expense = _to_decimal_soft(
            ws.cell(row_idx, expense_col).value,
            sheet=ws.title,
            row_index=row_idx,
            field="Расход",
            source=_sheet_source(ws),
        )
        if income == 0 and expense == 0:
            continue
        values = [_master_cell_value(ws, row_idx, headers, header) for header in output_headers]
        row = MasterReconciliationRow(
            values=values,
            source=source,
            source_link=_cell_hyperlink_target(ws, row_idx, source_col),
            customer=customer,
            executor=executor,
            income=income,
            expense=expense,
        )
        if filter_col is not None and _is_excluded_master_filter(
            _cell_display_value(ws, row_idx, filter_col)
        ):
            excluded_rows.append(row)
        else:
            rows.append(row)
    return output_headers, rows, excluded_rows


def _collect_rsch_rows(ws: Worksheet) -> list[RschReconciliationRow]:
    headers = _header_map(ws, prefer_last=True)
    rows: list[RschReconciliationRow] = []
    for row_idx in range(2, ws.max_row + 1):
        first = ws.cell(row_idx, 1).value
        if _is_total_row(first):
            continue
        income = _to_decimal_soft(
            ws.cell(row_idx, headers["Приход"]).value,
            sheet=ws.title,
            row_index=row_idx,
            field="Приход",
            source=_sheet_source(ws),
        )
        expense = _to_decimal_soft(
            ws.cell(row_idx, headers["Расход"]).value,
            sheet=ws.title,
            row_index=row_idx,
            field="Расход",
            source=_sheet_source(ws),
        )
        if income == 0 and expense == 0:
            continue
        customer = str(ws.cell(row_idx, headers["ЗАКАЗЧИК"]).value or "").strip()
        if _is_excluded_customer(customer):
            continue
        comment = str(ws.cell(row_idx, headers["Комментарий"]).value or "").strip()
        if _is_excluded_rsch_comment(comment):
            continue
        rows.append(
            RschReconciliationRow(
                row_id=f"{ws.title}:{row_idx}",
                executor=str(ws.cell(row_idx, headers["ИСПОЛНИТЕЛЬ"]).value or "").strip(),
                customer=customer,
                contractor=str(ws.cell(row_idx, headers["Контрагент"]).value or "").strip(),
                comment=comment,
                income=income,
                expense=expense,
                source_link=_cell_hyperlink_target(ws, row_idx, headers.get("Источник", 1)),
            )
        )
    return rows


def _jaccard_similarity(left_tokens: set[str], right_tokens: set[str]) -> float:
    """Jaccard coefficient on two token sets."""
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(intersection) / len(union)


def _score_pair(
    master: MasterReconciliationRow,
    rsch: RschReconciliationRow,
) -> float:
    """Compute integral match score for a (master, rsch) pair.

    Returns -1 if amount does not match at all.
    Score ≥ 100 → VERIFIED,  ≥ 40 → REVIEW,  < 40 or empty → ERROR.
    """
    from difflib import SequenceMatcher

    # ── amount match (required) ──────────────────────────────
    if not _row_amount_matches(master, rsch):
        return -1.0

    score = 0.0

    # ── executor match (max +50) ─────────────────────────────
    if _executor_matches(master.executor, rsch.executor):
        score += 50.0
    elif master.executor and rsch.executor:
        # Partial: alias overlap without full token-subset
        left_keys = _executor_alias_keys(master.executor)
        right_keys = _executor_alias_keys(rsch.executor)
        if left_keys & right_keys:
            score += 30.0

    # ── customer match (max +50) ─────────────────────────────
    master_norm = _normalize_text(master.customer)
    master_canon = _canonical_match_text(master.customer)

    best_customer_score = 0.0
    for candidate in (rsch.customer, rsch.contractor, rsch.comment):
        if not candidate:
            continue
        cand_norm = _normalize_text(candidate)
        cand_canon = _canonical_match_text(candidate)

        # Perfect canonical match → max score
        if master_canon and master_canon == cand_canon:
            best_customer_score = 50.0
            break

        # Substring match → high score
        if master_norm and cand_norm and (master_norm in cand_norm or cand_norm in master_norm):
            best_customer_score = 45.0
            continue

        # Compact substring
        mast_comp = _compact_text(master.customer)
        cand_comp = _compact_text(candidate)
        if (
            len(mast_comp) >= 6
            and len(cand_comp) >= 6
            and (mast_comp in cand_comp or cand_comp in mast_comp)
        ):
            best_customer_score = max(best_customer_score, 40.0)
            continue

        # Jaccard on tokens
        master_tokens = _text_tokens(master.customer)
        cand_tokens = _text_tokens(candidate)
        j = _jaccard_similarity(master_tokens, cand_tokens)
        if j >= 0.3:
            best_customer_score = max(best_customer_score, 35.0 * j)

        # difflib ratio on normalised strings
        if master_norm and cand_norm:
            r = SequenceMatcher(None, master_norm, cand_norm).ratio()
            if r >= 0.6:
                best_customer_score = max(best_customer_score, 30.0 * r)

    score += best_customer_score
    return score


def _pair_reason(
    master: MasterReconciliationRow,
    rsch: RschReconciliationRow,
    score: float,
) -> str:
    """Determine human-readable reason for a match pair.

    Returns empty string for VERIFIED (≥90), specific reason otherwise.
    """
    if score >= 90:
        return ""
    if score < 0:
        return REASON_NO_RSCH

    # Check what went wrong
    executor_ok = _executor_matches(master.executor, rsch.executor)

    customer_ok = False
    for candidate in (rsch.customer, rsch.contractor, rsch.comment):
        if not candidate:
            continue
        mc = _canonical_match_text(master.customer)
        cc = _canonical_match_text(candidate)
        if mc and mc == cc:
            customer_ok = True
            break
        mn = _normalize_text(master.customer)
        cn = _normalize_text(candidate)
        if mn and cn and (mn in cn or cn in mn):
            customer_ok = True
            break

    if executor_ok and not customer_ok:
        return REASON_CUSTOMER_MISMATCH
    if customer_ok and not executor_ok:
        return REASON_EXECUTOR_MISMATCH
    if not executor_ok and not customer_ok:
        return REASON_CUSTOMER_MISMATCH
    # Amount-only fallback
    return REASON_AMOUNT_MISMATCH


def _build_reconciliation_rows(
    master_rows: list[MasterReconciliationRow],
    rsch_rows: list[RschReconciliationRow],
    alias_repo: Optional[Any] = None,
) -> list[ReconciliationRow]:
    """Simplified scoring-based matching.

    For each Master row, finds RSCH candidates by matching amount,
    scores each candidate (executor match + customer similarity),
    then does greedy assignment — each RSCH row used at most once.
    """
    from collections import defaultdict

    result: list[ReconciliationRow] = []
    used_rsch: set[int] = set()

    # ── build amount index ───────────────────────────────────
    amount_to_rsch: dict[Decimal, list[tuple[int, RschReconciliationRow]]] = defaultdict(list)
    for idx, row in enumerate(rsch_rows):
        if row.income != 0:
            amount_to_rsch[abs(row.income).quantize(Decimal("0.01"))].append((idx, row))
        if row.expense != 0:
            amount_to_rsch[abs(row.expense).quantize(Decimal("0.01"))].append((idx, row))

    # ── for each Master, find & score candidates ─────────────
    master_assignments: list[tuple[int, int, float]] = []  # (master_idx, rsch_idx, score)

    for mi, mrow in enumerate(master_rows):
        target_amounts = set()
        if mrow.income != 0:
            target_amounts.add(abs(mrow.income).quantize(Decimal("0.01")))
        if mrow.expense != 0:
            target_amounts.add(abs(mrow.expense).quantize(Decimal("0.01")))

        candidates: list[tuple[float, int]] = []  # (score, rsch_idx)
        for amt in target_amounts:
            for ri, rrow in amount_to_rsch.get(amt, []):
                s = _score_pair(mrow, rrow)
                if s >= 0:
                    candidates.append((s, ri))

        if candidates:
            # Sort by score descending, pick the best
            candidates.sort(key=lambda x: -x[0])
            best_score, best_ri = candidates[0]
            master_assignments.append((mi, best_ri, best_score))
        else:
            # No candidate with matching amount
            master_assignments.append((mi, -1, -1.0))

    # ── greedy assign (by descending score) ──────────────────
    master_assignments.sort(key=lambda x: -x[2])
    final_pairs: dict[int, tuple[int, float]] = {}  # master_idx → (rsch_idx, score)

    for mi, ri, score in master_assignments:
        if ri < 0:
            continue
        if ri in used_rsch:
            # This RSCH already taken; try to find the next best
            mrow = master_rows[mi]
            target_amounts = set()
            if mrow.income != 0:
                target_amounts.add(abs(mrow.income).quantize(Decimal("0.01")))
            if mrow.expense != 0:
                target_amounts.add(abs(mrow.expense).quantize(Decimal("0.01")))
            remaining = [
                (s, ri2)
                for amt in target_amounts
                for ri2, _ in amount_to_rsch.get(amt, [])
                if ri2 not in used_rsch
                for s in [_score_pair(mrow, rsch_rows[ri2])]
                if s >= 0
            ]
            if remaining:
                remaining.sort(key=lambda x: -x[0])
                final_pairs[mi] = (remaining[0][1], remaining[0][0])
                used_rsch.add(remaining[0][1])
        else:
            final_pairs[mi] = (ri, score)
            used_rsch.add(ri)

    # ── build output ─────────────────────────────────────────
    matched_masters: set[int] = set()
    for mi, mrow in enumerate(master_rows):
        if mi in final_pairs:
            ri, score = final_pairs[mi]
            rrow = rsch_rows[ri]
            matched_masters.add(mi)

            if score >= 90:
                status, reason = STATUS_VERIFIED, ""
            elif score >= 40:
                status = STATUS_REVIEW
                reason = _pair_reason(mrow, rrow, score)
            else:
                status = STATUS_ERROR
                reason = _pair_reason(mrow, rrow, score)

            result.append(
                ReconciliationRow(
                    master=mrow,
                    rsch=rrow,
                    status=status,
                    reason=reason,
                )
            )
        else:
            result.append(
                ReconciliationRow(
                    master=mrow,
                    rsch=None,
                    status=STATUS_ERROR,
                    reason=REASON_NO_RSCH,
                )
            )

    # Unmatched RSCH rows
    for ri, rrow in enumerate(rsch_rows):
        if ri not in used_rsch:
            result.append(
                ReconciliationRow(
                    master=None,
                    rsch=rrow,
                    status=STATUS_ERROR,
                    reason=REASON_NO_CURATOR,
                )
            )

    return result


def _suppress_rsch_rows_matched_by_excluded_master_filters(
    rsch_rows: list[RschReconciliationRow],
    excluded_master_rows: list[MasterReconciliationRow],
) -> list[RschReconciliationRow]:
    if not excluded_master_rows:
        return rsch_rows

    suppressed_indexes: set[int] = set()
    for master_row in excluded_master_rows:
        candidates = [
            (idx, row) for idx, row in enumerate(rsch_rows) if idx not in suppressed_indexes
        ]
        # Score each candidate, pick the best
        best_idx: int | None = None
        best_score = -1.0
        for idx, row in candidates:
            s = _score_pair(master_row, row)
            if s > best_score:
                best_score = s
                best_idx = idx
        if best_idx is not None:
            suppressed_indexes.add(best_idx)

    if not suppressed_indexes:
        return rsch_rows
    return [row for idx, row in enumerate(rsch_rows) if idx not in suppressed_indexes]


def _rsch_values(row: Optional[RschReconciliationRow]) -> list[Any]:
    if row is None:
        return [None, None, None, None, None, None]
    return [
        _excel_safe_text(row.executor),
        _excel_safe_text(row.customer),
        _excel_safe_text(row.contractor),
        _excel_safe_text(row.comment),
        row.income if row.income != 0 else None,
        row.expense if row.expense != 0 else None,
    ]


def _master_values(row: ReconciliationRow, master_headers: list[str]) -> list[Any]:
    target_len = len(master_headers)
    if row.master is not None:
        vals = row.master.values
        if len(vals) < target_len:
            vals = list(vals) + [None] * (target_len - len(vals))
        elif len(vals) > target_len:
            vals = vals[:target_len]
        return [_excel_safe_text(value) for value in vals]
    values: list[Any] = [None for _ in master_headers]
    if values:
        values[0] = _excel_safe_text(row.reason)
    return values
