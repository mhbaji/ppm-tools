"""Parse and persist budget and tagging workbook imports."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import (
    BudgetDetail,
    AffairField,
    DatasetInfo,
    Activity,
    PackageGroup,
    Program,
    Account,
    Department,
    FundingSource,
    Subactivity,
    OrganizationalUnit,
    Stage,
    Year,
    Affair,
)


MAX_IMPORT_ROWS = 100_000
MAX_IMPORT_SIZE = 30 * 1024 * 1024

DIMENSION_COLUMNS = (
    (Department, "skpd_code", "skpd_name", "KODE SKPD", "NAMA SKPD"),
    (OrganizationalUnit, "sub_unit_code", "sub_unit_name", "KODE SUB UNIT", "NAMA SUB UNIT"),
    (Affair, "urusan_code", "urusan_name", "KODE URUSAN", "NAMA URUSAN"),
    (
        AffairField,
        "bidang_urusan_code",
        "bidang_urusan_name",
        "KODE BIDANG URUSAN",
        "NAMA BIDANG URUSAN",
    ),
    (Program, "program_code", "program_name", "KODE PROGRAM", "NAMA PROGRAM"),
    (Activity, "kegiatan_code", "kegiatan_name", "KODE KEGIATAN", "NAMA KEGIATAN"),
    (
        Subactivity,
        "sub_kegiatan_code",
        "sub_kegiatan_name",
        "KODE SUB KEGIATAN",
        "NAMA SUB KEGIATAN",
    ),
    (
        FundingSource,
        "sumber_dana_code",
        "sumber_dana_name",
        "KODE SUMBER DANA",
        "NAMA SUMBER DANA",
    ),
    (
        Account,
        "rekening_code",
        "rekening_name",
        "KODE REKENING",
        "NAMA REKENING",
    ),
)

REQUIRED_COLUMNS = {
    "KODE SUB UNIT",
    "NAMA SUB UNIT",
    "KODE URUSAN",
    "NAMA URUSAN",
    "KODE BIDANG URUSAN",
    "NAMA BIDANG URUSAN",
    "KODE PROGRAM",
    "NAMA PROGRAM",
    "KODE KEGIATAN",
    "NAMA KEGIATAN",
    "KODE SUB KEGIATAN",
    "NAMA SUB KEGIATAN",
    "PAGU",
}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    if not result:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return result


def _amount(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Nilai pagu tidak valid.")
    if isinstance(value, (int, float)):
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
            raise ValueError(f"Nilai pagu tidak valid: {value}.") from error
    if amount != amount.to_integral_value():
        raise ValueError(f"Nilai pagu harus bilangan bulat: {value}.")
    return int(amount)


def parse_budget_workbook(file_bytes: bytes, year: int) -> list[dict[str, Any]]:
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
            str(cell.value).strip().upper(): index
            for index, cell in enumerate(header_cells)
            if cell.value is not None
        }
        missing = REQUIRED_COLUMNS - headers.keys()
        if missing:
            raise ValueError(
                "Kolom Excel tidak lengkap: " + ", ".join(sorted(missing))
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

            def value(column: str) -> Any:
                index = headers.get(column)
                return values[index] if index is not None and index < len(values) else None

            row: dict[str, Any] = {"tahun": year}
            for model, code_field, name_field, code_name, column_name in DIMENSION_COLUMNS:
                code = _text(value(code_name))
                name = _text(value(column_name))
                if model is Department and code_name not in headers and column_name not in headers:
                    row[code_field] = None
                    row[name_field] = None
                    continue
                if model in {FundingSource, Account} and code is None and name is None:
                    row[code_field] = None
                    row[name_field] = None
                    continue
                if not code or not name:
                    raise ValueError(
                        f"Baris {row_number}: kode dan nama {column_name} wajib diisi."
                    )
                row[code_field] = code
                row[name_field] = name

            row["nama_paket_kelompok"] = _text(
                value("NAMA PAKET/KELOMPOK")
            ) or _text(value("PAKET/KELOMPOK"))
            row["pagu"] = _amount(value("PAGU"))
            rows.append(row)

        if not rows:
            raise ValueError("File Excel tidak berisi data anggaran.")
        return rows
    finally:
        workbook.close()


def parse_tagging_workbook(
    file_bytes: bytes,
    scope: str,
) -> list[dict[str, Any]]:
    if len(file_bytes) > MAX_IMPORT_SIZE:
        raise ValueError("Ukuran file maksimal 30 MB.")

    try:
        workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as error:
        raise ValueError("File Excel tidak dapat dibaca.") from error

    try:
        worksheet = workbook.active
        known_headers = {
            "KODE SUB UNIT", "KODE SUBUNIT", "NAMA SUB UNIT", "NAMA SUBUNIT",
            "KODE SUB KEGIATAN", "KODE SUBKEGIATAN", "NAMA SUB KEGIATAN",
            "NAMA SUBKEGIATAN", "PERANGKAT DAERAH", "KODE", "SUB KEGIATAN",
            "NAMA PERANGKAT DAERAH", "KODE SKPD", "KODE OPD", "SKPD",
            "NAMA SKPD", "OPD", "NAMA OPD", "SUB UNIT", "SUBUNIT",
        }
        headers: dict[str, int] = {}
        header_row = 1
        for row_index, header_cells in enumerate(
            worksheet.iter_rows(min_row=1, max_row=20, values_only=True), start=1
        ):
            candidate = {}
            for index, cell_value in enumerate(header_cells):
                if cell_value is not None and str(cell_value).strip():
                    key = " ".join(
                        str(cell_value).strip().upper().replace("_", " ").split()
                    )
                    candidate.setdefault(key, index)
            if len(known_headers & candidate.keys()) >= 2:
                headers, header_row = candidate, row_index
                break
        if not headers:
            raise ValueError(
                "Header tidak ditemukan. Gunakan kolom Perangkat Daerah, Kode, dan Sub Kegiatan."
            )
        organizational_unit_code_column = next(
            (
                headers[name]
                for name in (
                    "KODE SUB UNIT",
                    "KODE SUBUNIT",
                    "KODE SKPD",
                    "KODE OPD",
                )
                if name in headers
            ),
            None,
        )
        organizational_unit_name_column = headers.get(
            "NAMA SUB UNIT",
            headers.get(
                "NAMA SUBUNIT",
                headers.get(
                    "PERANGKAT DAERAH",
                    headers.get(
                        "NAMA PERANGKAT DAERAH",
                        headers.get(
                            "SUB UNIT",
                            headers.get(
                                "SUBUNIT",
                                headers.get(
                                    "NAMA SKPD",
                                    headers.get("SKPD", headers.get("NAMA OPD", headers.get("OPD"))),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        subactivity_code_column = next(
            (
                headers[name]
                for name in ("KODE SUB KEGIATAN", "KODE SUBKEGIATAN", "KODE")
                if name in headers
            ),
            None,
        )
        subactivity_name_column = next(
            (
                headers[name]
                for name in ("NAMA SUB KEGIATAN", "NAMA SUBKEGIATAN", "SUB KEGIATAN")
                if name in headers
            ),
            None,
        )
        package_column = headers.get("NAMA PAKET/KELOMPOK", headers.get("PAKET/KELOMPOK"))
        if (organizational_unit_code_column is None and organizational_unit_name_column is None) or (
            subactivity_code_column is None and subactivity_name_column is None
        ):
            raise ValueError(
                "File Excel harus memiliki kode atau nama sub unit dan sub kegiatan."
            )
        if scope == "paket_kelompok" and package_column is None:
            raise ValueError(
                "File Excel untuk tagging paket harus memiliki kolom NAMA PAKET/KELOMPOK."
            )

        records: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row_number, values in enumerate(
            worksheet.iter_rows(min_row=header_row + 1, values_only=True),
            start=header_row + 1,
        ):
            if row_number > MAX_IMPORT_ROWS + header_row:
                raise ValueError(f"File Excel maksimal {MAX_IMPORT_ROWS:,} baris data.")
            def value(column: int | None) -> Any:
                return values[column] if column is not None and column < len(values) else None

            organizational_unit_code = _text(value(organizational_unit_code_column))
            organizational_unit_name = _text(value(organizational_unit_name_column))
            subactivity_code = _text(value(subactivity_code_column))
            subactivity_name = _text(value(subactivity_name_column))
            package_name = (
                _text(value(package_column))
            )
            if not any((organizational_unit_code, organizational_unit_name, subactivity_code, subactivity_name)):
                continue
            if (organizational_unit_name or organizational_unit_code or "").isdigit() and (
                subactivity_code or subactivity_name or ""
            ).isdigit():
                continue
            if not (organizational_unit_code or organizational_unit_name) or not (
                subactivity_code or subactivity_name
            ):
                raise ValueError(
                    f"Baris {row_number}: sub unit dan sub kegiatan wajib diisi."
                )
            if scope == "paket_kelompok" and not package_name:
                raise ValueError(
                    f"Baris {row_number}: nama paket/kelompok wajib diisi untuk tagging paket."
                )
            normalized_package = package_name or ""
            unit_key = organizational_unit_code or f"name:{organizational_unit_name.casefold()}"
            activity_key = subactivity_code or f"name:{subactivity_name.casefold()}"
            records[(unit_key, activity_key, normalized_package)] = {
                "row_number": row_number,
                "sub_unit_code": organizational_unit_code,
                "sub_unit_name": organizational_unit_name,
                "sub_kegiatan_code": subactivity_code,
                "sub_kegiatan_name": subactivity_name,
                "paket_kelompok_name": normalized_package,
            }
        if not records:
            raise ValueError("File Excel tidak berisi data tagging.")
        return list(records.values())
    finally:
        workbook.close()


def save_budget_import(
    session: Session,
    rows: list[dict[str, Any]],
    year: int,
    stage_id: int,
) -> tuple[int, str]:
    year_record = session.scalar(select(Year).where(Year.name == year))
    if year_record is None:
        year_record = Year(name=year)
        session.add(year_record)
        session.flush()

    existing_mappings: dict[str, set[tuple[str, str]]] = {}
    for organizational_unit_code, department_code, department_name in session.execute(
        select(OrganizationalUnit.code, Department.code, Department.name)
        .join(BudgetDetail, BudgetDetail.department_id == Department.id)
        .join(OrganizationalUnit, OrganizationalUnit.id == BudgetDetail.organizational_unit_id)
        .where(BudgetDetail.year_id == year_record.id)
    ).all():
        existing_mappings.setdefault(organizational_unit_code, set()).add(
            (department_code, department_name)
        )

    for row in rows:
        if row["skpd_code"] is not None and row["skpd_name"] is not None:
            continue
        mappings = existing_mappings.get(row["sub_unit_code"], set())
        if len(mappings) > 1:
            raise ValueError(
                f"Sub unit {row['sub_unit_code']} memiliki lebih dari satu SKPD. "
                "Tambahkan kolom KODE SKPD dan NAMA SKPD pada file Excel."
            )
        if mappings:
            row["skpd_code"], row["skpd_name"] = next(iter(mappings))
            continue

        organizational_unit_code = row["sub_unit_code"]
        parts = organizational_unit_code.rsplit(".", 1)
        department_code = (
            f"{parts[0]}.0000"
            if len(parts) == 2 and parts[1] != "0000"
            else organizational_unit_code
        )
        existing_department = session.scalar(
            select(Department)
            .where(Department.code == department_code)
            .order_by(Department.year_id.desc())
        )
        if existing_department is None and department_code != organizational_unit_code:
            raise ValueError(
                f"SKPD untuk sub unit {organizational_unit_code} tidak dapat ditentukan. "
                "Tambahkan kolom KODE SKPD dan NAMA SKPD pada file Excel."
            )
        row["skpd_code"] = department_code
        row["skpd_name"] = (
            existing_department.name
            if existing_department is not None
            else row["sub_unit_name"]
        )

    dimension_values: dict[type, dict[str, str]] = {
        model: {} for model, *_ in DIMENSION_COLUMNS
    }
    for row in rows:
        for model, code_field, name_field, _, _ in DIMENSION_COLUMNS:
            code = row[code_field]
            name = row[name_field]
            if code is None or name is None:
                continue
            previous_name = dimension_values[model].get(code)
            if previous_name is not None and previous_name != name:
                raise ValueError(f"Kode {code} memiliki nama berbeda di file Excel.")
            dimension_values[model][code] = name

    stage = session.get(Stage, stage_id)
    if stage is None or stage.year_id != year_record.id:
        raise ValueError("Jenis tahapan tidak tersedia untuk tahun tersebut.")

    references: dict[type, dict[str, int]] = {}
    for model, values in dimension_values.items():
        references[model] = {}
        existing = {
            item.code: item
            for item in session.scalars(
                select(model).where(
                    model.year_id == year_record.id,
                    model.code.in_(values.keys()),
                )
            ).all()
        } if values else {}
        for code, name in values.items():
            item = existing.get(code)
            if item is None:
                item = model(code=code, name=name, year_id=year_record.id)
                session.add(item)
                session.flush()
            elif item.name != name:
                item.name = name
            references[model][code] = item.id

    packages: dict[str, int] = {}
    for name in {
        row["nama_paket_kelompok"]
        for row in rows
        if row["nama_paket_kelompok"]
    }:
        package = session.scalar(
            select(PackageGroup).where(
                PackageGroup.year_id == year_record.id,
                PackageGroup.name == name,
            )
        )
        if package is None:
            package = PackageGroup(name=name, year_id=year_record.id)
            session.add(package)
            session.flush()
        packages[name] = package.id

    session.execute(
        delete(BudgetDetail).where(
            BudgetDetail.year_id == year_record.id,
            BudgetDetail.stage_id == stage_id,
        )
    )
    imported_rows = []
    for row in rows:
        imported_rows.append(
            BudgetDetail(
                year_id=year_record.id,
                stage_id=stage_id,
                department_id=references[Department][row["skpd_code"]],
                organizational_unit_id=references[OrganizationalUnit][row["sub_unit_code"]],
                affair_id=references[Affair][row["urusan_code"]],
                affair_field_id=references[AffairField][row["bidang_urusan_code"]],
                program_id=references[Program][row["program_code"]],
                activity_id=references[Activity][row["kegiatan_code"]],
                subactivity_id=references[Subactivity][row["sub_kegiatan_code"]],
                funding_source_id=(
                    references[FundingSource].get(row["sumber_dana_code"])
                    if row["sumber_dana_code"]
                    else None
                ),
                account_id=(
                    references[Account].get(row["rekening_code"])
                    if row["rekening_code"]
                    else None
                ),
                package_group_id=(
                    packages.get(row["nama_paket_kelompok"])
                    if row["nama_paket_kelompok"]
                    else None
                ),
                budget=row["pagu"],
            )
        )
    session.add_all(imported_rows)

    data_info = session.scalar(
        select(DatasetInfo).where(
            DatasetInfo.year_id == year_record.id,
            DatasetInfo.stage_id == stage_id,
        )
    )
    if data_info is None:
        data_info = DatasetInfo(
            year_id=year_record.id,
            stage_id=stage_id,
            updated_at=datetime.now(),
        )
        session.add(data_info)
    else:
        data_info.updated_at = datetime.now()

    return len(imported_rows), stage.name
