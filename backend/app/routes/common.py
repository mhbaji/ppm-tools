"""Shared API helpers for validation, authorization, hierarchy building, and errors."""

import hmac
import logging
from functools import wraps
from typing import Any
from urllib.parse import quote

from flask import Blueprint, current_app, jsonify, request, session as web_session
from sqlalchemy import String, cast, exists, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import (
    BudgetDetail,
    AdminUser,
    TaggingType,
    Activity,
    PackageGroup,
    Program,
    Account,
    Department,
    DepartmentAlias,
    FundingSource,
    Subactivity,
    OrganizationalUnit,
    SubactivityTagging,
    Year,
)


LOGGER = logging.getLogger("apbd")


class APIError(Exception):
    """Represent a controlled API error with an HTTP status."""
    def __init__(self, status: int, message: str) -> None:
        """Store the HTTP status associated with this API error."""
        super().__init__(message)
        self.status = status

def get_session() -> Session:
    """Create a database session from the active Flask application."""
    session_factory = current_app.extensions["apbd_session_factory"]
    return session_factory()

def check_csrf_token() -> bool:
    """Compare the submitted CSRF token without timing-sensitive string checks."""
    submitted = request.headers.get("X-CSRF-Token", "")
    expected = web_session.get("csrf_token", "")
    return bool(submitted and expected and hmac.compare_digest(submitted, expected))

def admin_required(view):
    """Protect admin endpoints and enforce CSRF checks for mutations."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        """Apply authorization checks before dispatching to an admin handler."""
        admin_id = web_session.get("admin_user_id")
        if not isinstance(admin_id, int):
            return jsonify({"error": "Silakan login sebagai admin."}), 401
        with get_session() as database_session:
            admin = database_session.get(AdminUser, admin_id)
            if admin is None or not admin.is_active:
                web_session.clear()
                return jsonify({"error": "Silakan login sebagai admin."}), 401
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if not check_csrf_token():
                return jsonify({"error": "Token keamanan tidak valid."}), 403
        return view(*args, **kwargs)

    return wrapped

def requested_year(session: Session) -> int:
    """Validate and resolve the year requested by an API caller."""
    value = request.args.get("year", "")
    if not value.isdecimal():
        raise APIError(400, "Parameter year wajib berupa tahun yang valid.")

    year = int(value)
    available = session.scalar(select(Year.id).where(Year.name == year))
    if available is None:
        raise APIError(404, f"Tahun {year} tidak tersedia.")
    return year

def requested_stage_id(session: Session, year: int) -> int:
    """Validate that the requested stage contains budget data for the year."""
    value = request.args.get("tahapan_id", "")
    if not value.isdecimal():
        raise APIError(400, "Parameter tahapan_id wajib berupa ID tahapan yang valid.")

    stage_id = int(value)
    available = session.scalar(
        select(BudgetDetail.id)
        .where(
            BudgetDetail.year.has(Year.name == year),
            BudgetDetail.stage_id == stage_id,
        )
        .limit(1)
    )
    if available is None:
        raise APIError(
            404, f"Data tahapan {stage_id} untuk tahun {year} tidak tersedia."
        )
    return stage_id

def escape_like(value: str) -> str:
    """Escape SQL LIKE wildcards in user-supplied search text."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def get_search_filters(search: str) -> list[Any]:
    """Build reusable filters for searching across budget hierarchy fields."""
    if not search:
        return []

    pattern = f"%{escape_like(search)}%"
    return [
        cast(BudgetDetail.id, String).ilike(pattern, escape="\\"),
        BudgetDetail.year.has(cast(Year.name, String).ilike(pattern, escape="\\")),
        BudgetDetail.department.has(
            or_(
                Department.code.ilike(pattern, escape="\\"),
                Department.name.ilike(pattern, escape="\\"),
                Department.aliases.any(DepartmentAlias.name.ilike(pattern, escape="\\")),
            )
        ),
        BudgetDetail.organizational_unit.has(
            or_(
                OrganizationalUnit.code.ilike(pattern, escape="\\"),
                OrganizationalUnit.name.ilike(pattern, escape="\\"),
            )
        ),
        BudgetDetail.program.has(
            or_(
                Program.code.ilike(pattern, escape="\\"),
                Program.name.ilike(pattern, escape="\\"),
            )
        ),
        BudgetDetail.activity.has(
            or_(
                Activity.code.ilike(pattern, escape="\\"),
                Activity.name.ilike(pattern, escape="\\"),
            )
        ),
        BudgetDetail.subactivity.has(
            or_(
                Subactivity.code.ilike(pattern, escape="\\"),
                Subactivity.name.ilike(pattern, escape="\\"),
            )
        ),
        BudgetDetail.account.has(
            or_(
                Account.code.ilike(pattern, escape="\\"),
                Account.name.ilike(pattern, escape="\\"),
            )
        ),
        BudgetDetail.funding_source.has(
            or_(
                FundingSource.code.ilike(pattern, escape="\\"),
                FundingSource.name.ilike(pattern, escape="\\"),
            )
        ),
        BudgetDetail.package_group.has(
            PackageGroup.name.ilike(pattern, escape="\\")
        ),
        cast(BudgetDetail.budget, String).ilike(pattern, escape="\\"),
        exists(
            select(1)
            .select_from(SubactivityTagging)
            .join(
                TaggingType,
                TaggingType.id == SubactivityTagging.tagging_type_id,
            )
            .where(
                SubactivityTagging.subactivity_id
                == BudgetDetail.subactivity_id,
                or_(
                    cast(TaggingType.code, String).ilike(
                        pattern, escape="\\"
                    ),
                    TaggingType.name.ilike(pattern, escape="\\"),
                ),
                SubactivityTagging.year_id == BudgetDetail.year_id,
            )
        ),
    ]

def create_tree_node(
    level: str,
    code: str | None,
    name: str,
    department: str | None = None,
    funding_source: str | None = None,
) -> dict[str, Any]:
    """Initialize a consistent hierarchy node for budget aggregation."""
    return {
        "level": level,
        "code": code,
        "skpd": department,
        "name": name,
        "pagu": 0,
        "sumber_dana": funding_source,
        "tagging": set(),
        "groups": set(),
        "children": {},
    }

def build_hierarchy_rows(
    records: list[tuple[Any, ...]],
    limit: int,
    offset: int,
    paginated: bool,
    aggregate_budget: dict[tuple[int, int, int, int], int] | None = None,
    number_offset: int = 0,
    tagging_by_subactivity: dict[tuple[int, int, int | None], set[str]] | None = None,
) -> tuple[list[dict[str, object]], int]:
    """Aggregate budget records into the paginated API hierarchy."""
    roots: dict[tuple[str, str], dict[str, Any]] = {}
    group_nodes: list[dict[str, Any]] = []
    nomor_by_group: dict[tuple[int, int, int, int], int] = {}

    def get_child(
        parent: dict[str, Any],
        key: tuple[str, ...],
        level: str,
        code: str | None,
        name: str,
        department: str | None = None,
        funding_source: str | None = None,
    ) -> dict[str, Any]:
        """Reuse an existing hierarchy node or create it under its parent."""
        children = parent["children"]
        if key not in children:
            children[key] = create_tree_node(
                level, code, name, department=department, funding_source=funding_source
            )
        return children[key]

    for (
        budget,
        organizational_unit,
        program,
        activity,
        subactivity,
        account,
        funding_source,
    ) in records:
        group_key = (
            budget.organizational_unit_id,
            budget.program_id,
            budget.activity_id,
            budget.subactivity_id,
        )
        group_node = nomor_by_group.get(group_key)
        if group_node is None:
            group_node = number_offset + len(group_nodes) + 1
            nomor_by_group[group_key] = group_node
            group_nodes.append(
                {
                    "group_key": group_key,
                    "nomor": group_node,
                    "node": None,
                }
            )

        root_key = ("skpd", organizational_unit.code)
        if root_key not in roots:
            roots[root_key] = create_tree_node(
                "skpd", organizational_unit.code, organizational_unit.name, department=organizational_unit.name
            )
        department_node = roots[root_key]
        program_node = get_child(
            department_node,
            ("program", program.code),
            "program",
            program.code,
            program.name,
        )
        activity_node = get_child(
            program_node,
            ("kegiatan", activity.code),
            "kegiatan",
            activity.code,
            activity.name,
        )
        subactivity_node = get_child(
            activity_node,
            ("sub_kegiatan", subactivity.code),
            "sub_kegiatan",
            subactivity.code,
            subactivity.name,
        )
        if tagging_by_subactivity is not None:
            subactivity_node["tagging"].update(
                tagging_by_subactivity.get(
                    (
                        budget.organizational_unit_id,
                        budget.subactivity_id,
                        None,
                    ),
                    set(),
                )
            )
        group_index = group_node - number_offset - 1
        if group_nodes[group_index]["node"] is None:
            group_nodes[group_index]["node"] = subactivity_node

        amount = budget.budget or 0
        path_nodes = [department_node, program_node, activity_node, subactivity_node]
        for node in path_nodes:
            if group_node not in node["groups"]:
                node["pagu"] += (
                    aggregate_budget[group_key]
                    if aggregate_budget is not None
                    else amount
                )
                node["groups"].add(group_node)
            elif aggregate_budget is None:
                node["pagu"] += amount

        parent_node = subactivity_node
        if budget.package_group is not None:
            package_key = ("paket", budget.package_group.name)
            parent_node = get_child(
                subactivity_node,
                package_key,
                "paket",
                None,
                budget.package_group.name,
            )
            if tagging_by_subactivity is not None:
                parent_node["tagging"].update(
                    tagging_by_subactivity.get(
                        (
                            budget.organizational_unit_id,
                            budget.subactivity_id,
                            budget.package_group_id,
                        ),
                        set(),
                    )
                )
            parent_node["pagu"] += amount
            parent_node["groups"].add(group_node)

        if account is not None:
            account_key = (
                "rekening",
                account.code,
                funding_source.code if funding_source is not None else "",
            )
            account_node = get_child(
                parent_node,
                account_key,
                "rekening",
                account.code,
                account.name,
                funding_source=funding_source.name if funding_source is not None else None,
            )
            account_node["pagu"] += amount
            account_node["groups"].add(group_node)

    for item in group_nodes:
        item["node"]["nomor"] = item["nomor"]

    selected_group_numbers = [
        item["nomor"] for item in group_nodes[offset : offset + limit]
    ] if paginated else [item["nomor"] for item in group_nodes]
    selected_groups = set(selected_group_numbers)
    rows: list[dict[str, object]] = []

    def flatten(
        node: dict[str, Any],
        parent_key: str | None = None,
        root_code: str | None = None,
    ) -> None:
        """Emit visible hierarchy nodes with their ancestor keys."""
        if not node["groups"].intersection(selected_groups):
            return

        if node["level"] == "skpd":
            root_code = node["code"]
        row_key = (
            f"{parent_key}/" if parent_key is not None else ""
        ) + f"{node['level']}:{quote(str(node['code'] or node['name']), safe='')}"
        has_children = any(
            child["groups"].intersection(selected_groups)
            for child in node["children"].values()
        )
        rows.append(
            {
                "nomor": node.get("nomor") if node["level"] == "sub_kegiatan" else None,
                "level": node["level"],
                "code": node["code"],
                "skpd": node["skpd"],
                "name": node["name"],
                "row_key": row_key,
                "parent_key": parent_key,
                "root_code": root_code,
                "has_children": has_children,
                "pagu": node["pagu"],
                "sumber_dana": node["sumber_dana"],
                "tagging": sorted(node["tagging"]),
            }
        )
        for child in node["children"].values():
            flatten(child, row_key, root_code)

    for root in roots.values():
        flatten(root)
    return rows, len(group_nodes)

def handle_api_error(error: APIError):
    """Convert expected API errors into JSON responses."""
    return jsonify({"error": str(error)}), error.status

def handle_database_error(error: SQLAlchemyError):
    """Log database failures and return a generic server error."""
    LOGGER.exception(
        "Gagal mengakses database (%s) untuk permintaan %s", error, request.path
    )
    return jsonify({"error": "Terjadi kesalahan saat mengakses data anggaran."}), 500

def handle_data_error(error: RuntimeError):
    """Log malformed data failures and return a generic server error."""
    LOGGER.exception(
        "Format data tidak valid (%s) untuk permintaan %s", error, request.path
    )
    return jsonify({"error": "Format data anggaran tidak valid."}), 500

def register_api_error_handlers(blueprint: Blueprint) -> None:
    """Attach shared JSON error handlers to an API blueprint."""
    blueprint.register_error_handler(APIError, handle_api_error)
    blueprint.register_error_handler(SQLAlchemyError, handle_database_error)
    blueprint.register_error_handler(RuntimeError, handle_data_error)
