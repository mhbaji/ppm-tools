"""Migrate legacy SQLite data to the current English database schema."""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


MASTER_TABLES = (
    "skpd",
    "sub_unit",
    "urusan",
    "bidang_urusan",
    "program",
    "kegiatan",
    "sub_kegiatan",
    "sumber_dana",
    "rekening",
)

ENGLISH_TABLE_NAMES = {
    "admin_editable_note": "admin_notes",
    "admin_upload": "admin_uploads",
    "admin_user": "admin_users",
    "bidang_urusan": "affair_fields",
    "capaian_kinerja": "performance_results",
    "data_info": "dataset_info",
    "indikator": "indicators",
    "jenis_tagging": "tagging_types",
    "kegiatan": "activities",
    "level_pekerjaan": "job_levels",
    "paket_kelompok": "package_groups",
    "periode": "periods",
    "program": "programs",
    "realisasi_upload": "realization_uploads",
    "rekening": "accounts",
    "rincian_anggaran": "budget_details",
    "satuan": "units",
    "skpd": "departments",
    "skpd_alias": "department_aliases",
    "sub_kegiatan": "subactivities",
    "sub_unit": "organizational_units",
    "sumber_dana": "funding_sources",
    "tagging_subkegiatan": "subactivity_taggings",
    "tahapan": "stages",
    "tahun": "years",
    "target_kinerja": "performance_targets",
    "urusan": "affairs",
}

ENGLISH_COLUMN_NAMES = {
    "admin_uploads": {},
    "admin_users": {},
    "affair_fields": {"tahun_id": "year_id"},
    "activities": {"tahun_id": "year_id"},
    "accounts": {"tahun_id": "year_id"},
    "budget_details": {
        "tahun_id": "year_id",
        "tahapan_id": "stage_id",
        "skpd_id": "department_id",
        "sub_unit_id": "organizational_unit_id",
        "urusan_id": "affair_id",
        "bidang_urusan_id": "affair_field_id",
        "kegiatan_id": "activity_id",
        "sub_kegiatan_id": "subactivity_id",
        "sumber_dana_id": "funding_source_id",
        "rekening_id": "account_id",
        "paket_kelompok_id": "package_group_id",
        "pagu": "budget",
    },
    "dataset_info": {"tahun_id": "year_id", "tahapan_id": "stage_id"},
    "department_aliases": {"skpd_id": "department_id"},
    "departments": {"tahun_id": "year_id"},
    "funding_sources": {"tahun_id": "year_id"},
    "import_metadata": {"tahun_id": "year_id"},
    "job_levels": {},
    "indicators": {},
    "organizational_units": {"tahun_id": "year_id"},
    "package_groups": {"tahun_id": "year_id"},
    "performance_results": {
        "target_kinerja_id": "performance_target_id",
        "periode_id": "period_id",
        "capaian": "achievement",
        "persentase_capaian": "achievement_percentage",
        "realisasi_anggaran": "realized_budget",
    },
    "performance_targets": {
        "sub_unit_id": "organizational_unit_id",
        "tahun_id": "year_id",
        "pekerjaan_id": "job_id",
        "level_pekerjaan_id": "job_level_id",
        "indikator_id": "indicator_id",
        "satuan_id": "unit_id",
    },
    "periods": {},
    "programs": {"tahun_id": "year_id"},
    "realization_uploads": {"tahun_id": "year_id", "periode_id": "period_id"},
    "stages": {"tahun_id": "year_id"},
    "subactivities": {"tahun_id": "year_id"},
    "subactivity_taggings": {
        "tahun_id": "year_id",
        "sub_unit_id": "organizational_unit_id",
        "sub_kegiatan_id": "subactivity_id",
        "jenis_tagging_id": "tagging_type_id",
        "paket_kelompok_id": "package_group_id",
    },
    "tagging_types": {"tahun_id": "year_id"},
    "units": {},
    "affairs": {"tahun_id": "year_id"},
}


def initialize_database_file(database_path: Path, legacy_path: Path) -> bool:
    """Copy the existing database into a new, empty default database file."""
    if database_path.exists() and database_path.stat().st_size > 0:
        return False
    if not legacy_path.exists() or legacy_path.stat().st_size == 0:
        return False

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{database_path.name}.",
        suffix=".migrating",
        dir=database_path.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    source = sqlite3.connect(legacy_path)
    destination = sqlite3.connect(temporary_path)
    try:
        source.backup(destination)
        destination.close()
        destination = None
        os.replace(temporary_path, database_path)
    except Exception:
        if destination is not None:
            destination.close()
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        source.close()
    return True


def migrate_english_schema(database_path: Path) -> bool:
    """Rename legacy database tables and columns without changing their data."""
    if not database_path.exists() or database_path.stat().st_size == 0:
        return False

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not tables.intersection(ENGLISH_TABLE_NAMES):
            return False

        backup_path = database_path.with_suffix(
            database_path.suffix + ".before-english-schema"
        )
        if not backup_path.exists():
            backup = sqlite3.connect(backup_path)
            try:
                connection.backup(backup)
            finally:
                backup.close()

        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            for old_name, new_name in ENGLISH_TABLE_NAMES.items():
                if old_name in tables and new_name in tables:
                    raise RuntimeError(
                        f"Database contains both {old_name} and {new_name} tables."
                    )
                if old_name in tables:
                    connection.execute(
                        f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"'
                    )

            renamed_tables = {
                new_name
                for old_name, new_name in ENGLISH_TABLE_NAMES.items()
                if old_name in tables
            }
            for table, column_names in ENGLISH_COLUMN_NAMES.items():
                if table not in tables and table not in renamed_tables:
                    continue
                columns = _columns(connection, table)
                for old_name, new_name in column_names.items():
                    if old_name == new_name:
                        continue
                    if old_name in columns and new_name in columns:
                        raise RuntimeError(
                            f"Database table {table} contains both "
                            f"{old_name} and {new_name} columns."
                        )
                    if old_name in columns:
                        connection.execute(
                            f'ALTER TABLE "{table}" RENAME COLUMN '
                            f'"{old_name}" TO "{new_name}"'
                        )
                        columns.remove(old_name)
                        columns.add(new_name)

            connection.commit()
        except Exception:
            connection.rollback()
            raise

        connection.execute("PRAGMA foreign_keys = ON")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                f"English schema migration has invalid relationships: {violations[:5]}"
            )
        return True
    finally:
        connection.close()


def _rows(connection: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(f'SELECT * FROM "{table}"').fetchall()
    ]


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def migrate_database(database_path: Path) -> bool:
    if not database_path.exists():
        return False

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        if "apbd_anggaran" not in {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        } or "source_excel_row" not in _columns(connection, "apbd_anggaran"):
            return False

        budgets = _rows(connection, "apbd_anggaran")
        dimension_rows = {
            table: _rows(connection, table)
            for table in MASTER_TABLES
        }
        tagging_type = _rows(connection, "jenis_tagging")
        tagging_rows = _rows(connection, "tagging_subkegiatan")
        stages = _rows(connection, "tahapan")
        import_metadata = _rows(connection, "import_metadata")
        admin_notes = _rows(connection, "admin_editable_note")

        years = sorted(
            {int(row["tahun"]) for row in budgets}
            | {int(row["tahun"]) for rows in dimension_rows.values() for row in rows}
            | {int(row["tahun"]) for row in tagging_type}
            | {int(row["tahun"]) for row in tagging_rows}
            | {int(row["tahun"]) for row in import_metadata}
        )
        now = datetime.now().replace(microsecond=0).isoformat(sep=" ")
        backup_path = database_path.with_suffix(
            database_path.suffix + ".before-id-schema"
        )
        if not backup_path.exists():
            backup = sqlite3.connect(backup_path)
            try:
                connection.backup(backup)
            finally:
                backup.close()

        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table in (
                "tagging_subkegiatan",
                "apbd_anggaran",
                "jenis_tagging",
                "tahapan",
                "import_metadata",
                "paket_kelompok",
                "data_info",
                *MASTER_TABLES,
                "tahun",
                "admin_editable_note",
            ):
                connection.execute(f'DROP TABLE IF EXISTS "{table}"')

            connection.execute(
                "CREATE TABLE tahun ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name INTEGER NOT NULL UNIQUE)"
            )
            year_ids: dict[int, int] = {}
            for year in years:
                cursor = connection.execute(
                    "INSERT INTO tahun(name) VALUES (?)", (year,)
                )
                year_ids[year] = int(cursor.lastrowid)

            for table in MASTER_TABLES:
                connection.execute(
                    f'CREATE TABLE "{table}" ('
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "code TEXT NOT NULL, "
                    "name TEXT NOT NULL, "
                    "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                    "UNIQUE(code, tahun_id))"
                )

            master_ids: dict[str, dict[tuple[str, int], int]] = {}
            for table in MASTER_TABLES:
                master_ids[table] = {}
                for row in dimension_rows[table]:
                    year = int(row["tahun"])
                    cursor = connection.execute(
                        f'INSERT INTO "{table}"(code,name,tahun_id) VALUES (?,?,?)',
                        (row["code"], row["name"].strip(), year_ids[year]),
                    )
                    master_ids[table][(row["code"], year)] = int(cursor.lastrowid)

            connection.execute(
                "CREATE TABLE paket_kelompok ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT NOT NULL, "
                "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                "UNIQUE(name, tahun_id))"
            )
            package_ids: dict[tuple[str, int], int] = {}
            for row in budgets:
                name = (row["nama_paket_kelompok"] or "").strip()
                if not name:
                    continue
                year = int(row["tahun"])
                key = (name, year)
                if key not in package_ids:
                    cursor = connection.execute(
                        "INSERT INTO paket_kelompok(name,tahun_id) VALUES (?,?)",
                        (name, year_ids[year]),
                    )
                    package_ids[key] = int(cursor.lastrowid)

            connection.execute(
                "CREATE TABLE tahapan ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "code INTEGER NOT NULL, "
                "name TEXT NOT NULL, "
                "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                "UNIQUE(code,tahun_id), "
                "UNIQUE(name,tahun_id))"
            )
            budget_year_by_stage: dict[int, int] = {}
            for budget in budgets:
                budget_year_by_stage.setdefault(
                    int(budget["tahapan_id"]), int(budget["tahun"])
                )
            stage_ids: dict[tuple[int, int], int] = {}
            for index, stage in enumerate(sorted(stages, key=lambda row: row["id"]), 1):
                old_id = int(stage["id"])
                year = budget_year_by_stage.get(old_id, years[0] if years else 0)
                if not year:
                    continue
                connection.execute(
                    "INSERT INTO tahapan(id,code,name,tahun_id) VALUES (?,?,?,?)",
                    (old_id, index, stage["name"], year_ids[year]),
                )
                stage_ids[(old_id, year)] = old_id

            connection.execute(
                "CREATE TABLE jenis_tagging ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "code INTEGER NOT NULL UNIQUE, "
                "name TEXT NOT NULL, "
                "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                "UNIQUE(name,tahun_id))"
            )
            tagging_type_ids: dict[tuple[int, int], int] = {}
            for row in tagging_type:
                code = int(row["code"])
                year = int(row["tahun"])
                connection.execute(
                    "INSERT INTO jenis_tagging(id,code,name,tahun_id) VALUES (?,?,?,?)",
                    (code, code, row["name"].strip(), year_ids[year]),
                )
                tagging_type_ids[(code, year)] = code

            connection.execute(
                "CREATE TABLE apbd_anggaran ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                "tahapan_id INTEGER NOT NULL REFERENCES tahapan(id), "
                "skpd_id INTEGER NOT NULL REFERENCES skpd(id), "
                "sub_unit_id INTEGER NOT NULL REFERENCES sub_unit(id), "
                "urusan_id INTEGER NOT NULL REFERENCES urusan(id), "
                "bidang_urusan_id INTEGER NOT NULL REFERENCES bidang_urusan(id), "
                "program_id INTEGER NOT NULL REFERENCES program(id), "
                "kegiatan_id INTEGER NOT NULL REFERENCES kegiatan(id), "
                "sub_kegiatan_id INTEGER NOT NULL REFERENCES sub_kegiatan(id), "
                "sumber_dana_id INTEGER REFERENCES sumber_dana(id), "
                "rekening_id INTEGER REFERENCES rekening(id), "
                "paket_kelompok_id INTEGER REFERENCES paket_kelompok(id), "
                "pagu INTEGER)"
            )
            subunit_by_subactivity: dict[tuple[str, int], int] = {}
            for row in budgets:
                year = int(row["tahun"])
                key = lambda table, field: master_ids[table][(row[field], year)]
                stage_id = stage_ids[(int(row["tahapan_id"]), year)]
                package_name = (row["nama_paket_kelompok"] or "").strip()
                package_id = package_ids.get((package_name, year)) if package_name else None
                connection.execute(
                    "INSERT INTO apbd_anggaran("
                    "id,tahun_id,tahapan_id,skpd_id,sub_unit_id,urusan_id,"
                    "bidang_urusan_id,program_id,kegiatan_id,sub_kegiatan_id,"
                    "sumber_dana_id,rekening_id,paket_kelompok_id,pagu"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        int(row["id"]),
                        year_ids[year],
                        stage_id,
                        key("skpd", "skpd_code"),
                        key("sub_unit", "sub_unit_code"),
                        key("urusan", "urusan_code"),
                        key("bidang_urusan", "bidang_urusan_code"),
                        key("program", "program_code"),
                        key("kegiatan", "kegiatan_code"),
                        key("sub_kegiatan", "sub_kegiatan_code"),
                        master_ids["sumber_dana"].get((row["sumber_dana_code"], year))
                        if row["sumber_dana_code"]
                        else None,
                        master_ids["rekening"].get((row["rekening_code"], year))
                        if row["rekening_code"]
                        else None,
                        package_id,
                        row["pagu"],
                    ),
                )
                subunit_by_subactivity.setdefault(
                    (row["sub_kegiatan_code"], year),
                    key("sub_unit", "sub_unit_code"),
                )

            connection.execute(
                "CREATE TABLE tagging_subkegiatan ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                "sub_unit_id INTEGER NOT NULL REFERENCES sub_unit(id), "
                "sub_kegiatan_id INTEGER NOT NULL REFERENCES sub_kegiatan(id), "
                "jenis_tagging_id INTEGER NOT NULL REFERENCES jenis_tagging(id), "
                "paket_kelompok_id INTEGER REFERENCES paket_kelompok(id))"
            )
            for row in tagging_rows:
                year = int(row["tahun"])
                subactivity_id = master_ids["sub_kegiatan"].get(
                    (row["subkegiatan_code"], year)
                )
                subunit_id = subunit_by_subactivity.get((row["subkegiatan_code"], year))
                tagging_type_id = tagging_type_ids.get(
                    (int(row["tagging_code"]), year)
                )
                if subactivity_id and subunit_id and tagging_type_id:
                    connection.execute(
                        "INSERT INTO tagging_subkegiatan("
                        "tahun_id,sub_unit_id,sub_kegiatan_id,jenis_tagging_id,paket_kelompok_id"
                        ") VALUES (?,?,?,?,NULL)",
                        (
                            year_ids[year],
                            subunit_id,
                            subactivity_id,
                            tagging_type_id,
                        ),
                    )

            connection.execute(
                "CREATE TABLE data_info ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                "tahapan_id INTEGER NOT NULL REFERENCES tahapan(id), "
                "updated_at TEXT NOT NULL, "
                "UNIQUE(tahun_id,tahapan_id))"
            )
            for year, stage_id in sorted(
                {
                    (int(row["tahun"]), int(row["tahapan_id"]))
                    for row in budgets
                }
            ):
                connection.execute(
                    "INSERT INTO data_info(tahun_id,tahapan_id,updated_at) VALUES (?,?,?)",
                    (year_ids[year], stage_id, now),
                )

            connection.execute(
                "CREATE TABLE import_metadata ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "key TEXT NOT NULL UNIQUE, "
                "value TEXT NOT NULL, "
                "tahun_id INTEGER NOT NULL REFERENCES tahun(id))"
            )
            for row in import_metadata:
                year = int(row["tahun"])
                connection.execute(
                    "INSERT INTO import_metadata(key,value,tahun_id) VALUES (?,?,?)",
                    (row["key"], row["value"], year_ids[year]),
                )

            connection.execute(
                "CREATE TABLE admin_editable_note ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "key TEXT NOT NULL UNIQUE, "
                "description TEXT NOT NULL)"
            )
            for row in admin_notes:
                connection.execute(
                    "INSERT INTO admin_editable_note(key,description) VALUES (?,?)",
                    (row["key"], row["description"]),
                )

            connection.commit()
        except Exception:
            connection.rollback()
            raise

        connection.execute("PRAGMA foreign_keys = ON")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"Skema migrasi memiliki relasi tidak valid: {violations[:5]}")
        return True
    finally:
        connection.close()


def migrate_feature_schema(database_path: Path) -> None:
    if not database_path.exists():
        return

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        legacy_financial_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }.intersection({"pagu_anggaran", "realisasi_anggaran"})
        has_legacy_financial_data = any(
            connection.execute(
                f'SELECT 1 FROM "{table}" LIMIT 1'
            ).fetchone()
            is not None
            for table in legacy_financial_tables
        )
        backup_path = database_path.with_suffix(
            database_path.suffix + ".before-financial-consolidation"
        )
        if has_legacy_financial_data and not backup_path.exists():
            backup = sqlite3.connect(backup_path)
            try:
                connection.backup(backup)
            finally:
                backup.close()

        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        views = {
            row["name"]: row["sql"] or ""
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='view'"
            )
        }
        if "apbd_anggaran" in tables and "rincian_anggaran" in tables:
            raise RuntimeError(
                "Database memiliki tabel apbd_anggaran dan rincian_anggaran sekaligus."
            )
        if "apbd_anggaran" in tables:
            for name, sql in views.items():
                if "apbd_anggaran" in sql.casefold():
                    connection.execute(f'DROP VIEW "{name}"')
            connection.execute(
                "ALTER TABLE apbd_anggaran RENAME TO rincian_anggaran"
            )

        if "pagu_anggaran" in tables:
            columns = _columns(connection, "pagu_anggaran")
            if "pekerjaan_id" not in columns and "program_id" in columns:
                rows = _rows(connection, "pagu_anggaran")
                connection.execute(
                    "CREATE TABLE pagu_anggaran_new ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "sub_unit_id INTEGER NOT NULL REFERENCES sub_unit(id), "
                    "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                    "pekerjaan_id INTEGER NOT NULL, "
                    "level_pekerjaan_id INTEGER NOT NULL REFERENCES level_pekerjaan(id), "
                    "pagu NUMERIC(20,2) NOT NULL)"
                )
                for row in rows:
                    work_ids = [
                        row.get("program_id"),
                        row.get("kegiatan_id"),
                        row.get("sub_kegiatan_id"),
                    ]
                    work_id = next((value for value in work_ids if value is not None), None)
                    if work_id is None or sum(value is not None for value in work_ids) != 1:
                        raise RuntimeError(
                            f"Baris pagu_anggaran {row['id']} tidak memiliki satu pekerjaan."
                        )
                    connection.execute(
                        "INSERT INTO pagu_anggaran_new("
                        "id,sub_unit_id,tahun_id,pekerjaan_id,level_pekerjaan_id,pagu"
                        ") VALUES (?,?,?,?,?,?)",
                        (
                            row["id"],
                            row["sub_unit_id"],
                            row["tahun_id"],
                            work_id,
                            row["level_pekerjaan_id"],
                            row["pagu"],
                        ),
                    )
                connection.execute("DROP TABLE pagu_anggaran")
                connection.execute(
                    "ALTER TABLE pagu_anggaran_new RENAME TO pagu_anggaran"
                )

        if "target_kinerja" in tables:
            columns = _columns(connection, "target_kinerja")
            if "pekerjaan_id" not in columns and "program_id" in columns:
                rows = _rows(connection, "target_kinerja")
                connection.execute(
                    "CREATE TABLE target_kinerja_new ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "sub_unit_id INTEGER NOT NULL REFERENCES sub_unit(id), "
                    "tahun_id INTEGER NOT NULL REFERENCES tahun(id), "
                    "pekerjaan_id INTEGER NOT NULL, "
                    "level_pekerjaan_id INTEGER NOT NULL REFERENCES level_pekerjaan(id), "
                    "indikator_id INTEGER NOT NULL REFERENCES indikator(id), "
                    "satuan_id INTEGER NOT NULL REFERENCES satuan(id), "
                    "target NUMERIC(20,4) NOT NULL)"
                )
                for row in rows:
                    work_ids = [row.get("program_id"), row.get("sub_kegiatan_id")]
                    work_id = next((value for value in work_ids if value is not None), None)
                    if work_id is None or sum(value is not None for value in work_ids) != 1:
                        raise RuntimeError(
                            f"Baris target_kinerja {row['id']} tidak memiliki satu pekerjaan."
                        )
                    connection.execute(
                        "INSERT INTO target_kinerja_new("
                        "id,sub_unit_id,tahun_id,pekerjaan_id,level_pekerjaan_id,"
                        "indikator_id,satuan_id,target) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            row["id"],
                            row["sub_unit_id"],
                            row["tahun_id"],
                            work_id,
                            row["level_pekerjaan_id"],
                            row["indikator_id"],
                            row["satuan_id"],
                            row["target"],
                        ),
                    )
                connection.execute("DROP TABLE target_kinerja")
                connection.execute(
                    "ALTER TABLE target_kinerja_new RENAME TO target_kinerja"
                )

        if "capaian_kinerja" in tables and "target_kinerja" in tables:
            columns = _columns(connection, "capaian_kinerja")
            achievement_column = next(
                (row for row in connection.execute(
                    'PRAGMA table_info("capaian_kinerja")'
                ) if row["name"] == "capaian"),
                None,
            )
            needs_rebuild = (
                "persentase_capaian" not in columns
                or "realisasi_anggaran" not in columns
                or (achievement_column is not None and achievement_column["notnull"])
            )
            if needs_rebuild:
                connection.execute(
                    "CREATE TABLE capaian_kinerja_new ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "target_kinerja_id INTEGER NOT NULL REFERENCES target_kinerja(id), "
                    "periode_id INTEGER NOT NULL REFERENCES periode(id), "
                    "capaian NUMERIC(20,4), "
                    "persentase_capaian NUMERIC(12,4), "
                    "realisasi_anggaran NUMERIC(20,2), "
                    "UNIQUE(target_kinerja_id,periode_id))"
                )
                percentage_column = (
                    "persentase_capaian"
                    if "persentase_capaian" in columns
                    else "NULL"
                )
                realization_column = (
                    "realisasi_anggaran"
                    if "realisasi_anggaran" in columns
                    else "NULL"
                )
                connection.execute(
                    "INSERT INTO capaian_kinerja_new("
                    "id,target_kinerja_id,periode_id,capaian,"
                    "persentase_capaian,realisasi_anggaran"
                    ") SELECT id,target_kinerja_id,periode_id,capaian,"
                    f"{percentage_column},{realization_column} "
                    "FROM capaian_kinerja"
                )
                connection.execute(
                    "UPDATE capaian_kinerja_new SET persentase_capaian=("
                    "SELECT CASE WHEN target.target<>0 "
                    "THEN capaian_kinerja_new.capaian*100/target.target END "
                    "FROM target_kinerja AS target "
                    "WHERE target.id=capaian_kinerja_new.target_kinerja_id) "
                    "WHERE persentase_capaian IS NULL AND capaian IS NOT NULL"
                )
                if {
                    "pagu_anggaran",
                    "realisasi_anggaran",
                }.issubset(tables):
                    connection.execute(
                        "INSERT OR IGNORE INTO capaian_kinerja_new("
                        "target_kinerja_id,periode_id,capaian,realisasi_anggaran"
                        ") SELECT target.id,realisasi.periode_id,NULL,"
                        "SUM(realisasi.realisasi) "
                        "FROM realisasi_anggaran AS realisasi "
                        "JOIN pagu_anggaran AS pagu "
                        "ON pagu.id=realisasi.pagu_anggaran_id "
                        "JOIN target_kinerja AS target "
                        "ON target.sub_unit_id=pagu.sub_unit_id "
                        "AND target.tahun_id=pagu.tahun_id "
                        "AND target.pekerjaan_id=pagu.pekerjaan_id "
                        "AND target.level_pekerjaan_id=pagu.level_pekerjaan_id "
                        "GROUP BY target.id,realisasi.periode_id"
                    )
                    connection.execute(
                        "UPDATE capaian_kinerja_new AS capaian SET "
                        "realisasi_anggaran=("
                        "SELECT SUM(realisasi.realisasi) "
                        "FROM realisasi_anggaran AS realisasi "
                        "JOIN pagu_anggaran AS pagu "
                        "ON pagu.id=realisasi.pagu_anggaran_id "
                        "JOIN target_kinerja AS target "
                        "ON target.sub_unit_id=pagu.sub_unit_id "
                        "AND target.tahun_id=pagu.tahun_id "
                        "AND target.pekerjaan_id=pagu.pekerjaan_id "
                        "AND target.level_pekerjaan_id=pagu.level_pekerjaan_id "
                        "WHERE target.id=capaian.target_kinerja_id "
                        "AND realisasi.periode_id=capaian.periode_id) "
                        "WHERE EXISTS ("
                        "SELECT 1 FROM realisasi_anggaran AS realisasi "
                        "JOIN pagu_anggaran AS pagu "
                        "ON pagu.id=realisasi.pagu_anggaran_id "
                        "JOIN target_kinerja AS target "
                        "ON target.sub_unit_id=pagu.sub_unit_id "
                        "AND target.tahun_id=pagu.tahun_id "
                        "AND target.pekerjaan_id=pagu.pekerjaan_id "
                        "AND target.level_pekerjaan_id=pagu.level_pekerjaan_id "
                        "WHERE target.id=capaian.target_kinerja_id "
                        "AND realisasi.periode_id=capaian.periode_id)"
                    )
                if "periode" in tables:
                    connection.execute("DROP TABLE capaian_kinerja")
                    connection.execute(
                        "ALTER TABLE capaian_kinerja_new RENAME TO capaian_kinerja"
                    )

        if "realisasi_anggaran" in tables:
            connection.execute("DROP TABLE realisasi_anggaran")
        if "pagu_anggaran" in tables:
            connection.execute("DROP TABLE pagu_anggaran")

        connection.commit()
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                f"Migrasi database menyisakan pelanggaran foreign key: {violations[0]}"
            )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.close()


def migrate_link_directory_schema(database_path: Path) -> None:
    """Add link-directory fields without inferring years for legacy links."""
    if not database_path.exists():
        return
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        category_table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='link_categories'"
        ).fetchone()
        if category_table_exists is not None:
            category_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(link_categories)")
            }
            if "is_active" not in category_columns:
                connection.execute(
                    "ALTER TABLE link_categories ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
                )
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='directory_links'"
        ).fetchone()
        if table_exists is not None:
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(directory_links)")
            }
            if "icon" not in columns:
                connection.execute("ALTER TABLE directory_links ADD COLUMN icon TEXT")
            if "year_id" not in columns:
                connection.execute(
                    "ALTER TABLE directory_links ADD COLUMN year_id INTEGER REFERENCES years(id)"
                )
        connection.commit()
    finally:
        connection.close()
