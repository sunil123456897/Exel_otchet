from __future__ import annotations
import re
from decimal import Decimal
from typing import Any, Callable, Optional
from openpyxl.worksheet.worksheet import Worksheet
from core.domain.data_loss_log import record_loss
from core.infra.excel_hyperlinks import extract_hyperlink_formula_parts
from ._types import MasterReconciliationRow, RschReconciliationRow, ReconciliationRow
from ._utils import (_to_decimal, _normalize_text, _is_total_row,
    _is_excluded_customer, _is_filter_header, _is_excluded_master_filter,
    _is_excluded_master_header, _is_excluded_rsch_comment, _excel_safe_text, STATUS_VERIFIED, STATUS_REVIEW, STATUS_ERROR,
    REASON_NO_CURATOR, REASON_NO_RSCH, REASON_AMOUNT_MISMATCH,
    REASON_EXECUTOR_MISMATCH, REASON_CUSTOMER_MISMATCH,
    _MASTER_HEADER_ALIASES,
    _text_tokens, _compact_text, _extract_canonical_customer,
    _customer_prefix_match)
from ._resolve import (_executor_matches, _row_amount_matches,
    _rsch_customer_matches, _rsch_customer_matches_weak)


def _customer_exact_or_alias_match(
    master_customer: str,
    rsch_row: RschReconciliationRow,
    alias_repo: Optional[Any] = None,
) -> bool:
    """Strict customer match for VERIFIED status.

    Returns True if any of the following holds:
    1. Exact text match (case-insensitive, whitespace-normalised) between
       master customer and any of rsch customer/contractor/comment, OR
    2. The canonical prefix of the master customer (name extracted before
       trailing noise — project number, INN, amount) equals the normalised
       rsch candidate. Handles curator cells like
       «Анастасия рекрутинг 529. ... ИНН ... сумма ...».
    3. An explicit alias exists in the alias repository — looked up by the
       canonical prefix (so one alias «анастасия рекрутинг» covers every
       noisy variant of that customer), falling back to the raw master text.

    Loose/substring matches do NOT qualify — those get REVIEW status
    so accountants can review and add aliases if appropriate.
    """
    if not master_customer:
        return False
    master_norm = _normalize_text(master_customer)
    if not master_norm:
        return False

    # Уровень 1 — точное совпадение нормализованного текста.
    for candidate in (rsch_row.customer, rsch_row.contractor, rsch_row.comment):
        if not candidate:
            continue
        cand_norm = _normalize_text(candidate)
        if cand_norm and cand_norm == master_norm:
            return True

    # Уровень 2 — авто-извлечение канонического префикса из «мусорной» строки.
    canonical = _extract_canonical_customer(master_customer)
    if canonical and canonical != master_norm:
        for candidate in (rsch_row.customer, rsch_row.contractor, rsch_row.comment):
            if not candidate:
                continue
            cand_norm = _normalize_text(candidate)
            # 2a — точное совпадение извлечённого префикса с rsch-кандидатом.
            if cand_norm and canonical == cand_norm:
                return True
            # 2b — rsch-имя является префиксом из целых токенов канонического
            # master (имя заказчика + хвост из юр.формы/контрагента). Покрывает
            # «Анастасия рекрутинг ООО Интернет Решения ИНН ...» ↔ «анастасия
            # рекрутинг».
            if cand_norm and _customer_prefix_match(canonical, candidate):
                return True

    # Уровень 3 — алиас по каноническому префиксу, затем по исходному тексту.
    if alias_repo is not None:
        keys = [canonical, master_customer] if canonical else [master_customer]
        for key in keys:
            for candidate in (rsch_row.customer, rsch_row.contractor):
                if candidate and alias_repo.is_alias(key, candidate):
                    return True
    return False


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
        values = [
            _master_cell_value(ws, row_idx, headers, header) for header in output_headers
        ]
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


def _find_best_rsch_match(
    master_row: MasterReconciliationRow,
    customer_candidates: list[tuple[int, RschReconciliationRow]],
    used_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    amount_candidates = [
        (idx, row)
        for idx, row in customer_candidates
        if idx not in used_indexes and _row_amount_matches(master_row, row)
    ]
    for idx, row in amount_candidates:
        if _executor_matches(master_row.executor, row.executor):
            return idx, row
    return None, None


def _find_likely_executor_mismatch(
    master_row: MasterReconciliationRow,
    customer_candidates: list[tuple[int, RschReconciliationRow]],
    used_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    for idx, row in customer_candidates:
        if idx not in used_indexes and _row_amount_matches(master_row, row):
            return idx, row
    return None, None


def _find_likely_rsch_mismatch(
    master_row: MasterReconciliationRow,
    customer_candidates: list[tuple[int, RschReconciliationRow]],
    used_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    for idx, row in customer_candidates:
        if idx not in used_indexes and _executor_matches(master_row.executor, row.executor):
            return idx, row
    return None, None


def _weak_customer_review_candidate_matches(
    master_row: MasterReconciliationRow,
    rsch_row: RschReconciliationRow,
) -> bool:
    return (
        _row_amount_matches(master_row, rsch_row)
        and _executor_matches(master_row.executor, rsch_row.executor)
        and _rsch_customer_matches_weak(master_row.customer, rsch_row)
    )


def _find_likely_customer_mismatch(
    master_idx: int,
    master_count: int,
    get_weak_candidates: Callable[[int], list[tuple[int, RschReconciliationRow]]],
    used_indexes: set[int],
    exact_master_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    candidates = [
        (idx, row)
        for idx, row in get_weak_candidates(master_idx)
        if idx not in used_indexes
    ]
    if len(candidates) != 1:
        return None, None

    candidate_idx, candidate = candidates[0]
    competing_masters = [
        idx
        for idx in range(master_count)
        if idx != master_idx
        and idx not in exact_master_indexes
        and any(
            other_candidate_idx == candidate_idx
            for other_candidate_idx, _ in get_weak_candidates(idx)
        )
    ]
    if competing_masters:
        return None, None
    return candidate_idx, candidate


def _surname_tokens(value: str) -> set[str]:
    raw = re.split(r"[^a-zа-яёA-ZА-ЯЁ]+", str(value))
    return {
        w.lower() for w in raw
        if len(w) >= 3 and w[0].isalpha() and w[0].upper() == w[0]
    }


def _customer_surname_matches(
    master_customer: str,
    rsch_row: RschReconciliationRow,
) -> bool:
    master_surnames = _surname_tokens(master_customer)
    if not master_surnames:
        return False
    rsch_text = f"{rsch_row.comment or ''} {rsch_row.contractor or ''}".lower()
    return any(surname in rsch_text for surname in master_surnames)


def _find_surname_rsch_match(
    master_row: MasterReconciliationRow,
    rsch_rows: list[RschReconciliationRow],
    used_indexes: set[int],
    amount_to_rsch: dict[Decimal, list[tuple[int, RschReconciliationRow]]],
) -> tuple[int | None, RschReconciliationRow | None]:
    target_amounts = set()
    if master_row.income != 0:
        target_amounts.add(abs(master_row.income).quantize(Decimal("0.01")))
    if master_row.expense != 0:
        target_amounts.add(abs(master_row.expense).quantize(Decimal("0.01")))

    amount_candidates = set()
    for amt in target_amounts:
        if amt in amount_to_rsch:
            for idx, _ in amount_to_rsch[amt]:
                amount_candidates.add(idx)

    candidates = [
        (idx, rsch_rows[idx])
        for idx in sorted(amount_candidates)
        if idx not in used_indexes
        and _row_amount_matches(master_row, rsch_rows[idx])
        and _executor_matches(master_row.executor, rsch_rows[idx].executor)
        and _customer_surname_matches(master_row.customer, rsch_rows[idx])
    ]
    if not candidates:
        return None, None
    return candidates[0]


def _build_reconciliation_rows(
    master_rows: list[MasterReconciliationRow],
    rsch_rows: list[RschReconciliationRow],
    alias_repo: Optional[Any] = None,
) -> list[ReconciliationRow]:
    result: list[ReconciliationRow] = []
    used_rsch_indexes: set[int] = set()
    exact_matches: dict[int, int] = {}

    from collections import defaultdict
    token_to_rsch: dict[str, list[tuple[int, RschReconciliationRow]]] = defaultdict(list)
    compact_to_rsch: dict[str, list[tuple[int, RschReconciliationRow]]] = defaultdict(list)
    norm_to_rsch: dict[str, list[tuple[int, RschReconciliationRow]]] = defaultdict(list)
    amount_to_rsch: dict[Decimal, list[tuple[int, RschReconciliationRow]]] = defaultdict(list)

    for idx, row in enumerate(rsch_rows):
        if row.income != 0:
            amount_to_rsch[abs(row.income).quantize(Decimal("0.01"))].append((idx, row))
        if row.expense != 0:
            amount_to_rsch[abs(row.expense).quantize(Decimal("0.01"))].append((idx, row))

        for candidate in (row.customer, row.contractor, row.comment):
            if not candidate:
                continue
            norm = _normalize_text(candidate)
            if norm:
                norm_to_rsch[norm].append((idx, row))
            comp = _compact_text(candidate)
            if comp:
                compact_to_rsch[comp].append((idx, row))
            for tok in _text_tokens(candidate):
                token_to_rsch[tok].append((idx, row))

    customer_candidates_by_master = []
    for master_row in master_rows:
        candidate_indices = set()
        master_tokens = _text_tokens(master_row.customer)
        for tok in master_tokens:
            if tok in token_to_rsch:
                for idx, _ in token_to_rsch[tok]:
                    candidate_indices.add(idx)

        master_comp = _compact_text(master_row.customer)
        if len(master_comp) >= 6:
            for comp_key, rows in compact_to_rsch.items():
                if len(comp_key) >= 6 and (master_comp in comp_key or comp_key in master_comp):
                    for idx, _ in rows:
                        candidate_indices.add(idx)

        master_norm = _normalize_text(master_row.customer)
        if master_norm:
            for norm_key, rows in norm_to_rsch.items():
                if norm_key and (master_norm in norm_key or norm_key in master_norm):
                    for idx, _ in rows:
                        candidate_indices.add(idx)

        cands = [
            (idx, rsch_rows[idx])
            for idx in sorted(candidate_indices)
            if _rsch_customer_matches(master_row.customer, rsch_rows[idx])
        ]
        customer_candidates_by_master.append(cands)

    weak_candidates_by_master: dict[int, list[tuple[int, RschReconciliationRow]]] = {}

    def get_weak_candidates(master_idx: int) -> list[tuple[int, RschReconciliationRow]]:
        candidates = weak_candidates_by_master.get(master_idx)
        if candidates is None:
            master_row = master_rows[master_idx]
            target_amounts = set()
            if master_row.income != 0:
                target_amounts.add(abs(master_row.income).quantize(Decimal("0.01")))
            if master_row.expense != 0:
                target_amounts.add(abs(master_row.expense).quantize(Decimal("0.01")))

            amount_candidates = set()
            for amt in target_amounts:
                if amt in amount_to_rsch:
                    for idx, _ in amount_to_rsch[amt]:
                        amount_candidates.add(idx)

            candidates = [
                (idx, rsch_rows[idx])
                for idx in sorted(amount_candidates)
                if _weak_customer_review_candidate_matches(master_row, rsch_rows[idx])
            ]
            weak_candidates_by_master[master_idx] = candidates
        return candidates

    for master_idx, master_row in enumerate(master_rows):
        match_idx, rsch_row = _find_best_rsch_match(
            master_row,
            customer_candidates_by_master[master_idx],
            used_rsch_indexes,
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            exact_matches[master_idx] = match_idx

    for master_idx, master_row in enumerate(master_rows):
        if master_idx in exact_matches:
            rsch_row = rsch_rows[exact_matches[master_idx]]
            executor_ok = _executor_matches(master_row.executor, rsch_row.executor)
            # VERIFIED requires strict customer match (exact or alias)
            # + amount (already guaranteed by exact_matches) + executor.
            # Loose customer match downgrades to REVIEW so accountants
            # can add an alias if appropriate.
            customer_strict = _customer_exact_or_alias_match(
                master_row.customer, rsch_row, alias_repo
            )
            if customer_strict and executor_ok:
                status, reason = STATUS_VERIFIED, ""
            elif not customer_strict:
                status, reason = STATUS_REVIEW, REASON_CUSTOMER_MISMATCH
            else:
                status, reason = STATUS_REVIEW, REASON_EXECUTOR_MISMATCH
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=status,
                    reason=reason,
                )
            )
            continue

        match_idx, rsch_row = _find_likely_executor_mismatch(
            master_row,
            customer_candidates_by_master[master_idx],
            used_rsch_indexes,
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_REVIEW,
                    reason=REASON_EXECUTOR_MISMATCH,
                )
            )
            continue

        match_idx, rsch_row = _find_likely_rsch_mismatch(
            master_row,
            customer_candidates_by_master[master_idx],
            used_rsch_indexes,
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_REVIEW,
                    reason=REASON_AMOUNT_MISMATCH,
                )
            )
            continue

        match_idx, rsch_row = _find_likely_customer_mismatch(
            master_idx,
            len(master_rows),
            get_weak_candidates,
            used_rsch_indexes,
            set(exact_matches),
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_REVIEW,
                    reason=REASON_CUSTOMER_MISMATCH,
                )
            )
            continue

        match_idx, rsch_row = _find_surname_rsch_match(
            master_row,
            rsch_rows,
            used_rsch_indexes,
            amount_to_rsch,
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_REVIEW,
                    reason=REASON_CUSTOMER_MISMATCH,
                )
            )
            continue

        result.append(
            ReconciliationRow(
                master=master_row,
                rsch=None,
                status=STATUS_ERROR,
                reason=REASON_NO_RSCH,
            )
        )

    for idx, row in enumerate(rsch_rows):
        if idx in used_rsch_indexes:
            continue
        result.append(
            ReconciliationRow(
                master=None,
                rsch=row,
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
            (idx, row)
            for idx, row in enumerate(rsch_rows)
            if idx not in suppressed_indexes
            and _rsch_customer_matches(master_row.customer, row)
        ]
        match_idx, _rsch_row = _find_best_rsch_match(
            master_row,
            candidates,
            suppressed_indexes,
        )
        if match_idx is not None:
            suppressed_indexes.add(match_idx)

    if not suppressed_indexes:
        return rsch_rows
    return [
        row
        for idx, row in enumerate(rsch_rows)
        if idx not in suppressed_indexes
    ]


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


