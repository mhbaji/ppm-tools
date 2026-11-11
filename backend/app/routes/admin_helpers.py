"""Supporting upload, validation, serialization, and legacy admin operations used by admin routes."""

from collections import defaultdict
from datetime import datetime
from io import BytesIO
import mimetypes
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from flask import (
    current_app,
    request,
    send_file,
)
from sqlalchemy import and_, event, exists, func, or_, select
from openpyxl import Workbook

from ..models import (
    BudgetDetail,
    AdminUpload,
    PerformanceResult,
    DatasetInfo,
    AffairField,
    Indicator,
    Activity,
    TaggingType,
    JobLevel,
    PackageGroup,
    Period,
    Program,
    RealizationUpload,
    Account,
    Unit,
    Department,
    FundingSource,
    Stage,
    Subactivity,
    OrganizationalUnit,
    SubactivityTagging,
    PerformanceTarget,
    Year,
    Affair,
    DirectoryLink,
)
from .common import (
    APIError,
    admin_required,
    escape_like,
    get_session,
    requested_stage_id,
    requested_year,
)

ADMIN_UPLOAD_KINDS = {"sub_kegiatan", "tagging_sub_kegiatan"}

def _year_id(database_session, year: int) -> int | None:
    """Look up the database identifier for a calendar year."""
    return database_session.scalar(select(Year.id).where(Year.name == year))

def _valid_year(value) -> bool:
    """Reject booleans and years outside the supported range."""
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and 1900 <= value <= 2200
    )

def _save_admin_upload(database_session, upload, file_bytes: bytes, kind: str):
    """Persist an uploaded workbook and clean it up if its transaction rolls back."""
    original_filename = upload.filename or "unggah.xlsx"
    stored_filename = f"{uuid4().hex}{Path(original_filename).suffix.lower()}"
    url = f"/api/admin/uploads/{kind}/{stored_filename}"
    upload_directory = Path(current_app.config["ADMIN_UPLOAD_DIR"])
    stored_path = upload_directory / stored_filename
    try:
        upload_directory.mkdir(parents=True, exist_ok=True)
        stored_path.write_bytes(file_bytes)
    except OSError as error:
        try:
            stored_path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            raise APIError(
                500,
                "File impor gagal disimpan dan file sementara gagal dibersihkan.",
            ) from cleanup_error
        raise APIError(500, "File impor tidak dapat disimpan ke storage.") from error

    def remove_file_after_rollback(session) -> None:
        """Remove the stored workbook when its metadata transaction fails."""
        stored_path.unlink(missing_ok=True)

    event.listen(
        database_session,
        "after_rollback",
        remove_file_after_rollback,
        once=True,
    )
    metadata = AdminUpload(
        kind=kind,
        original_filename=original_filename,
        file_type=(
            mimetypes.guess_type(original_filename)[0]
            or upload.mimetype
            or "application/octet-stream"
        ),
        file_size=len(file_bytes),
        url=url,
        uploaded_at=datetime.now(),
    )
    database_session.add(metadata)
    database_session.flush()
    return metadata

def _admin_upload_json(item: AdminUpload) -> dict[str, Any]:
    """Serialize upload metadata for the admin API response."""
    return {
        "id": item.id,
        "filename": item.original_filename,
        "file_type": item.file_type,
        "file_size": item.file_size,
        "uploaded_at": item.uploaded_at.isoformat(sep=" "),
        "url": item.url,
        "download_url": item.url,
    }

def _realization_statement(year_id: int, period_id: int, search: str):
    """Build the filtered query used to retrieve realization records."""
    work_code = func.coalesce(
        Program.code,
        Activity.code,
        Subactivity.code,
        OrganizationalUnit.code,
    )
    work_name = func.coalesce(
        Program.name,
        Activity.name,
        Subactivity.name,
        OrganizationalUnit.name,
    )
    normalized_level = func.lower(func.replace(JobLevel.name, "_", " "))
    latest_stage_id = (
        select(BudgetDetail.stage_id)
        .where(BudgetDetail.year_id == year_id)
        .order_by(BudgetDetail.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    budget = (
        select(func.sum(BudgetDetail.budget))
        .where(
            BudgetDetail.year_id == year_id,
            BudgetDetail.stage_id == latest_stage_id,
            BudgetDetail.organizational_unit_id
            == PerformanceTarget.organizational_unit_id,
            or_(
                normalized_level.in_(["sub unit", "subunit"]),
                and_(
                    normalized_level == "program",
                    BudgetDetail.program_id == PerformanceTarget.job_id,
                ),
                and_(
                    normalized_level == "kegiatan",
                    BudgetDetail.activity_id == PerformanceTarget.job_id,
                ),
                and_(
                    normalized_level == "sub kegiatan",
                    BudgetDetail.subactivity_id == PerformanceTarget.job_id,
                ),
            ),
        )
        .scalar_subquery()
    )
    statement = (
        select(
            PerformanceTarget.id,
            OrganizationalUnit.code,
            OrganizationalUnit.name,
            JobLevel.name.label("level"),
            work_code,
            work_name,
            Indicator.name,
            Unit.name,
            PerformanceTarget.target,
            PerformanceResult.achievement.label("achievement"),
            PerformanceResult.achievement_percentage.label("achievement_percentage"),
            budget,
            PerformanceResult.realized_budget.label("realization"),
        )
        .join(OrganizationalUnit, OrganizationalUnit.id == PerformanceTarget.organizational_unit_id)
        .join(JobLevel, JobLevel.id == PerformanceTarget.job_level_id)
        .outerjoin(
            Program,
            and_(
                normalized_level == "program",
                Program.id == PerformanceTarget.job_id,
            ),
        )
        .outerjoin(
            Activity,
            and_(
                normalized_level == "kegiatan",
                Activity.id == PerformanceTarget.job_id,
            ),
        )
        .outerjoin(
            Subactivity,
            and_(
                normalized_level == "sub kegiatan",
                Subactivity.id == PerformanceTarget.job_id,
            ),
        )
        .outerjoin(Indicator, Indicator.id == PerformanceTarget.indicator_id)
        .outerjoin(Unit, Unit.id == PerformanceTarget.unit_id)
        .outerjoin(
            PerformanceResult,
            and_(
                PerformanceResult.performance_target_id == PerformanceTarget.id,
                PerformanceResult.period_id == period_id,
            ),
        )
        .where(PerformanceTarget.year_id == year_id)
    )
    if search:
        pattern = f"%{escape_like(search)}%"
        statement = statement.where(
            or_(
                OrganizationalUnit.code.ilike(pattern, escape="\\"),
                OrganizationalUnit.name.ilike(pattern, escape="\\"),
                work_code.ilike(pattern, escape="\\"),
                work_name.ilike(pattern, escape="\\"),
                JobLevel.name.ilike(pattern, escape="\\"),
                Indicator.name.ilike(pattern, escape="\\"),
                Unit.name.ilike(pattern, escape="\\"),
            )
        )
    return statement.order_by(
        OrganizationalUnit.name,
        work_code,
        Indicator.name,
        Unit.name,
        PerformanceTarget.id,
    )

def _serialize_realization_rows(rows):
    """Convert realization query results into API-ready records."""
    return [
        {
            "pagu_id": row[0],
            "subunit_code": row[1],
            "subunit_name": row[2],
            "level": row[3],
            "work_code": row[4],
            "work_name": row[5],
            "indicator": row[6],
            "unit": row[7],
            "target": float(row[8]) if row[8] is not None else None,
            "achievement": float(row[9]) if row[9] is not None else None,
            "achievement_percentage": float(row[10]) if row[10] is not None else None,
            "budget": float(row[11]) if row[11] is not None else None,
            "realization": float(row[12]) if row[12] is not None else None,
        }
        for row in rows
    ]

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

def _format_export_sheet(worksheet) -> None:
    """Apply consistent sizing and filters to an exported worksheet."""
    worksheet.freeze_panes = "C2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for column in worksheet.columns:
        width = min(
            max(max(len(str(cell.value or "")) for cell in column) + 2, 12),
            60,
        )
        worksheet.column_dimensions[column[0].column_letter].width = width

def _year_has_data(database_session, year_id: int) -> bool:
    """Check whether a year is referenced by existing application data."""
    for model in (
        BudgetDetail,
        DatasetInfo,
        TaggingType,
        PackageGroup,
        Stage,
        SubactivityTagging,
        PerformanceTarget,
        RealizationUpload,
        Department,
        OrganizationalUnit,
        Affair,
        AffairField,
        Program,
        Activity,
        Subactivity,
        FundingSource,
        Account,
        DirectoryLink,
    ):
        if database_session.scalar(
            select(model.id).where(model.year_id == year_id).limit(1)
        ) is not None:
            return True
    return False

# Excel dibuat di browser; handler lama dipertahankan tanpa mendaftarkan endpoint unduhan.
@admin_required
def export_admin_tagging():
    """Retain the disabled admin tagging workbook response without registering a route."""
    search = request.args.get("q", "").strip()
    tagging_code_value = request.args.get("tagging_code", "")
    scope = request.args.get("scope", "sub_kegiatan")
    sheet_mode = request.args.get("sheet_mode", "single")
    if scope not in {"sub_kegiatan", "paket_kelompok"}:
        raise APIError(400, "Parameter scope tidak valid.")
    if sheet_mode not in {"single", "sub_unit"}:
        raise APIError(400, "Pilihan format sheet Excel tidak valid.")
    if tagging_code_value and not tagging_code_value.isdecimal():
        raise APIError(400, "Parameter tagging_code harus berupa ID jenis tagging.")

    with get_session() as database_session:
        year = requested_year(database_session)
        year_id = _year_id(database_session, year)
        stage_id = requested_stage_id(database_session, year)
        filters = [
            BudgetDetail.year_id == year_id,
            BudgetDetail.stage_id == stage_id,
        ]
        if search:
            pattern = f"%{escape_like(search)}%"
            filters.append(
                or_(
                    Subactivity.code.ilike(pattern, escape="\\"),
                    Subactivity.name.ilike(pattern, escape="\\"),
                )
            )
        statement = (
            select(
                OrganizationalUnit.code,
                OrganizationalUnit.name,
                Department.name,
                Subactivity.code,
                Subactivity.name,
            )
            .join(BudgetDetail, BudgetDetail.organizational_unit_id == OrganizationalUnit.id)
            .join(Subactivity, Subactivity.id == BudgetDetail.subactivity_id)
            .join(Department, Department.id == BudgetDetail.department_id)
            .where(*filters)
        )
        if scope == "paket_kelompok":
            statement = (
                statement.add_columns(PackageGroup.name)
                .join(
                    PackageGroup,
                    PackageGroup.id == BudgetDetail.package_group_id,
                )
            )
        if tagging_code_value:
            tagging_type = database_session.scalar(
                select(TaggingType).where(
                    TaggingType.code == int(tagging_code_value),
                    TaggingType.year_id == year_id,
                )
            )
            if tagging_type is None:
                raise APIError(400, "Jenis tagging tidak tersedia untuk tahun tersebut.")
            tag_filters = [
                SubactivityTagging.year_id == year_id,
                SubactivityTagging.tagging_type_id == tagging_type.id,
                SubactivityTagging.organizational_unit_id == OrganizationalUnit.id,
                SubactivityTagging.subactivity_id == Subactivity.id,
            ]
            if scope == "paket_kelompok":
                tag_filters.append(
                    SubactivityTagging.package_group_id == BudgetDetail.package_group_id
                )
            else:
                tag_filters.append(SubactivityTagging.package_group_id.is_(None))
            statement = statement.where(exists(select(1).where(*tag_filters)))

        statement = statement.distinct().order_by(
            OrganizationalUnit.name,
            Subactivity.name,
            PackageGroup.name if scope == "paket_kelompok" else Subactivity.name,
        )
        rows = database_session.execute(statement).all()
        tagging_rows = database_session.execute(
            select(
                SubactivityTagging.organizational_unit_id,
                OrganizationalUnit.code,
                Subactivity.code,
                SubactivityTagging.package_group_id,
                TaggingType.name,
            )
            .join(OrganizationalUnit, OrganizationalUnit.id == SubactivityTagging.organizational_unit_id)
            .join(Subactivity, Subactivity.id == SubactivityTagging.subactivity_id)
            .join(TaggingType, TaggingType.id == SubactivityTagging.tagging_type_id)
            .where(
                SubactivityTagging.year_id == year_id,
                SubactivityTagging.package_group_id.is_not(None)
                if scope == "paket_kelompok"
                else SubactivityTagging.package_group_id.is_(None),
            )
        ).all()
        tags_by_key: dict[tuple[str, str, int | None], list[str]] = defaultdict(list)
        for unit_id, unit_code, activity_code, package_id, tagging_name in tagging_rows:
            tags_by_key[(unit_code, activity_code, package_id)].append(tagging_name)

    workbook = Workbook()
    headers = (
        [
            "No",
            "Kode Sub Unit",
            "Perangkat Daerah",
            "Kode Sub Kegiatan",
            "Sub Kegiatan",
            "Paket/Kelompok",
            "Jenis Tagging",
        ]
        if scope == "paket_kelompok"
        else [
            "No",
            "Kode Sub Unit",
            "Perangkat Daerah",
            "Kode Sub Kegiatan",
            "Sub Kegiatan",
            "Jenis Tagging",
        ]
    )

    def append_tagging_rows(worksheet, values: list[Any]) -> None:
        """Write one tagging result set into an export worksheet."""
        worksheet.append(headers)
        for number, row in enumerate(values, start=1):
            key = (row[0], row[3], row[5] if scope == "paket_kelompok" else None)
            export_values = [number, row[0], row[1], row[3], row[4]]
            if scope == "paket_kelompok":
                export_values.append(row[5])
            export_values.append(", ".join(sorted(set(tags_by_key.get(key, [])))))
            worksheet.append([_excel_safe(value) for value in export_values])
        _format_export_sheet(worksheet)

    if sheet_mode == "single":
        append_tagging_rows(workbook.active, rows)
        workbook.active.title = "Tagging"
    else:
        grouped_rows: dict[tuple[str, str], list[Any]] = defaultdict(list)
        for row in rows:
            grouped_rows[(row[0], row[1])].append(row)
        used_titles: set[str] = set()
        for index, ((unit_code, unit_name), unit_rows) in enumerate(grouped_rows.items()):
            worksheet = workbook.active if index == 0 else workbook.create_sheet()
            worksheet.title = _safe_sheet_title(unit_name or unit_code, used_titles)
            append_tagging_rows(worksheet, unit_rows)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"tagging-{scope}-{year}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

_CATALOG_MODELS = {
    "level-pekerjaan": JobLevel,
    "indikator": Indicator,
    "satuan": Unit,
    "periode": Period,
}

_CATALOG_DEPENDENCIES = {
    "level-pekerjaan": (PerformanceTarget,),
    "indikator": (PerformanceTarget,),
    "satuan": (PerformanceTarget,),
    "periode": (PerformanceResult, RealizationUpload),
}

def _catalog_model(catalog: str):
    """Resolve a supported reference catalog to its ORM model."""
    model = _CATALOG_MODELS.get(catalog)
    if model is None:
        raise APIError(404, "Jenis data referensi tidak ditemukan.")
    return model

def _valid_name(value) -> bool:
    """Validate a non-empty reference name within the allowed length."""
    return isinstance(value, str) and bool(value.strip()) and len(value.strip()) <= 200

def _catalog_item_used(database_session, catalog: str, item_id: int) -> bool:
    """Check whether a reference item is still linked to imported records."""
    foreign_key_name = {
        "level-pekerjaan": "level_pekerjaan_id",
        "indikator": "indikator_id",
        "satuan": "satuan_id",
        "periode": "periode_id",
    }[catalog]
    return any(
        database_session.scalar(
            select(model.id)
            .where(getattr(model, foreign_key_name) == item_id)
            .limit(1)
        )
        is not None
        for model in _CATALOG_DEPENDENCIES[catalog]
    )

def _master_model(resource: str):
    """Resolve a supported department resource to its ORM model."""
    model = {"skpd": Department, "sub-unit": OrganizationalUnit}.get(resource)
    if model is None:
        raise APIError(404, "Jenis perangkat daerah tidak ditemukan.")
    return model

def _master_item_used(database_session, resource: str, item_id: int) -> bool:
    """Check whether a department resource is referenced by application data."""
    if resource == "skpd":
        references = ((BudgetDetail, BudgetDetail.department_id),)
    else:
        references = (
            (BudgetDetail, BudgetDetail.organizational_unit_id),
            (SubactivityTagging, SubactivityTagging.organizational_unit_id),
            (PerformanceTarget, PerformanceTarget.organizational_unit_id),
        )
    return any(
        database_session.scalar(
            select(model.id).where(column == item_id).limit(1)
        )
        is not None
        for model, column in references
    )

def _master_year_id(database_session, year) -> int:
    """Validate a year and require its database record to exist."""
    if not _valid_year(year):
        raise APIError(400, "Tahun harus berupa angka antara 1900 dan 2200.")
    year_id = _year_id(database_session, year)
    if year_id is None:
        raise APIError(400, "Tahun belum tersedia.")
    return year_id
