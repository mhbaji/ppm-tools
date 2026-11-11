"""Query, workbook, and serialization helpers used by public API routes; disabled legacy handlers remain unregistered here."""

from collections import defaultdict
from io import BytesIO
import re
from typing import Any

from flask import jsonify, request, send_file
from openpyxl.cell import WriteOnlyCell
from openpyxl import Workbook
from sqlalchemy import and_, func, or_, select, tuple_

from ..models import (
    BudgetDetail,
    PerformanceResult,
    TaggingType,
    Activity,
    JobLevel,
    PackageGroup,
    Period,
    Program,
    Account,
    Department,
    FundingSource,
    Subactivity,
    OrganizationalUnit,
    SubactivityTagging,
    Stage,
    PerformanceTarget,
    Year,
)
from .common import (
    APIError,
    escape_like,
    get_search_filters,
    get_session,
    requested_stage_id,
    requested_year,
)

def _period_label(name: str) -> str:
    """Normalize realization period names for display."""
    value = name.strip()
    if value.casefold().startswith("realisasi "):
        value = value[len("realisasi "):].strip()
    if value.casefold().startswith("triwulan "):
        value = value[len("triwulan "):].strip()
    if value in {"1", "2", "3", "4"}:
        value = ("I", "II", "III", "IV")[int(value) - 1]
    return f"Triwulan {value}"

def _latest_realization(
    values: dict[str, float],
    periods: list[dict[str, Any]],
) -> float:
    """Return the most recent available realization amount."""
    return next(
        (
            values[period["name"]]
            for period in reversed(periods)
            if period["name"] in values
        ),
        0.0,
    )

def _public_tagging_data(
    session,
    year_id: int,
    stage_id: int,
    tagging_code: int | None,
    search: str,
    item_offset: int = 0,
    item_limit: int | None = None,
    sub_unit_codes: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], int]:
    """Build page details while aggregating summary data across all matches."""
    filters = [SubactivityTagging.year_id == year_id]
    if tagging_code is not None:
        filters.append(TaggingType.code == tagging_code)
    if sub_unit_codes:
        filters.append(OrganizationalUnit.code.in_(sub_unit_codes))
    if search:
        pattern = f"%{escape_like(search)}%"
        filters.append(
            or_(
                OrganizationalUnit.code.ilike(pattern, escape="\\"),
                OrganizationalUnit.name.ilike(pattern, escape="\\"),
                Department.name.ilike(pattern, escape="\\"),
                Subactivity.code.ilike(pattern, escape="\\"),
                Subactivity.name.ilike(pattern, escape="\\"),
                PackageGroup.name.ilike(pattern, escape="\\"),
                TaggingType.name.ilike(pattern, escape="\\"),
                BudgetDetail.package_group.has(
                    PackageGroup.name.ilike(pattern, escape="\\")
                ),
            )
        )

    statement = (
        select(
            SubactivityTagging.id,
            SubactivityTagging.organizational_unit_id,
            OrganizationalUnit.code,
            OrganizationalUnit.name,
            SubactivityTagging.subactivity_id,
            Subactivity.code,
            Subactivity.name,
            func.min(Department.name),
            SubactivityTagging.package_group_id,
            func.min(PackageGroup.name),
            TaggingType.code,
            TaggingType.name,
            func.sum(func.coalesce(BudgetDetail.budget, 0)),
        )
        .select_from(SubactivityTagging)
        .join(OrganizationalUnit, OrganizationalUnit.id == SubactivityTagging.organizational_unit_id)
        .join(Subactivity, Subactivity.id == SubactivityTagging.subactivity_id)
        .join(TaggingType, TaggingType.id == SubactivityTagging.tagging_type_id)
        .outerjoin(
            PackageGroup,
            PackageGroup.id == SubactivityTagging.package_group_id,
        )
        .join(
            BudgetDetail,
            and_(
                BudgetDetail.year_id == year_id,
                BudgetDetail.stage_id == stage_id,
                BudgetDetail.organizational_unit_id == SubactivityTagging.organizational_unit_id,
                BudgetDetail.subactivity_id == SubactivityTagging.subactivity_id,
                or_(
                    SubactivityTagging.package_group_id.is_(None),
                    BudgetDetail.package_group_id
                    == SubactivityTagging.package_group_id,
                ),
            ),
        )
        .join(Department, Department.id == BudgetDetail.department_id)
        .where(*filters)
        .group_by(
            SubactivityTagging.id,
            SubactivityTagging.organizational_unit_id,
            OrganizationalUnit.code,
            OrganizationalUnit.name,
            SubactivityTagging.subactivity_id,
            Subactivity.code,
            Subactivity.name,
            SubactivityTagging.package_group_id,
            TaggingType.code,
            TaggingType.name,
        )
        .order_by(
            func.min(Department.name),
            Subactivity.name,
            PackageGroup.name,
            TaggingType.name,
        )
    )
    rows = session.execute(statement).all()
    pairs = {(row[1], row[4]) for row in rows}
    realization_by_pair: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    level_id = session.scalar(
        select(JobLevel.id).where(
            func.lower(func.replace(JobLevel.name, "_", " ")) == "sub kegiatan"
        )
    )
    if pairs and level_id is not None:
        realization_rows = session.execute(
            select(
                PerformanceTarget.organizational_unit_id,
                PerformanceTarget.job_id,
                PerformanceResult.period_id,
                func.max(PerformanceResult.realized_budget),
            )
            .join(
                PerformanceResult,
                PerformanceResult.performance_target_id == PerformanceTarget.id,
            )
            .where(
                PerformanceTarget.year_id == year_id,
                PerformanceTarget.job_level_id == level_id,
                tuple_(
                    PerformanceTarget.organizational_unit_id,
                    PerformanceTarget.job_id,
                ).in_(pairs),
                PerformanceResult.realized_budget.is_not(None),
            )
            .group_by(
                PerformanceTarget.organizational_unit_id,
                PerformanceTarget.job_id,
                PerformanceResult.period_id,
            )
        ).all()
        period_names = dict(session.execute(select(Period.id, Period.name)).all())
        for unit_id, activity_id, period_id, amount in realization_rows:
            name = period_names.get(period_id, str(period_id))
            realization_by_pair[(unit_id, activity_id)][name] = float(amount or 0)

    item_rows = (
        rows
        if item_limit is None
        else rows[item_offset : item_offset + item_limit]
    )
    parent_keys = {
        (row[1], row[4])
        for row in item_rows
        if row[8] is None
    }
    children_by_parent: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    if parent_keys:
        package_rows = session.execute(
            select(
                BudgetDetail.organizational_unit_id,
                BudgetDetail.subactivity_id,
                PackageGroup.id,
                PackageGroup.name,
                func.sum(func.coalesce(BudgetDetail.budget, 0)),
            )
            .join(PackageGroup, PackageGroup.id == BudgetDetail.package_group_id)
            .where(
                BudgetDetail.year_id == year_id,
                BudgetDetail.stage_id == stage_id,
                BudgetDetail.package_group_id.is_not(None),
                tuple_(
                    BudgetDetail.organizational_unit_id,
                    BudgetDetail.subactivity_id,
                ).in_(parent_keys),
            )
            .group_by(
                BudgetDetail.organizational_unit_id,
                BudgetDetail.subactivity_id,
                PackageGroup.id,
                PackageGroup.name,
            )
            .order_by(PackageGroup.name)
        ).all()
        for unit_id, activity_id, package_id, package_name, budget in package_rows:
            children_by_parent[(unit_id, activity_id)].append(
                {
                    "id": f"package:{unit_id}:{activity_id}:{package_id}",
                    "sub_unit_id": unit_id,
                    "sub_kegiatan_id": activity_id,
                    "paket_kelompok_id": package_id,
                    "paket_kelompok_name": package_name,
                    "budget": int(budget or 0),
                }
            )

    periods = [
        {"id": period_id, "name": name, "label": _period_label(name)}
        for period_id, name in session.execute(
            select(Period.id, Period.name).order_by(Period.id)
        ).all()
    ]
    organizational_unit_ids: set[int] = set()
    subactivities: set[tuple[int, int]] = set()
    packages: set[tuple[int, int, int]] = set()
    activity_budgets: dict[tuple[int, int], int] = {}
    package_budgets: dict[tuple[int, int, int], int] = {}
    realization_totals = {item["name"]: 0.0 for item in periods}
    for row in rows:
        unit_id, activity_id = row[1], row[4]
        pair = (unit_id, activity_id)
        realization = realization_by_pair.get(pair, {})
        organizational_unit_ids.add(unit_id)
        subactivities.add(pair)
        budget = int(row[12] or 0)
        if row[8] is not None:
            package_key = (unit_id, activity_id, row[8])
            packages.add(package_key)
            package_budgets[package_key] = budget
        else:
            activity_budgets[pair] = budget
    for pair in subactivities:
        for name, amount in realization_by_pair.get(pair, {}).items():
            realization_totals[name] = realization_totals.get(name, 0) + amount
    budget = sum(activity_budgets.values()) + sum(
        amount
        for (unit_id, activity_id, _), amount in package_budgets.items()
        if (unit_id, activity_id) not in activity_budgets
    )
    realization_total = sum(
        _latest_realization(realization_by_pair.get(pair, {}), periods)
        for pair in subactivities
    )
    summary = {
        "opd_count": len(organizational_unit_ids),
        "sub_unit_count": len(organizational_unit_ids),
        "subactivity_count": len(subactivities),
        "package_count": len(packages),
        "budget": budget,
        "realization_total": realization_total,
        "realization_percentage": round(realization_total * 100 / budget, 2)
        if budget
        else 0,
        "realization_by_period": realization_totals,
    }
    items = []
    for row in item_rows:
        unit_id, activity_id = row[1], row[4]
        pair = (unit_id, activity_id)
        realization = realization_by_pair.get(pair, {})
        items.append(
            {
                "id": row[0],
                "sub_unit_id": unit_id,
                "sub_unit_code": row[2],
                "sub_unit_name": row[3],
                "sub_kegiatan_id": activity_id,
                "sub_kegiatan_code": row[5],
                "sub_kegiatan_name": row[6],
                "perangkat_daerah_name": row[3],
                "opd_name": row[7] or row[3],
                "paket_kelompok_id": row[8],
                "paket_kelompok_name": row[9],
                "tagging_code": row[10],
                "tagging_name": row[11],
                "budget": int(row[12] or 0),
                "realization_by_period": realization,
                "realization_total": _latest_realization(realization, periods),
                "children": children_by_parent.get(pair, [])
                if row[8] is None
                else [],
            }
        )
    return items, summary, periods, len(rows)

def _excel_safe(value):
    """Prevent spreadsheet cells from interpreting untrusted text as formulas."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value

def _safe_sheet_title(value: str, used: set[str]) -> str:
    """Create a unique Excel worksheet title within Excel naming limits."""
    base = re.sub(r"[\\/*?:\[\]]", "_", value).strip("'")[:31] or "Sub Unit"
    title = base
    suffix = 2
    while title.casefold() in used:
        ending = f" ({suffix})"
        title = f"{base[:31 - len(ending)]}{ending}"
        suffix += 1
    used.add(title.casefold())
    return title

def _format_export_sheet(worksheet, freeze_panes: str = "A2") -> None:
    """Apply consistent sizing and filters to an exported worksheet."""
    worksheet.freeze_panes = freeze_panes
    worksheet.auto_filter.ref = worksheet.dimensions
    for column in worksheet.columns:
        width = min(
            max(max(len(str(cell.value or "")) for cell in column) + 2, 12),
            60,
        )
        worksheet.column_dimensions[column[0].column_letter].width = width

# Excel dibuat di browser; handler lama dipertahankan tanpa mendaftarkan endpoint unduhan.
def export_public_tagging():
    """Retain the browser-replaced tagging workbook handler without registering a route."""
    code_value = request.args.get("tagging_code", "")
    sheet_mode = request.args.get("sheet_mode", "single")
    if code_value and not code_value.isdecimal():
        raise APIError(400, "Parameter tagging_code tidak valid.")
    if sheet_mode not in {"single", "sub_unit"}:
        raise APIError(400, "Pilihan format sheet Excel tidak valid.")
    with get_session() as session:
        year = requested_year(session)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        stage_id = requested_stage_id(session, year)
        items, summary, periods, _total = _public_tagging_data(
            session,
            year_id,
            stage_id,
            int(code_value) if code_value else None,
            request.args.get("q", "").strip(),
        )

    workbook = Workbook()
    headers = [
        "No",
        "Perangkat Daerah",
        "Kode Sub Kegiatan",
        "Sub Kegiatan",
        "Paket/Kelompok",
        "Anggaran",
        "Realisasi Total",
        *[item["label"] for item in periods],
    ]
    detail_rows = [
        [
            number,
            _excel_safe(item["perangkat_daerah_name"]),
            _excel_safe(item["sub_kegiatan_code"]),
            _excel_safe(item["sub_kegiatan_name"]),
            _excel_safe(item["paket_kelompok_name"]),
            item["budget"],
            item["realization_total"],
            *[
                item["realization_by_period"].get(period["name"])
                for period in periods
            ],
        ]
        for number, item in enumerate(items, start=1)
    ]
    summary_rows = [
        ["Ringkasan Tagging", year],
        ["Jumlah Sub Unit", summary["sub_unit_count"]],
        ["Jumlah sub kegiatan", summary["subactivity_count"]],
        ["Jumlah paket pekerjaan", summary["package_count"]],
        ["Anggaran", summary["budget"]],
        ["Realisasi total", summary["realization_total"]],
        ["Persentase Realisasi Total", summary["realization_percentage"]],
    ]
    summary_rows.extend(
        [
            period["label"],
            summary["realization_by_period"].get(period["name"], 0),
        ]
        for period in periods
    )
    if sheet_mode == "single":
        worksheet = workbook.active
        worksheet.title = "Daftar Tagging"
        for row in summary_rows:
            worksheet.append([_excel_safe(value) for value in row])
        worksheet.append([])
        header_row = worksheet.max_row + 1
        worksheet.append(headers)
        for row in detail_rows:
            worksheet.append(row)
        worksheet["B7"].number_format = '0.00"%"'
        worksheet.freeze_panes = f"A{header_row + 1}"
        worksheet.auto_filter.ref = f"A{header_row}:{worksheet.cell(worksheet.max_row, len(headers)).coordinate}"
        for column in worksheet.columns:
            width = min(
                max(len(str(cell.value or "")) for cell in column) + 2,
                60,
            )
            worksheet.column_dimensions[column[0].column_letter].width = max(width, 12)
    else:
        summary_sheet = workbook.active
        summary_sheet.title = "Ringkasan"
        for row in summary_rows:
            summary_sheet.append([_excel_safe(value) for value in row])
        summary_sheet["B7"].number_format = '0.00"%"'
        _format_export_sheet(summary_sheet)
        items_by_unit: dict[str, list[list[Any]]] = defaultdict(list)
        for row, item in zip(detail_rows, items):
            items_by_unit[item["sub_unit_name"]].append(row)
        used_titles = {"ringkasan"}
        for unit_name, unit_rows in items_by_unit.items():
            sheet = workbook.create_sheet(_safe_sheet_title(unit_name, used_titles))
            sheet.append(headers)
            for row in unit_rows:
                sheet.append(row)
            _format_export_sheet(sheet)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"tagging-{year}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# Dinamisasi Anggaran dinonaktifkan; pertahankan handler tanpa mendaftarkan endpoint.
def get_dynamic_budget():
    """Retain disabled budget-dynamicization logic without exposing an API endpoint."""
    organizational_unit_value = request.args.get("sub_unit_id", "")
    export_format = request.args.get("format", "")
    sheet_mode = request.args.get("sheet_mode", "single")
    search = request.args.get("q", "").strip()
    if export_format not in {"", "all", "excel"}:
        raise APIError(400, "Format unduhan dinamisasi anggaran tidak valid.")
    if sheet_mode not in {"single", "sub_unit"}:
        raise APIError(400, "Pilihan format sheet Excel tidak valid.")
    level_value = request.args.get("level", "rekening")
    level_depths = {
        "sub_unit": 0,
        "skpd": 0,
        "program": 1,
        "kegiatan": 2,
        "sub_kegiatan": 3,
        "paket": 4,
        "kelompok": 4,
        "rekening": 5,
    }
    if level_value not in level_depths:
        raise APIError(400, "Tingkat rincian dinamisasi anggaran tidak valid.")
    if organizational_unit_value and not organizational_unit_value.isdecimal():
        raise APIError(400, "Parameter sub_unit_id tidak valid.")
    try:
        limit = int(request.args.get("limit", "10"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise APIError(
            400, "Parameter limit dan offset harus berupa bilangan bulat."
        ) from error
    if not 1 <= limit <= 200 or offset < 0:
        raise APIError(400, "Limit harus 1–200 dan offset tidak boleh negatif.")

    with get_session() as session:
        year = requested_year(session)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        stages = session.execute(
            select(
                Stage.id,
                Stage.name,
                Stage.code,
            )
            .join(BudgetDetail, BudgetDetail.stage_id == Stage.id)
            .where(
                Stage.year_id == year_id,
                BudgetDetail.year_id == year_id,
            )
            .group_by(Stage.id, Stage.name, Stage.code)
            .order_by(Stage.code, Stage.id)
        ).all()
        organizational_units = session.execute(
            select(OrganizationalUnit.id, OrganizationalUnit.code, OrganizationalUnit.name)
            .join(BudgetDetail, BudgetDetail.organizational_unit_id == OrganizationalUnit.id)
            .where(BudgetDetail.year_id == year_id)
            .distinct()
            .order_by(OrganizationalUnit.name)
        ).all()
        filters = [BudgetDetail.year_id == year_id]
        search_filters = get_search_filters(search)
        if search_filters:
            filters.append(or_(*search_filters))
        if organizational_unit_value:
            organizational_unit_id = int(organizational_unit_value)
            if not any(item.id == organizational_unit_id for item in organizational_units):
                raise APIError(404, "Sub Unit tidak tersedia untuk tahun tersebut.")
            filters.append(BudgetDetail.organizational_unit_id == organizational_unit_id)
        group_columns = (
            BudgetDetail.organizational_unit_id,
            BudgetDetail.program_id,
            BudgetDetail.activity_id,
            BudgetDetail.subactivity_id,
        )
        total_groups = session.scalar(
            select(func.count()).select_from(
                select(*group_columns).where(*filters).distinct().subquery()
            )
        ) or 0
        if export_format == "all":
            limit = max(total_groups, 1)
            offset = 0
        group_keys = [
            tuple(row)
            for row in session.execute(
                select(*group_columns)
                .join(BudgetDetail.organizational_unit)
                .join(BudgetDetail.program)
                .join(BudgetDetail.activity)
                .join(BudgetDetail.subactivity)
                .where(*filters)
                .distinct()
                .order_by(
                    OrganizationalUnit.name,
                    Program.code,
                    Activity.code,
                    Subactivity.code,
                )
                .limit(limit)
                .offset(offset)
            ).all()
        ]
        record_filters = list(filters)
        if group_keys:
            record_filters.append(tuple_(*group_columns).in_(group_keys))
        else:
            record_filters.append(BudgetDetail.id == -1)
        records = session.execute(
            select(
                BudgetDetail,
                OrganizationalUnit,
                Program,
                Activity,
                Subactivity,
                PackageGroup,
                Account,
                FundingSource,
            )
            .join(BudgetDetail.organizational_unit)
            .join(BudgetDetail.program)
            .join(BudgetDetail.activity)
            .join(BudgetDetail.subactivity)
            .outerjoin(BudgetDetail.package_group)
            .outerjoin(BudgetDetail.account)
            .outerjoin(BudgetDetail.funding_source)
            .where(*record_filters)
            .order_by(
                OrganizationalUnit.name,
                Program.code,
                Activity.code,
                Subactivity.code,
                PackageGroup.name,
                Account.code,
                FundingSource.name,
                BudgetDetail.id,
            )
        ).all()

    stage_ids = [stage.id for stage in stages]
    roots: dict[tuple[str, int, int | None], dict[str, Any]] = {}

    def get_node(
        parent: dict[str, Any] | None,
        key: tuple[str, int, int | None],
        level: str,
        code: str | None,
        name: str,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Reuse a hierarchy node or create it at the requested level."""
        container = roots if parent is None else parent["children"]
        if key not in container:
            container[key] = {
                "level": level,
                "code": code,
                "name": name,
                "source": source,
                "amounts": {stage_id: 0 for stage_id in stage_ids},
                "children": {},
            }
        return container[key]

    for (
        budget,
        organizational_unit,
        program,
        activity,
        subactivity,
        package,
        account,
        source,
    ) in records:
        path = [
            get_node(
                None,
                ("sub_unit", organizational_unit.id, None),
                "sub_unit",
                organizational_unit.code,
                organizational_unit.name,
            ),
        ]
        path.append(
            get_node(
                path[-1],
                ("program", program.id, None),
                "program",
                program.code,
                program.name,
            )
        )
        path.append(
            get_node(
                path[-1],
                ("kegiatan", activity.id, None),
                "kegiatan",
                activity.code,
                activity.name,
            )
        )
        path.append(
            get_node(
                path[-1],
                ("sub_kegiatan", subactivity.id, None),
                "sub_kegiatan",
                subactivity.code,
                subactivity.name,
            )
        )
        if package is not None:
            path.append(
                get_node(
                    path[-1],
                    ("paket", package.id, None),
                    "paket",
                    None,
                    package.name,
                )
            )
        if account is not None:
            path.append(
                get_node(
                    path[-1],
                    (
                        "rekening",
                        account.id,
                        source.id if source is not None else None,
                    ),
                    "rekening",
                    account.code,
                    account.name,
                    source.name if source is not None else None,
                )
            )
        amount = budget.budget or 0
        for node in path:
            node["amounts"][budget.stage_id] += amount

    rows = []

    def flatten(
        node: dict[str, Any],
        depth: int = 0,
        organizational_unit_name: str | None = None,
    ) -> None:
        """Collect visible hierarchy rows while retaining their parent unit."""
        if export_format == "all" and depth > level_depths[level_value]:
            return
        if node["level"] == "sub_unit":
            organizational_unit_name = node["name"]
        rows.append(
            {
                "level": node["level"],
                "code": node["code"],
                "name": node["name"],
                "sub_unit_name": organizational_unit_name,
                "source": node["source"],
                "amounts": node["amounts"],
            }
        )
        for child in node["children"].values():
            flatten(child, depth + 1, organizational_unit_name)

    for root in roots.values():
        flatten(root)

    if export_format == "excel":
        workbook = Workbook()
        headers = [
            "Kode",
            "SKPD / Program / Kegiatan / Subkegiatan / Paket / Kelompok / Rekening",
            *[_excel_safe(stage.name) for stage in stages],
            "Sumber Dana",
        ]
        level_indent = {
            "sub_unit": 0,
            "program": 2,
            "kegiatan": 4,
            "sub_kegiatan": 6,
            "paket": 8,
            "rekening": 10,
        }
        def append_budget_rows(worksheet, values: list[dict[str, Any]]) -> None:
            """Write budget rows and stage amounts to an Excel worksheet."""
            worksheet.append(headers)
            for item in values:
                worksheet.append(
                    [
                    _excel_safe(item["code"]),
                    _excel_safe(
                        f"{' ' * level_indent.get(item['level'], 0)}{item['name']}"
                    ),
                    *[item["amounts"].get(stage.id, 0) for stage in stages],
                    _excel_safe(item["source"]),
                    ]
                )
            _format_export_sheet(worksheet, "C2")

        if sheet_mode == "single":
            worksheet = workbook.active
            worksheet.title = "Dinamisasi Anggaran"
            append_budget_rows(worksheet, rows)
        else:
            grouped_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for item in rows:
                grouped_rows[item["sub_unit_name"] or "Tanpa Sub Unit"].append(item)
            used_titles: set[str] = set()
            for index, (unit_name, unit_rows) in enumerate(grouped_rows.items()):
                worksheet = workbook.active if index == 0 else workbook.create_sheet()
                worksheet.title = _safe_sheet_title(unit_name, used_titles)
                append_budget_rows(worksheet, unit_rows)
        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"dynamic-budget-{year}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return jsonify({
        "year": year,
        "stages": [
            {"id": stage.id, "code": stage.code, "name": stage.name}
            for stage in stages
        ],
        "sub_units": [
            {"id": item.id, "code": item.code, "name": item.name}
            for item in organizational_units
        ],
        "total": total_groups,
        "limit": limit,
        "offset": offset,
        "rows": rows,
    })


def finish_budget_comparison_hierarchy(
    nodes: dict[tuple[Any, ...], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert comparison nodes into a nested hierarchy."""
    finished = []
    for node in nodes.values():
        node["children"] = finish_budget_comparison_hierarchy(
            node.pop("_children_by_key")
        )
        finished.append(node)
    return finished


def flatten_budget_comparison_hierarchy(
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Create ordered export rows from the comparison hierarchy."""
    rows = []
    for node in nodes:
        rows.append(
            {
                "code": node["code"],
                "name": node["name"],
                "hierarchy": node["hierarchy"],
                "depth": node["depth"],
                "level": node["level"],
                "has_children": bool(node["children"]),
                "sub_unit_name": node["sub_unit_name"],
                "amounts": node["amounts"],
            }
        )
        rows.extend(flatten_budget_comparison_hierarchy(node["children"]))
    return rows


def create_budget_export_sheet(
    workbook: Workbook,
    title: str,
    used_titles: set[str],
    headers: list[str],
):
    """Create a formatted budget-export worksheet with a safe title."""
    worksheet = workbook.create_sheet(
        title=_safe_sheet_title(title, used_titles)
    )
    worksheet.freeze_panes = "A2"
    for column, width in {"A": 18, "B": 72, "C": 20, "D": 28}.items():
        worksheet.column_dimensions[column].width = width
    worksheet.append([WriteOnlyCell(worksheet, value=value) for value in headers])
    return worksheet
