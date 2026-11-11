"""Parse and persist realization workbook imports."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .importing import MAX_IMPORT_ROWS, MAX_IMPORT_SIZE
from .models import (
    BudgetDetail,
    PerformanceResult,
    Indicator,
    Activity,
    JobLevel,
    Program,
    Unit,
    Subactivity,
    OrganizationalUnit,
    Year,
    PerformanceTarget,
)


WORK_MODELS = {
    "program": Program,
    "kegiatan": Activity,
    "sub_kegiatan": Subactivity,
}
WORK_CODE_LENGTHS = {7: "program", 12: "kegiatan", 17: "sub_kegiatan"}


def _normalized_header(value: Any) -> str:
    return " ".join(str(value).strip().upper().replace("_", " ").split())


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    if not result:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return result


def _decimal(value: Any, label: str, row_number: int) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"Baris {row_number}: nilai {label} tidak valid.")
    if isinstance(value, (int, float, Decimal)):
        amount = Decimal(str(value))
    else:
        normalized = str(value).strip().replace(" ", "")
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        elif normalized.count(".") > 1 or (
            "." in normalized and len(normalized.rsplit(".", 1)[1]) == 3
        ):
            normalized = normalized.replace(".", "")
        try:
            amount = Decimal(normalized)
        except InvalidOperation as error:
            raise ValueError(
                f"Baris {row_number}: nilai {label} tidak valid ({value})."
            ) from error
    if not amount.is_finite():
        raise ValueError(f"Baris {row_number}: nilai {label} tidak valid.")
    return amount


def parse_realization_workbook(file_bytes: bytes) -> list[dict[str, Any]]:
    if len(file_bytes) > MAX_IMPORT_SIZE:
        raise ValueError("Ukuran file maksimal 30 MB.")
    try:
        workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as error:
        raise ValueError("File Excel tidak dapat dibaca.") from error

    try:
        worksheet = workbook.active
        header_cells = next(worksheet.iter_rows(min_row=1, max_row=1))
        headers = {
            _normalized_header(cell.value): index
            for index, cell in enumerate(header_cells)
            if cell.value is not None
        }

        def find_header(*names: str) -> int | None:
            return next(
                (headers[_normalized_header(name)] for name in names
                 if _normalized_header(name) in headers),
                None,
            )

        def row_value(values: tuple[Any, ...], *names: str) -> Any:
            index = find_header(*names)
            return values[index] if index is not None and index < len(values) else None

        realization_column = find_header("REALISASI")
        subunit_code_column = find_header(
            "KODE SUB UNIT", "KODE SUBUNIT", "KODE SKPD", "KODE OPD"
        )
        subunit_name_column = find_header(
            "NAMA SUB UNIT",
            "NAMA SUBUNIT",
            "SUB UNIT",
            "SUBUNIT",
            "PERANGKAT DAERAH",
            "NAMA PERANGKAT DAERAH",
            "SKPD",
            "NAMA SKPD",
            "OPD",
            "NAMA OPD",
        )
        if realization_column is None:
            raise ValueError("File Excel harus memiliki kolom REALISASI.")
        if subunit_code_column is None and subunit_name_column is None:
            raise ValueError("File Excel harus memiliki KODE SUB UNIT atau NAMA SUB UNIT.")

        explicit_work_columns = {
            "program": (
                ("KODE PROGRAM",),
                ("NAMA PROGRAM", "PROGRAM"),
            ),
            "kegiatan": (
                ("KODE KEGIATAN",),
                ("NAMA KEGIATAN", "KEGIATAN"),
            ),
            "sub_kegiatan": (
                ("KODE SUB KEGIATAN", "KODE SUBKEGIATAN"),
                ("NAMA SUB KEGIATAN", "NAMA SUBKEGIATAN", "SUB KEGIATAN"),
            ),
        }
        has_work_columns = any(
            find_header(*code_names) is not None
            or find_header(*name_names) is not None
            for code_names, name_names in explicit_work_columns.values()
        )
        generic_code_column = find_header(
            "KODE PEKERJAAN",
            "KODE PROGRAM/KEGIATAN/SUB KEGIATAN",
            "KODE",
        )
        generic_name_column = find_header(
            "NAMA PEKERJAAN",
            "NAMA PROGRAM/KEGIATAN/SUB KEGIATAN",
            "NAMA KEGIATAN/PEKERJAAN",
            "PEKERJAAN",
        )
        if not has_work_columns and generic_code_column is None and generic_name_column is None:
            raise ValueError(
                "File Excel harus memiliki kode/nama program, kegiatan, sub kegiatan, "
                "atau pekerjaan."
            )

        rows: list[dict[str, Any]] = []
        for row_number, values in enumerate(
            worksheet.iter_rows(min_row=2, values_only=True),
            start=2,
        ):
            if row_number > MAX_IMPORT_ROWS + 1:
                raise ValueError(f"File Excel maksimal {MAX_IMPORT_ROWS:,} baris data.")
            if not any(value is not None and str(value).strip() for value in values):
                continue

            work_code = None
            work_name = None
            work_level = None
            for level in ("sub_kegiatan", "kegiatan", "program"):
                code_names, name_names = explicit_work_columns[level]
                code = _text(row_value(values, *code_names))
                name = _text(row_value(values, *name_names))
                if code or name:
                    work_code, work_name, work_level = code, name, level
                    break
            if work_code is None and work_name is None:
                work_code = _text(
                    row_value(
                        values,
                        "KODE PEKERJAAN",
                        "KODE PROGRAM/KEGIATAN/SUB KEGIATAN",
                        "KODE",
                    )
                )
                work_name = _text(
                    row_value(
                        values,
                        "NAMA PEKERJAAN",
                        "NAMA PROGRAM/KEGIATAN/SUB KEGIATAN",
                        "NAMA KEGIATAN/PEKERJAAN",
                        "PEKERJAAN",
                    )
                )
                work_level = _text(row_value(values, "LEVEL PEKERJAAN", "LEVEL"))

            target = _decimal(row_value(values, "TARGET"), "TARGET", row_number)
            indicator = _text(row_value(values, "INDIKATOR", "NAMA INDIKATOR"))
            unit = _text(row_value(values, "SATUAN", "NAMA SATUAN"))
            if target is not None and (not indicator or not unit):
                raise ValueError(
                    f"Baris {row_number}: INDIKATOR dan SATUAN wajib diisi jika TARGET tersedia."
                )

            subunit_code = _text(
                values[subunit_code_column]
                if subunit_code_column is not None
                and subunit_code_column < len(values)
                else None
            )
            subunit_name = _text(
                values[subunit_name_column]
                if subunit_name_column is not None
                and subunit_name_column < len(values)
                else None
            )
            realization = _decimal(
                row_value(values, "REALISASI"), "REALISASI", row_number
            )
            if not subunit_code and not subunit_name:
                raise ValueError(f"Baris {row_number}: sub unit wajib diisi.")
            if not work_code and not work_name:
                raise ValueError(f"Baris {row_number}: pekerjaan wajib diisi.")

            rows.append(
                {
                    "row_number": row_number,
                    "subunit_code": subunit_code,
                    "subunit_name": subunit_name,
                    "work_code": work_code,
                    "work_name": work_name,
                    "work_level": work_level,
                    "indicator": indicator,
                    "unit": unit,
                    "target": target,
                    "achievement": _decimal(
                        row_value(values, "CAPAIAN"), "CAPAIAN", row_number
                    ),
                    "achievement_percentage": _decimal(
                        row_value(values, "PERSENTASE CAPAIAN", "PERSENTASE_CAPAIAN"),
                        "PERSENTASE CAPAIAN",
                        row_number,
                    ),
                    "realization": realization,
                    "budget": _decimal(
                        row_value(values, "PAGU", "PAGU ANGGARAN", "ANGGARAN"),
                        "ANGGARAN",
                        row_number,
                    ),
                }
            )
        if not rows:
            raise ValueError("File Excel tidak berisi data realisasi.")
        return rows
    finally:
        workbook.close()


def _canonical_level(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().replace("_", " ").split())
    return {
        "program": "program",
        "kegiatan": "kegiatan",
        "sub kegiatan": "sub_kegiatan",
        "subkegiatan": "sub_kegiatan",
    }.get(normalized)


def _resolve_work(
    session: Session,
    year_id: int,
    code: str | None,
    name: str | None,
    explicit_level: str | None,
) -> tuple[str, Any] | None:
    level = _canonical_level(explicit_level)
    if level is None and code:
        level = WORK_CODE_LENGTHS.get(len(code))
    models = [WORK_MODELS[level]] if level else list(WORK_MODELS.values())
    matches = []
    for model in models:
        statement = select(model).where(model.year_id == year_id)
        if code:
            statement = statement.where(model.code == code)
        elif name:
            statement = statement.where(func.lower(model.name) == name.casefold())
        else:
            return None
        matches.extend(session.scalars(statement).all())
    if len(matches) != 1:
        return None
    item = matches[0]
    if name and item.name.strip().casefold() != name.strip().casefold():
        return ("name-mismatch", item)
    actual_level = next(
        name for name, model in WORK_MODELS.items() if isinstance(item, model)
    )
    return actual_level, item


def _budget_from_detail(
    session: Session,
    year_id: int,
    subunit_id: int,
    work_level: str,
    work_id: int,
) -> Decimal | None:
    stage_id = session.scalar(
        select(BudgetDetail.stage_id)
        .where(BudgetDetail.year_id == year_id)
        .order_by(BudgetDetail.id.desc())
        .limit(1)
    )
    if stage_id is None:
        return None
    work_column = {
        "program": BudgetDetail.program_id,
        "kegiatan": BudgetDetail.activity_id,
        "sub_kegiatan": BudgetDetail.subactivity_id,
    }[work_level]
    value = session.scalar(
        select(func.sum(BudgetDetail.budget)).where(
            BudgetDetail.year_id == year_id,
            BudgetDetail.stage_id == stage_id,
            BudgetDetail.organizational_unit_id == subunit_id,
            work_column == work_id,
        )
    )
    return Decimal(value) if value is not None else None


def save_realization_import(
    session: Session,
    rows: list[dict[str, Any]],
    year: int,
    period_id: int,
) -> tuple[int, list[str]]:
    year_record = session.scalar(select(Year).where(Year.name == year))
    if year_record is None:
        raise ValueError(f"Tahun {year} tidak tersedia.")
    levels = {
        _canonical_level(item.name): item
        for item in session.scalars(select(JobLevel)).all()
    }
    warnings: list[str] = []
    imported = 0

    for row in rows:
        row_number = row["row_number"]
        subunit_statement = select(OrganizationalUnit).where(OrganizationalUnit.year_id == year_record.id)
        if row["subunit_code"]:
            subunit_statement = subunit_statement.where(
                OrganizationalUnit.code == row["subunit_code"]
            )
        else:
            subunit_statement = subunit_statement.where(
                func.lower(OrganizationalUnit.name) == row["subunit_name"].casefold()
            )
        subunits = session.scalars(subunit_statement).all()
        if len(subunits) != 1:
            warnings.append(
                f"Baris {row_number}: sub unit "
                f"{row['subunit_code'] or row['subunit_name']} tidak ditemukan atau ambigu."
            )
            continue
        subunit = subunits[0]
        if (
            row["subunit_name"]
            and subunit.name.strip().casefold() != row["subunit_name"].strip().casefold()
        ):
            warnings.append(
                f"Baris {row_number}: nama sub unit berbeda; kode sub unit digunakan."
            )

        resolved_work = _resolve_work(
            session,
            year_record.id,
            row["work_code"],
            row["work_name"],
            row["work_level"],
        )
        if resolved_work is None:
            warnings.append(
                f"Baris {row_number}: pekerjaan "
                f"{row['work_code'] or row['work_name']} tidak ditemukan atau ambigu."
            )
            continue
        work_level, work = resolved_work
        if work_level == "name-mismatch":
            warnings.append(
                f"Baris {row_number}: nama pekerjaan berbeda; kode pekerjaan digunakan."
            )
            work_level = next(
                level for level, model in WORK_MODELS.items() if isinstance(work, model)
            )
        level = levels.get(work_level)
        if level is None:
            warnings.append(
                f"Baris {row_number}: master level pekerjaan '{work_level}' tidak tersedia."
            )
            continue

        if row["target"] is None:
            warnings.append(
                f"Baris {row_number}: realisasi tidak disimpan karena target kinerja "
                "tidak tersedia."
            )
            continue

        budget = _budget_from_detail(
            session, year_record.id, subunit.id, work_level, work.id
        )
        if budget is None:
            warnings.append(
                f"Baris {row_number}: pagu tidak ditemukan pada rincian APBD."
            )

        indicator = session.scalar(
            select(Indicator).where(
                func.lower(Indicator.name) == row["indicator"].casefold()
            )
        )
        if indicator is None:
            indicator = Indicator(name=row["indicator"].strip())
            session.add(indicator)
            session.flush()
        unit = session.scalar(
            select(Unit).where(func.lower(Unit.name) == row["unit"].casefold())
        )
        if unit is None:
            unit = Unit(name=row["unit"].strip())
            session.add(unit)
            session.flush()

        target_record = session.scalar(
            select(PerformanceTarget).where(
                PerformanceTarget.organizational_unit_id == subunit.id,
                PerformanceTarget.year_id == year_record.id,
                PerformanceTarget.job_id == work.id,
                PerformanceTarget.job_level_id == level.id,
                PerformanceTarget.indicator_id == indicator.id,
                PerformanceTarget.unit_id == unit.id,
            )
        )
        if target_record is None:
            target_record = PerformanceTarget(
                organizational_unit_id=subunit.id,
                year_id=year_record.id,
                job_id=work.id,
                job_level_id=level.id,
                indicator_id=indicator.id,
                unit_id=unit.id,
                target=row["target"],
            )
            session.add(target_record)
            session.flush()
        else:
            target_record.target = row["target"]

        achievement_record = session.scalar(
            select(PerformanceResult).where(
                PerformanceResult.performance_target_id == target_record.id,
                PerformanceResult.period_id == period_id,
            )
        )
        percentage = row.get("achievement_percentage")
        if percentage is None and row["achievement"] is not None and row["target"]:
            percentage = row["achievement"] * 100 / row["target"]
        if achievement_record is None:
            achievement_record = PerformanceResult(
                performance_target_id=target_record.id,
                period_id=period_id,
                achievement=row["achievement"],
                achievement_percentage=percentage,
                realized_budget=row["realization"],
            )
            session.add(achievement_record)
        else:
            if (
                row["achievement"] is not None
                and achievement_record.achievement is not None
                and achievement_record.achievement != row["achievement"]
            ):
                warnings.append(
                    f"Baris {row_number}: capaian periode yang sudah ada berbeda; "
                    "nilai tersimpan dipertahankan."
                )
            elif row["achievement"] is not None:
                achievement_record.achievement = row["achievement"]
            if percentage is not None:
                achievement_record.achievement_percentage = percentage
            if row["realization"] is not None:
                achievement_record.realized_budget = row["realization"]
        imported += 1

    return imported, warnings[:200]
