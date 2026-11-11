"""Public API route handlers for budget, tagging, and comparison data."""

from .public_helpers import (
    _excel_safe,
    _latest_realization,
    _period_label,
    _public_tagging_data,
    create_budget_export_sheet,
    finish_budget_comparison_hierarchy,
    flatten_budget_comparison_hierarchy,
)
from .admin_helpers import _realization_statement, _serialize_realization_rows

from collections import defaultdict
from io import BytesIO
import json
from typing import Any
from urllib.parse import quote, unquote

from flask import Blueprint, jsonify, request, send_file
from openpyxl import Workbook
from sqlalchemy import and_, case, func, or_, select, tuple_
from sqlalchemy.orm import aliased

from ..models import (
    BudgetDetail,
    PerformanceResult,
    TaggingType,
    Activity,
    JobLevel,
    Indicator,
    PackageGroup,
    Period,
    Program,
    Account,
    Department,
    DepartmentAlias,
    FundingSource,
    Subactivity,
    OrganizationalUnit,
    SubactivityTagging,
    Stage,
    PerformanceTarget,
    Year,
    DirectoryLink,
    LinkCategory,
)
from .common import (
    APIError,
    build_hierarchy_rows,
    escape_like,
    get_search_filters,
    get_session,
    requested_stage_id,
    requested_year,
)


public_blueprint = Blueprint("public_api", __name__, url_prefix="/api")


@public_blueprint.get("/years")
def get_years():
    """List years available to public data views."""
    with get_session() as session:
        years = session.scalars(
            select(Year.name).order_by(Year.name.desc())
        ).all()
    return jsonify({"years": years})


@public_blueprint.get("/sub-units")
def get_public_sub_units():
    """List subunits available for a selected year."""
    with get_session() as session:
        year = requested_year(session)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        sub_units = session.execute(
            select(OrganizationalUnit.code, OrganizationalUnit.name)
            .where(OrganizationalUnit.year_id == year_id)
            .order_by(OrganizationalUnit.name, OrganizationalUnit.code)
        ).all()
    return jsonify(
        {
            "year": year,
            "sub_units": [
                {"code": code, "name": name} for code, name in sub_units
            ],
        }
    )


@public_blueprint.get("/tahapan")
def get_stage():
    """Return budget stages and the default selection for a year."""
    with get_session() as session:
        year = requested_year(session)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        stages = session.execute(
            select(
                Stage.id,
                Stage.name,
                func.max(BudgetDetail.id).label("latest_anggaran_id"),
            )
            .join(BudgetDetail, BudgetDetail.stage_id == Stage.id)
            .where(BudgetDetail.year_id == year_id, Stage.year_id == year_id)
            .group_by(Stage.id, Stage.name)
            .order_by(func.max(BudgetDetail.id).desc(), Stage.id.desc())
        ).all()
    return jsonify(
        {
            "year": year,
            "default_tahapan_id": stages[0].id if stages else None,
            "tahapan": [
                {"id": stage.id, "name": stage.name} for stage in stages
            ],
        }
    )


@public_blueprint.get("/realisasi/periods")
def get_public_realization_periods():
    """List periods that have realization records for the selected year."""
    year_value = request.args.get("year", "")
    if not year_value.isdecimal():
        raise APIError(400, "Parameter year wajib berupa tahun yang valid.")
    with get_session() as session:
        year_id = session.scalar(select(Year.id).where(Year.name == int(year_value)))
        if year_id is None:
            raise APIError(404, f"Tahun {year_value} tidak tersedia.")
        periods = session.execute(
            select(Period.id, Period.name)
            .join(PerformanceResult, PerformanceResult.period_id == Period.id)
            .join(
                PerformanceTarget,
                PerformanceTarget.id == PerformanceResult.performance_target_id,
            )
            .where(PerformanceTarget.year_id == year_id)
            .distinct()
            .order_by(Period.id)
        ).all()
    return jsonify(
        {
            "year": int(year_value),
            "periods": [{"id": period_id, "name": name} for period_id, name in periods],
        }
    )


@public_blueprint.get("/link-directory")
def get_public_link_directory():
    """Return active links grouped by their two-level public topic hierarchy."""
    category_value = request.args.get("category_id", "")
    topic_value = request.args.get("topic_id", "")
    search = request.args.get("q", "").strip()
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise APIError(400, "Limit dan offset harus berupa bilangan bulat.") from error
    if not 1 <= limit <= 100 or offset < 0:
        raise APIError(400, "Limit harus 1–100 dan offset tidak boleh negatif.")
    with get_session() as session:
        summary_parent = aliased(LinkCategory)
        summary = {
            "main_topics": session.scalar(
                select(func.count())
                .select_from(LinkCategory)
                .where(LinkCategory.parent_id.is_(None), LinkCategory.is_active.is_(True))
            )
            or 0,
            "detail_topics": session.scalar(
                select(func.count())
                .select_from(LinkCategory)
                .join(summary_parent, LinkCategory.parent_id == summary_parent.id)
                .where(LinkCategory.is_active.is_(True), summary_parent.is_active.is_(True))
            )
            or 0,
            "links": session.scalar(
                select(func.count())
                .select_from(DirectoryLink)
                .join(LinkCategory, DirectoryLink.category_id == LinkCategory.id)
                .outerjoin(summary_parent, LinkCategory.parent_id == summary_parent.id)
                .where(
                    DirectoryLink.is_active.is_(True),
                    LinkCategory.is_active.is_(True),
                    or_(LinkCategory.parent_id.is_(None), summary_parent.is_active.is_(True)),
                )
            )
            or 0,
        }
        if category_value:
            if not category_value.isdecimal():
                raise APIError(400, "Parameter category_id tidak valid.")
            category = session.get(LinkCategory, int(category_value))
            if (
                category is None
                or category.parent_id is None
                or not category.is_active
                or category.parent is None
                or not category.parent.is_active
            ):
                raise APIError(404, "Topik rincian tidak ditemukan.")
            statement = select(DirectoryLink).where(
                DirectoryLink.category_id == category.id,
                DirectoryLink.is_active.is_(True),
            )
            if search:
                pattern = f"%{escape_like(search)}%"
                statement = statement.where(
                    or_(
                        DirectoryLink.title.ilike(pattern, escape="\\"),
                        DirectoryLink.description.ilike(pattern, escape="\\"),
                        DirectoryLink.tags.ilike(pattern, escape="\\"),
                    )
                )
            total = session.scalar(
                select(func.count()).select_from(statement.order_by(None).subquery())
            ) or 0
            links = session.scalars(
                statement.order_by(DirectoryLink.published_at.desc(), DirectoryLink.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            return jsonify(
                {
                    "category": {
                        "id": category.id,
                        "name": category.name,
                        "description": category.description,
                        "parent_id": category.parent_id,
                    },
                    "links": [
                        {
                            "id": link.id,
                            "title": link.title,
                            "url": link.url,
                            "description": link.description,
                            "image_url": link.image_url,
                            "icon": link.icon,
                            "tags": json.loads(link.tags),
                            "published_at": link.published_at.isoformat(sep=" "),
                        }
                        for link in links
                    ],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "summary": summary,
                }
            )

        if search:
            root_category = aliased(LinkCategory)
            statement = (
                select(DirectoryLink, LinkCategory, root_category)
                .join(LinkCategory, DirectoryLink.category_id == LinkCategory.id)
                .outerjoin(root_category, root_category.id == LinkCategory.parent_id)
                .where(
                    DirectoryLink.is_active.is_(True),
                    LinkCategory.is_active.is_(True),
                    or_(LinkCategory.parent_id.is_(None), root_category.is_active.is_(True)),
                )
            )
            if topic_value:
                if not topic_value.isdecimal():
                    raise APIError(400, "Parameter topic_id tidak valid.")
                topic = session.get(LinkCategory, int(topic_value))
                if topic is None or topic.parent_id is not None or not topic.is_active:
                    raise APIError(404, "Topik utama tidak ditemukan.")
                statement = statement.where(
                    or_(
                        LinkCategory.id == topic.id,
                        LinkCategory.parent_id == topic.id,
                    )
                )
            pattern = f"%{escape_like(search)}%"
            statement = statement.where(
                or_(
                    DirectoryLink.title.ilike(pattern, escape="\\"),
                    DirectoryLink.description.ilike(pattern, escape="\\"),
                    DirectoryLink.tags.ilike(pattern, escape="\\"),
                    LinkCategory.name.ilike(pattern, escape="\\"),
                    LinkCategory.description.ilike(pattern, escape="\\"),
                    root_category.name.ilike(pattern, escape="\\"),
                    root_category.description.ilike(pattern, escape="\\"),
                )
            )
            total = session.scalar(
                select(func.count()).select_from(statement.order_by(None).subquery())
            ) or 0
            matches = session.execute(
                statement.order_by(
                    DirectoryLink.published_at.desc(), DirectoryLink.id.desc()
                )
                .limit(limit)
                .offset(offset)
            ).all()
            return jsonify(
                {
                    "query": search,
                    "links": [
                        {
                            "id": link.id,
                            "title": link.title,
                            "url": link.url,
                            "description": link.description,
                            "image_url": link.image_url,
                            "icon": link.icon,
                            "tags": json.loads(link.tags),
                            "published_at": link.published_at.isoformat(sep=" "),
                            "category": {
                                "id": category.id,
                                "name": category.name,
                            },
                            "topic": {
                                "id": (root or category).id,
                                "name": (root or category).name,
                            },
                        }
                        for link, category, root in matches
                    ],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "summary": summary,
                }
            )

        if topic_value:
            if not topic_value.isdecimal():
                raise APIError(400, "Parameter topic_id tidak valid.")
            topic = session.get(LinkCategory, int(topic_value))
            if topic is None or topic.parent_id is not None or not topic.is_active:
                raise APIError(404, "Topik utama tidak ditemukan.")

        root_statement = select(LinkCategory).where(
            LinkCategory.parent_id.is_(None), LinkCategory.is_active.is_(True)
        )
        if topic_value:
            root_statement = root_statement.where(LinkCategory.id == int(topic_value))
        root_categories = session.scalars(
            root_statement.order_by(LinkCategory.created_at.desc(), LinkCategory.id.desc())
        ).all()
        root_ids = [category.id for category in root_categories]
        child_categories = (
            session.scalars(
                select(LinkCategory)
                .where(LinkCategory.parent_id.in_(root_ids), LinkCategory.is_active.is_(True))
                .order_by(LinkCategory.created_at.desc(), LinkCategory.id.desc())
            ).all()
            if root_ids
            else []
        )
        children_by_root: dict[int, list[LinkCategory]] = defaultdict(list)
        for child in child_categories:
            if topic_value or len(children_by_root[child.parent_id]) < 5:
                children_by_root[child.parent_id].append(child)
        child_ids = [
            child.id for children in children_by_root.values() for child in children
        ]
        latest_links_by_category: dict[int, list[DirectoryLink]] = defaultdict(list)
        if child_ids:
            ranked_links = (
                select(
                    DirectoryLink.id.label("id"),
                    func.row_number()
                    .over(
                        partition_by=DirectoryLink.category_id,
                        order_by=(DirectoryLink.published_at.desc(), DirectoryLink.id.desc()),
                    )
                    .label("rank"),
                )
                .where(
                    DirectoryLink.category_id.in_(child_ids),
                    DirectoryLink.is_active.is_(True),
                )
                .subquery()
            )
            latest_links = session.execute(
                select(DirectoryLink)
                .join(ranked_links, ranked_links.c.id == DirectoryLink.id)
                .where(ranked_links.c.rank <= 3)
                .order_by(
                    DirectoryLink.category_id,
                    DirectoryLink.published_at.desc(),
                    DirectoryLink.id.desc(),
                )
            ).scalars().all()
            for link in latest_links:
                latest_links_by_category[link.category_id].append(link)
        topics = []
        for root in root_categories:
            subtopics = []
            for child in children_by_root[root.id]:
                links = latest_links_by_category[child.id]
                subtopics.append(
                    {
                        "id": child.id,
                        "name": child.name,
                        "description": child.description,
                        "created_at": child.created_at.isoformat(sep=" "),
                        "links": [
                            {
                                "id": link.id,
                                "title": link.title,
                                "url": link.url,
                                "description": link.description,
                                "image_url": link.image_url,
                                "icon": link.icon,
                                "tags": json.loads(link.tags),
                                "published_at": link.published_at.isoformat(sep=" "),
                            }
                            for link in links
                        ],
                    }
                )
            topics.append(
                {
                    "id": root.id,
                    "name": root.name,
                    "description": root.description,
                    "created_at": root.created_at.isoformat(sep=" "),
                    "subtopics": subtopics,
                }
            )
    return jsonify({"topics": topics, "summary": summary})


@public_blueprint.get("/tagging-summary")
def get_tagging_summary():
    """Aggregate tagging coverage, budget, and realization metrics."""
    with get_session() as session:
        year = requested_year(session)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        stage_id = requested_stage_id(session, year)
        filters = (
            BudgetDetail.year_id == year_id,
            BudgetDetail.stage_id == stage_id,
        )
        metrics_row = session.execute(
            select(
                func.count(),
                func.count(func.distinct(BudgetDetail.organizational_unit_id)),
                func.count(func.distinct(BudgetDetail.affair_id)),
                func.count(func.distinct(BudgetDetail.affair_field_id)),
                func.count(func.distinct(BudgetDetail.program_id)),
                func.count(func.distinct(BudgetDetail.activity_id)),
                func.count(func.distinct(BudgetDetail.subactivity_id)),
                func.sum(func.coalesce(BudgetDetail.budget, 0)),
            ).where(*filters)
        ).one()
        rows = session.execute(
            select(
                BudgetDetail.subactivity_id,
                BudgetDetail.organizational_unit_id,
                BudgetDetail.package_group_id,
                BudgetDetail.budget,
            ).where(
                BudgetDetail.year_id == year_id,
                BudgetDetail.stage_id == stage_id,
            )
        ).all()
        periods = [
            {"id": period_id, "name": name, "label": _period_label(name)}
            for period_id, name in session.execute(
                select(Period.id, Period.name).order_by(Period.id)
            ).all()
        ]
        activity_keys = {
            (organizational_unit_id, subactivity_id)
            for subactivity_id, organizational_unit_id, _, _ in rows
        }
        level_id = session.scalar(
            select(JobLevel.id).where(
                func.lower(
                    func.replace(JobLevel.name, "_", " ")
                ) == "sub kegiatan"
            )
        )
        realization_by_activity: dict[
            tuple[int, int], dict[str, float]
        ] = defaultdict(dict)
        if activity_keys and level_id is not None:
            realization_rows = session.execute(
                select(
                    PerformanceTarget.organizational_unit_id,
                    PerformanceTarget.job_id,
                    PerformanceResult.period_id,
                    func.max(PerformanceResult.realized_budget),
                )
                .join(PerformanceResult)
                .where(
                    PerformanceTarget.year_id == year_id,
                    PerformanceTarget.job_level_id == level_id,
                    tuple_(
                        PerformanceTarget.organizational_unit_id,
                        PerformanceTarget.job_id,
                    ).in_(activity_keys),
                    PerformanceResult.realized_budget.is_not(None),
                )
                .group_by(
                    PerformanceTarget.organizational_unit_id,
                    PerformanceTarget.job_id,
                    PerformanceResult.period_id,
                )
            ).all()
            period_names = {period["id"]: period["name"] for period in periods}
            for unit_id, activity_id, period_id, amount in realization_rows:
                realization_by_activity[(unit_id, activity_id)][
                    period_names.get(period_id, str(period_id))
                ] = float(amount or 0)
        names = dict(
            session.execute(
                select(TaggingType.code, TaggingType.name).where(
                    TaggingType.year_id == year_id
                )
            ).all()
        )
        tagging_rows = session.execute(
            select(
                SubactivityTagging.organizational_unit_id,
                SubactivityTagging.subactivity_id,
                SubactivityTagging.package_group_id,
                TaggingType.code,
            )
            .join(TaggingType)
            .where(SubactivityTagging.year_id == year_id)
        ).all()

    tags_by_subactivity: dict[
        tuple[int, int, int | None], set[str]
    ] = defaultdict(set)
    for organizational_unit_id, subactivity_id, package_id, tagging_code in tagging_rows:
        tags_by_subactivity[(organizational_unit_id, subactivity_id, package_id)].add(
            str(tagging_code)
        )
    type_stats: dict[str, dict[str, Any]] = {
        str(code): {
            "code": str(code),
            "name": name,
            "sub_units": set(),
            "subactivities": set(),
            "packages": set(),
            "budget": 0,
            "count": 0,
        }
        for code, name in names.items()
    }
    untagged_rows = 0
    untagged_subactivities: set[tuple[int, int]] = set()
    all_subactivities: set[tuple[int, int]] = set()
    tagged_subactivities: set[tuple[int, int]] = set()
    tagged_organizational_units: set[int] = set()
    realization_totals = {period["name"]: 0.0 for period in periods}
    for subactivity_id, organizational_unit_id, package_id, budget in rows:
        subactivity_key = (organizational_unit_id, subactivity_id)
        all_subactivities.add(subactivity_key)
        tags = tags_by_subactivity.get(
            (organizational_unit_id, subactivity_id, None),
            set(),
        ).copy()
        if package_id is not None:
            tags.update(
                tags_by_subactivity.get(
                    (organizational_unit_id, subactivity_id, package_id),
                    set(),
                )
            )
        if not tags:
            untagged_rows += 1
            untagged_subactivities.add(subactivity_key)
        else:
            tagged_subactivities.add(subactivity_key)
            tagged_organizational_units.add(organizational_unit_id)
        for code in tags:
            stats = type_stats.get(str(code))
            if stats is not None:
                stats["count"] += 1
                stats["sub_units"].add(organizational_unit_id)
                stats["subactivities"].add(subactivity_key)
                if package_id is not None:
                    stats["packages"].add(
                        (organizational_unit_id, subactivity_id, package_id)
                    )
                stats["budget"] += budget or 0
    for activity_key in all_subactivities:
        values = realization_by_activity.get(activity_key, {})
        for name, amount in values.items():
            realization_totals[name] = realization_totals.get(name, 0.0) + amount

    total_budget = float(metrics_row[7] or 0)
    realization_total = sum(
        _latest_realization(realization_by_activity.get(key, {}), periods)
        for key in all_subactivities
    )
    percentage = (
        lambda amount: round(amount * 100 / total_budget, 2)
        if total_budget
        else 0
    )
    period_metrics = {
        period["name"]: {
            "label": period["label"],
            "realization": realization_totals.get(period["name"], 0.0),
            "percentage": percentage(realization_totals.get(period["name"], 0.0)),
        }
        for period in periods
    }

    tagging_type = []
    for stats in type_stats.values():
        tagging_type.append(
            {
                "code": stats["code"],
                "name": stats["name"],
                "count": stats["count"],
                "opd_count": len(stats["sub_units"]),
                "sub_unit_count": len(stats["sub_units"]),
                "subactivity_count": len(stats["subactivities"]),
                "package_count": len(stats["packages"]),
                "budget": stats["budget"],
            }
        )
    tagging_type.sort(
        key=lambda item: (str(item["name"]).casefold(), str(item["code"]))
    )
    return jsonify(
        {
            "year": year,
            "tahapan_id": stage_id,
            "total_rows": len(rows),
            "total_budget": total_budget,
            "untagged_rows": untagged_rows,
            "opd_count": len(tagged_organizational_units),
            "sub_unit_count": len(tagged_organizational_units),
            "total_apbd_subactivities": len(all_subactivities),
            "total_subactivities": len(tagged_subactivities),
            "untagged_subactivities": len(untagged_subactivities),
            "tagging_types": tagging_type,
            "metrics": {
                "total": metrics_row[0] or 0,
                "sub_units": metrics_row[1] or 0,
                "urusan": metrics_row[2] or 0,
                "bidang_urusan": metrics_row[3] or 0,
                "program": metrics_row[4] or 0,
                "kegiatan": metrics_row[5] or 0,
                "subactivities": metrics_row[6] or 0,
                "total_budget": total_budget,
                "realization_total": realization_total,
                "realization_by_period": realization_totals,
                "percentage_total": percentage(realization_total),
                "period_metrics": period_metrics,
            },
        }
    )


@public_blueprint.get("/tagging-types")
def get_public_tagging_types():
    """List public tagging types for the selected year."""
    with get_session() as session:
        year = requested_year(session)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        types = session.execute(
            select(TaggingType.code, TaggingType.name)
            .where(TaggingType.year_id == year_id)
            .order_by(TaggingType.name, TaggingType.code)
        ).all()
    return jsonify(
        {
            "year": year,
            "tagging_types": [
                {"code": code, "name": name} for code, name in types
            ],
        }
    )


@public_blueprint.get("/tagging")
def get_public_tagging():
    """Return filtered tagging details and summary metrics."""
    try:
        limit = int(request.args.get("limit", "10"))
        offset = int(request.args.get("offset", "0"))
        code_value = request.args.get("tagging_code", "")
        tagging_code = int(code_value) if code_value else None
    except ValueError as error:
        raise APIError(400, "Parameter daftar tagging tidak valid.") from error
    if not 1 <= limit <= 200 or offset < 0:
        raise APIError(400, "Limit harus 1–200 dan offset tidak boleh negatif.")
    if code_value and not code_value.isdecimal():
        raise APIError(400, "Parameter tagging_code tidak valid.")
    sub_unit_codes = request.args.getlist("skpd_code")
    if any(not code or len(code) > 100 for code in sub_unit_codes):
        raise APIError(400, "Parameter sub unit tidak valid.")

    with get_session() as session:
        year = requested_year(session)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        stage_id = requested_stage_id(session, year)
        if sub_unit_codes:
            valid_codes = set(
                session.scalars(
                    select(OrganizationalUnit.code).where(
                        OrganizationalUnit.year_id == year_id,
                        OrganizationalUnit.code.in_(sub_unit_codes),
                    )
                ).all()
            )
            if valid_codes != set(sub_unit_codes):
                raise APIError(400, "Sub unit tidak tersedia untuk tahun tersebut.")
        items, summary, periods, total = _public_tagging_data(
            session,
            year_id,
            stage_id,
            tagging_code,
            request.args.get("q", "").strip(),
            offset,
            limit,
            list(dict.fromkeys(sub_unit_codes)) or None,
        )
    return jsonify(
        {
            "year": year,
            "tahapan_id": stage_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "summary": summary,
            "periods": periods,
            "items": items,
        }
    )

@public_blueprint.get("/realisasi")
def get_public_realization():
    """Return paginated public realization and achievement data."""
    year_value = request.args.get("year", "")
    period_value = request.args.get("period_id", "")
    if not year_value.isdecimal() or not period_value.isdecimal():
        raise APIError(400, "Tahun dan periode wajib dipilih.")
    export_format = request.args.get("format", "")
    if export_format not in {"", "excel"}:
        raise APIError(400, "Format unduhan realisasi tidak valid.")
    if export_format == "excel":
        limit, offset = 100, 0
    else:
        try:
            limit = int(request.args.get("limit", "10"))
            offset = int(request.args.get("offset", "0"))
        except ValueError as error:
            raise APIError(400, "Limit dan offset harus berupa bilangan bulat.") from error
        if not 1 <= limit <= 100 or offset < 0:
            raise APIError(400, "Limit harus 1–100 dan offset tidak boleh negatif.")

    sort_key = request.args.get("sort", "subunit")
    sort_direction = request.args.get("direction", "asc")
    sort_columns = {
        "subunit": OrganizationalUnit.name,
        "level": JobLevel.name,
        "work": func.coalesce(
            Program.name,
            Activity.name,
            Subactivity.name,
            OrganizationalUnit.name,
        ),
        "indicator": Indicator.name,
        "target": PerformanceTarget.target,
        "achievement": PerformanceResult.achievement,
        "realization": PerformanceResult.realized_budget,
    }
    if sort_key not in sort_columns or sort_direction not in {"asc", "desc"}:
        raise APIError(400, "Urutan data tidak valid.")
    sub_unit_codes = request.args.getlist("skpd_code")
    if any(not code or len(code) > 100 for code in sub_unit_codes):
        raise APIError(400, "Parameter sub unit tidak valid.")

    with get_session() as session:
        year = int(year_value)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        period_id = int(period_value)
        if year_id is None:
            raise APIError(404, f"Tahun {year} tidak tersedia.")
        period = session.get(Period, period_id)
        if period is None:
            raise APIError(404, "Periode tidak ditemukan.")
        statement = _realization_statement(
            year_id, period_id, request.args.get("q", "").strip()
        )
        if sub_unit_codes:
            valid_codes = set(
                session.scalars(
                    select(OrganizationalUnit.code).where(
                        OrganizationalUnit.year_id == year_id,
                        OrganizationalUnit.code.in_(sub_unit_codes),
                    )
                ).all()
            )
            if valid_codes != set(sub_unit_codes):
                raise APIError(400, "Sub unit tidak tersedia untuk tahun tersebut.")
            statement = statement.where(OrganizationalUnit.code.in_(sub_unit_codes))
        filtered_rows = statement.order_by(None).subquery()
        summary_row = session.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                func.lower(func.replace(filtered_rows.c.level, "_", " "))
                                == "sub kegiatan",
                                filtered_rows.c.realization,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.sum(
                    case(
                        (
                            func.lower(func.replace(filtered_rows.c.level, "_", " "))
                            .in_(["program", "sub unit", "subunit"])
                            & filtered_rows.c.achievement.is_not(None),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.avg(
                    case(
                        (
                            func.lower(func.replace(filtered_rows.c.level, "_", " "))
                            .in_(["program", "sub unit", "subunit"]),
                            filtered_rows.c.achievement_percentage,
                        ),
                        else_=None,
                    )
                ),
            )
            .select_from(filtered_rows)
        ).one()
        sort_column = sort_columns[sort_key]
        ordered_statement = statement.order_by(None).order_by(
            sort_column.desc() if sort_direction == "desc" else sort_column.asc(),
            PerformanceTarget.id.asc(),
        )
        if export_format == "excel":
            workbook = Workbook(write_only=True)
            worksheet = workbook.create_sheet("Realisasi")
            worksheet.append(["Tahun", year])
            worksheet.append(["Periode", _excel_safe(period.name)])
            worksheet.append(
                ["Total realisasi sub kegiatan", float(summary_row[1] or 0)]
            )
            worksheet.append(["Jumlah capaian indikator", summary_row[2] or 0])
            worksheet.append(
                [
                    "Rata-rata persentase capaian",
                    float(summary_row[3] or 0),
                ]
            )
            worksheet.append([""])
            worksheet.append(
                [
                    "Kode Subunit",
                    "Subunit",
                    "Level",
                    "Kode Pekerjaan",
                    "Pekerjaan",
                    "Indikator",
                    "Satuan",
                    "Target",
                    "Capaian",
                    "Persentase",
                    "Pagu",
                    "Realisasi",
                ]
            )
            for record in session.execute(ordered_statement).yield_per(1000):
                item = _serialize_realization_rows([record])[0]
                if item["level"].lower().replace("_", " ") not in {
                    "program",
                    "sub unit",
                    "subunit",
                }:
                    item.update(
                        {
                            "indicator": None,
                            "unit": None,
                            "target": None,
                            "achievement": None,
                            "achievement_percentage": None,
                        }
                    )
                worksheet.append(
                    [
                        _excel_safe(item["subunit_code"]),
                        _excel_safe(item["subunit_name"]),
                        _excel_safe(item["level"]),
                        _excel_safe(item["work_code"]),
                        _excel_safe(item["work_name"]),
                        _excel_safe(item["indicator"]),
                        _excel_safe(item["unit"]),
                        item["target"],
                        item["achievement"],
                        item["achievement_percentage"],
                        item["budget"],
                        item["realization"],
                    ]
                )
            workbook_buffer = BytesIO()
            workbook.save(workbook_buffer)
            workbook_buffer.seek(0)
            return send_file(
                workbook_buffer,
                as_attachment=True,
                download_name=f"realisasi-{year}-periode-{period_id}.xlsx",
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        rows = session.execute(
            ordered_statement.limit(limit).offset(offset)
        ).all()
    return jsonify(
        {
            "year": year,
            "period_id": period_id,
            "total": summary_row[0],
            "limit": limit,
            "offset": offset,
            "summary": {
                "realization_total": float(summary_row[1] or 0),
                "achievement_count": summary_row[2] or 0,
                "achievement_percentage_average": float(summary_row[3] or 0),
            },
            "rows": [
                {
                    **item,
                    **(
                        {}
                        if item["level"].lower().replace("_", " ")
                        in {"program", "sub unit", "subunit"}
                        else {
                            "indicator": None,
                            "unit": None,
                            "target": None,
                            "achievement": None,
                            "achievement_percentage": None,
                        }
                    ),
                }
                for item in _serialize_realization_rows(rows)
            ],
        }
    )


@public_blueprint.get("/perbandingan-anggaran")
def get_budget_comparison():
    """Compare selected budget stages or tagging sources."""
    export_format = request.args.get("format", "")
    if export_format not in {"", "all"}:
        raise APIError(400, "Format unduhan perbandingan anggaran tidak valid.")
    search = request.args.get("q", "").strip()
    try:
        limit = int(request.args.get("limit", "10"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise APIError(
            400, "Parameter limit dan offset harus berupa bilangan bulat."
        ) from error
    if not 1 <= limit <= 500 or offset < 0:
        raise APIError(400, "Limit harus 1–500 dan offset tidak boleh negatif.")
    selection_values = request.args.getlist("selection")
    tagging_stage_values = request.args.getlist("tagging_tahapan")
    if not selection_values:
        raise APIError(400, "Pilih minimal satu tahapan atau jenis tagging.")

    with get_session() as session:
        fallback_year: int | None = None
        selections: list[dict[str, Any]] = []
        for selection_index, value in enumerate(selection_values):
            requested_tagging_stage = (
                tagging_stage_values[selection_index]
                if selection_index < len(tagging_stage_values)
                else ""
            )
            parts = value.split(":", 2)
            if len(parts) == 3:
                kind, year_value, identifier = parts
            elif len(parts) == 2:
                kind, identifier = parts
                if fallback_year is None:
                    fallback_year = requested_year(session)
                year_value = str(fallback_year)
            else:
                raise APIError(400, "Pilihan sumber perbandingan tidak valid.")
            if (
                kind not in {"stage", "tagging"}
                or not identifier
                or (year_value != "*" and not year_value.isdecimal())
            ):
                raise APIError(400, "Pilihan sumber perbandingan tidak valid.")
            if year_value == "*":
                name = unquote(identifier)
                if kind == "stage":
                    matches = session.execute(
                        select(Stage.id, Stage.name)
                        .join(BudgetDetail, BudgetDetail.stage_id == Stage.id)
                        .where(Stage.name == name)
                        .distinct()
                    ).all()
                    if not matches:
                        raise APIError(
                            404, "Tahapan tidak tersedia untuk semua tahun."
                        )
                    selections.append(
                        {
                            "kind": kind,
                            "id": name,
                            "label": name,
                            "filters": [
                                BudgetDetail.stage_id.in_(
                                    [item.id for item in matches]
                                )
                            ],
                            "year": None,
                            "display": f"Semua Tahun - {name}",
                        }
                    )
                else:
                    type_rows = session.execute(
                        select(TaggingType.year_id, TaggingType.code)
                        .join(
                            SubactivityTagging,
                            SubactivityTagging.tagging_type_id == TaggingType.id,
                        )
                        .where(TaggingType.name == name)
                        .distinct()
                    ).all()
                    if not type_rows:
                        raise APIError(
                            404, "Jenis tagging tidak tersedia untuk semua tahun."
                        )
                    year_stage_filters = []
                    for tagging_year_id, _ in type_rows:
                        year_name = session.scalar(
                            select(Year.name).where(Year.id == tagging_year_id)
                        )
                        if year_name is None:
                            continue
                        stage_statement = (
                            select(Stage.id, Stage.name)
                            .join(BudgetDetail, BudgetDetail.stage_id == Stage.id)
                            .where(BudgetDetail.year_id == tagging_year_id)
                        )
                        if requested_tagging_stage:
                            stage_statement = stage_statement.where(
                                Stage.name == requested_tagging_stage
                            )
                            stage = session.execute(stage_statement.limit(1)).first()
                        else:
                            stage = session.execute(
                                stage_statement.order_by(BudgetDetail.id.desc()).limit(1)
                            ).first()
                        if stage is None:
                            continue
                        year_stage_filters.append(
                            and_(
                                BudgetDetail.year_id == tagging_year_id,
                                BudgetDetail.stage_id == stage.id,
                            )
                        )
                    if not year_stage_filters:
                        raise APIError(
                            404,
                            "Jenis tagging tidak memiliki data anggaran.",
                        )
                    selections.append(
                        {
                            "kind": kind,
                            "id": name,
                            "label": name,
                            "filters": [or_(*year_stage_filters)],
                            "year": None,
                            "display": (
                                f"Semua Tahun - {requested_tagging_stage} - Tagging: {name}"
                                if requested_tagging_stage
                                else f"Semua Tahun - Tagging: {name}"
                            ),
                        }
                    )
                continue

            year = int(year_value)
            year_id = session.scalar(select(Year.id).where(Year.name == year))
            if year_id is None:
                raise APIError(404, f"Tahun {year} tidak tersedia.")
            if kind == "stage":
                if not identifier.isdecimal():
                    raise APIError(400, "Pilihan tahapan tidak valid.")
                selection = session.execute(
                    select(Stage.id, Stage.name)
                    .join(
                        BudgetDetail,
                        BudgetDetail.stage_id == Stage.id,
                    )
                    .where(
                        Stage.id == int(identifier),
                        Stage.year_id == year_id,
                        BudgetDetail.year_id == year_id,
                    )
                    .limit(1)
                ).first()
                if selection is None:
                    raise APIError(404, "Tahapan tidak tersedia untuk tahun tersebut.")
                selections.append(
                    {
                        "kind": kind,
                        "id": selection.id,
                        "label": selection.name,
                        "filters": [
                            BudgetDetail.year_id == year_id,
                            BudgetDetail.stage_id == selection.id,
                        ],
                        "year": year,
                        "display": f"{year} - {selection.name}",
                    }
                )
            else:
                if not identifier.isdecimal():
                    raise APIError(400, "Pilihan jenis tagging tidak valid.")
                selection = session.execute(
                    select(TaggingType.code, TaggingType.name).where(
                        TaggingType.code == int(identifier),
                        TaggingType.year_id == year_id,
                    )
                ).first()
                if selection is None:
                    raise APIError(
                        404, "Jenis tagging tidak tersedia untuk tahun tersebut."
                    )
                stage_statement = (
                    select(Stage.id, Stage.name)
                    .join(BudgetDetail, BudgetDetail.stage_id == Stage.id)
                    .where(
                        Stage.year_id == year_id,
                        BudgetDetail.year_id == year_id,
                    )
                )
                if requested_tagging_stage:
                    if not requested_tagging_stage.isdecimal():
                        raise APIError(400, "Pilihan tahapan untuk tagging tidak valid.")
                    stage_statement = stage_statement.where(
                        Stage.id == int(requested_tagging_stage)
                    )
                stage = session.execute(
                    stage_statement.order_by(BudgetDetail.id.desc()).limit(1)
                ).first()
                if stage is None:
                    raise APIError(
                        404, "Jenis tagging tidak memiliki data anggaran."
                    )
                selections.append(
                    {
                        "kind": kind,
                        "id": selection.code,
                        "label": selection.name,
                        "filters": [
                            BudgetDetail.year_id == year_id,
                            BudgetDetail.stage_id == stage.id,
                        ],
                        "year": year,
                        "display": (
                            f"{year} - {stage.name} - Tagging: {selection.name}"
                        ),
                    }
                )

        rows_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
        search_filters = get_search_filters(search)
        for index, selection in enumerate(selections):
            filters = list(selection["filters"])
            if search_filters:
                filters.append(or_(*search_filters))
            if selection["kind"] == "tagging":
                tag_year_condition = (
                    SubactivityTagging.year_id == BudgetDetail.year_id
                    if selection["year"] is None
                    else SubactivityTagging.year_id
                    == session.scalar(
                        select(Year.id).where(Year.name == selection["year"])
                    )
                )
                tagging_match = (
                    TaggingType.name == selection["id"]
                    if selection["year"] is None
                    else TaggingType.code == selection["id"]
                )
                matching_tag = (
                    select(SubactivityTagging.id)
                    .join(
                        TaggingType,
                        TaggingType.id == SubactivityTagging.tagging_type_id,
                    )
                    .where(
                        tag_year_condition,
                        SubactivityTagging.organizational_unit_id
                        == BudgetDetail.organizational_unit_id,
                        SubactivityTagging.subactivity_id
                        == BudgetDetail.subactivity_id,
                        tagging_match,
                        or_(
                            SubactivityTagging.package_group_id.is_(None),
                            SubactivityTagging.package_group_id
                            == BudgetDetail.package_group_id,
                        ),
                    )
                    .exists()
                )
                filters.append(matching_tag)

            dimensions = (
                Department.id,
                Department.code,
                Department.name,
                OrganizationalUnit.id,
                OrganizationalUnit.code,
                OrganizationalUnit.name,
                Program.id,
                Program.code,
                Program.name,
                Activity.id,
                Activity.code,
                Activity.name,
                Subactivity.id,
                Subactivity.code,
                Subactivity.name,
                PackageGroup.id,
                PackageGroup.name,
                Account.id,
                Account.code,
                Account.name,
            )
            result_rows = session.execute(
                select(
                    *dimensions,
                    func.sum(func.coalesce(BudgetDetail.budget, 0)),
                )
                .join(BudgetDetail.department)
                .join(BudgetDetail.organizational_unit)
                .join(BudgetDetail.program)
                .join(BudgetDetail.activity)
                .join(BudgetDetail.subactivity)
                .outerjoin(BudgetDetail.package_group)
                .outerjoin(BudgetDetail.account)
                .where(*filters)
                .group_by(*dimensions)
                .order_by(
                    Department.name,
                    OrganizationalUnit.name,
                    Program.code,
                    Activity.code,
                    Subactivity.code,
                    PackageGroup.name,
                    Account.code,
                )
            ).all()
            for record in result_rows:
                key = (
                    record[1],
                    record[4],
                    record[7],
                    record[10],
                    record[13],
                    record[16],
                    record[18],
                )
                row = rows_by_key.get(key)
                if row is None:
                    hierarchy_parts = [
                        f"{record[2]} / {record[5]}",
                        record[8],
                        record[11],
                        record[14],
                        record[16],
                        record[19],
                    ]
                    hierarchy_keys = [
                        (record[1], record[4]),
                        record[7],
                        record[10],
                        record[13],
                        record[16],
                        record[18],
                    ]
                    hierarchy_codes = [
                        record[4],
                        record[7],
                        record[10],
                        record[13],
                        "",
                        record[18],
                    ]
                    hierarchy_entries = [
                        (depth, str(part), key, code or "")
                        for depth, (part, key, code) in enumerate(
                            zip(hierarchy_parts, hierarchy_keys, hierarchy_codes)
                        )
                        if part
                    ]
                    (
                        hierarchy_depths,
                        hierarchy_parts,
                        hierarchy_keys,
                        hierarchy_codes,
                    ) = zip(
                        *hierarchy_entries
                    )
                    row = {
                        "code": record[18] or record[13] or record[7],
                        "sub_unit_name": record[5],
                        "hierarchy": " / ".join(hierarchy_parts),
                        "hierarchy_parts": list(hierarchy_parts),
                        "hierarchy_keys": list(hierarchy_keys),
                        "hierarchy_depths": list(hierarchy_depths),
                        "hierarchy_codes": list(hierarchy_codes),
                        "amounts": [0 for _ in selections],
                    }
                    rows_by_key[key] = row
                row["amounts"][index] += float(record[-1] or 0)

    comparison_rows = sorted(
        rows_by_key.values(),
        key=lambda item: (item["hierarchy"].casefold(), str(item["code"])),
    )
    hierarchy_rows = []
    if export_format in {"", "all", "excel"}:
        roots: dict[tuple[Any, ...], dict[str, Any]] = {}
        level_names = [
            "skpd",
            "program",
            "kegiatan",
            "sub_kegiatan",
            "paket",
            "rekening",
        ]
        for item in comparison_rows:
            parts = item["hierarchy_parts"]
            keys = item["hierarchy_keys"]
            depths = item["hierarchy_depths"]
            codes = item["hierarchy_codes"]
            node_map = roots
            parent_path: list[Any] = []
            for name, key, depth, code in zip(parts, keys, depths, codes):
                node_key = (*parent_path, key)
                node = node_map.get(node_key)
                if node is None:
                    node = {
                        "code": code,
                        "name": name,
                        "hierarchy": " / ".join(parts[: depth + 1]),
                        "level": level_names[depth],
                        "depth": depth,
                        "sub_unit_name": item["sub_unit_name"],
                        "amounts": [0 for _ in selections],
                        "children": [],
                        "_children_by_key": {},
                    }
                    node_map[node_key] = node
                node["amounts"] = [
                    total + amount
                    for total, amount in zip(node["amounts"], item["amounts"])
                ]
                parent_path.append(key)
                node_map = node["_children_by_key"]

        hierarchy_rows = finish_budget_comparison_hierarchy(roots)
        hierarchy_rows.sort(key=lambda item: item["name"].casefold())
    export_rows = flatten_budget_comparison_hierarchy(hierarchy_rows)
    hierarchy_total = len(hierarchy_rows)
    selected_years = {selection["year"] for selection in selections}
    year_label = (
        str(next(iter(selected_years)))
        if len(selected_years) == 1 and None not in selected_years
        else "lintas-tahun"
    )
    result = {
        "year": year_label,
        "selections": [
            {
                "kind": selection["kind"],
                "id": selection["id"],
                "label": selection["label"],
                "display": selection["display"],
            }
            for selection in selections
        ],
        "columns": [selection["display"] for selection in selections],
        "total": hierarchy_total,
        "limit": limit,
        "offset": offset,
        "rows": hierarchy_rows[offset : offset + limit]
        if not export_format
        else export_rows,
    }
    return jsonify(result)


@public_blueprint.get("/anggaran")
def get_budget():
    """Return hierarchical budget data or its Excel export."""
    search = request.args.get("q", "").strip()
    level_search = request.args.get("level_q", "").strip()
    search_level = request.args.get("search_level", "skpd")
    if search_level not in {
        "skpd",
        "program",
        "kegiatan",
        "sub_kegiatan",
        "paket",
        "kelompok",
        "paket_kelompok",
        "rekening",
    }:
        raise APIError(400, "Tingkat pencarian anggaran tidak valid.")
    if search and search_level == "skpd" and not level_search:
        level_search = search
        search = ""
    department_codes = request.args.getlist("skpd_code")
    if any(not code or len(code) > 100 for code in department_codes):
        raise APIError(400, "Parameter sub unit tidak valid.")
    department_codes = list(dict.fromkeys(department_codes))
    export_format = request.args.get("format", "")
    sheet_mode = request.args.get("sheet_mode", "single")
    if export_format not in {"", "all", "excel"}:
        raise APIError(400, "Format data anggaran tidak valid.")
    if sheet_mode not in {"single", "sub_unit"}:
        raise APIError(400, "Pilihan format sheet Excel tidak valid.")
    paginated = not bool(search or level_search or department_codes or export_format)

    with get_session() as session:
        year = requested_year(session)
        year_id = session.scalar(select(Year.id).where(Year.name == year))
        stage_id = requested_stage_id(session, year)
        if department_codes:
            valid_codes = set(
                session.scalars(
                    select(OrganizationalUnit.code).where(
                        OrganizationalUnit.year_id == year_id,
                        OrganizationalUnit.code.in_(department_codes),
                    )
                ).all()
            )
            if valid_codes != set(department_codes):
                raise APIError(400, "Sub unit tidak tersedia untuk tahun tersebut.")
        filters = [
            BudgetDetail.year_id == year_id,
            BudgetDetail.stage_id == stage_id,
        ]
        search_filters = get_search_filters(search)
        if search_filters:
            filters.append(or_(*search_filters))
        if level_search:
            pattern = f"%{escape_like(level_search)}%"
            if search_level == "skpd":
                filters.append(
                    or_(
                        BudgetDetail.department.has(
                            or_(
                                Department.code.ilike(pattern, escape="\\"),
                                Department.name.ilike(pattern, escape="\\"),
                                Department.aliases.any(
                                    DepartmentAlias.name.ilike(pattern, escape="\\")
                                ),
                            )
                        ),
                        BudgetDetail.organizational_unit.has(
                            or_(
                                OrganizationalUnit.code.ilike(pattern, escape="\\"),
                                OrganizationalUnit.name.ilike(pattern, escape="\\"),
                            )
                        ),
                    )
                )
            else:
                target = {
                    "program": BudgetDetail.program.has(
                        or_(
                            Program.code.ilike(pattern, escape="\\"),
                            Program.name.ilike(pattern, escape="\\"),
                        )
                    ),
                    "kegiatan": BudgetDetail.activity.has(
                        or_(
                            Activity.code.ilike(pattern, escape="\\"),
                            Activity.name.ilike(pattern, escape="\\"),
                        )
                    ),
                    "sub_kegiatan": BudgetDetail.subactivity.has(
                        or_(
                            Subactivity.code.ilike(pattern, escape="\\"),
                            Subactivity.name.ilike(pattern, escape="\\"),
                        )
                    ),
                    "paket_kelompok": BudgetDetail.package_group.has(
                        PackageGroup.name.ilike(pattern, escape="\\")
                    ),
                    "paket": BudgetDetail.package_group.has(
                        PackageGroup.name.ilike(pattern, escape="\\")
                    ),
                    "kelompok": BudgetDetail.package_group.has(
                        PackageGroup.name.ilike(pattern, escape="\\")
                    ),
                    "rekening": BudgetDetail.account.has(
                        or_(
                            Account.code.ilike(pattern, escape="\\"),
                            Account.name.ilike(pattern, escape="\\"),
                        )
                    ),
                }.get(search_level)
                if target is not None:
                    filters.append(target)

        if not search and not level_search and not department_codes and not export_format:
            try:
                limit = int(request.args.get("limit", "10"))
                offset = int(request.args.get("offset", "0"))
            except ValueError as error:
                raise APIError(
                    400, "Parameter limit dan offset harus berupa bilangan bulat."
                ) from error
            if not 1 <= limit <= 500 or offset < 0:
                raise APIError(
                    400, "Limit harus 1–500 dan offset tidak boleh negatif."
                )

            total_department = session.scalar(
                select(func.count()).select_from(
                    select(BudgetDetail.organizational_unit_id)
                    .where(*filters)
                    .distinct()
                    .subquery()
                )
            ) or 0
            summary_rows = session.execute(
                select(
                    OrganizationalUnit.code,
                    OrganizationalUnit.name,
                    func.sum(func.coalesce(BudgetDetail.budget, 0)),
                )
                .join(BudgetDetail, BudgetDetail.organizational_unit_id == OrganizationalUnit.id)
                .where(*filters)
                .group_by(OrganizationalUnit.code, OrganizationalUnit.name)
                .order_by(OrganizationalUnit.name.asc())
                .limit(limit)
                .offset(offset)
            ).all()
            rows = [
                {
                    "nomor": None,
                    "level": "skpd",
                    "code": code,
                    "skpd": name,
                    "name": name,
                    "row_key": f"skpd:{quote(code, safe='')}",
                    "parent_key": None,
                    "root_code": code,
                    "has_children": True,
                    "pagu": budget,
                    "sumber_dana": None,
                    "tagging": [],
                }
                for code, name, budget in summary_rows
            ]
            return jsonify(
                {
                    "year": year,
                    "tahapan_id": stage_id,
                    "total": total_department,
                    "paginated": True,
                    "limit": limit,
                    "offset": offset,
                    "rows": rows,
                }
            )

        if department_codes:
            filters.append(BudgetDetail.organizational_unit.has(OrganizationalUnit.code.in_(department_codes)))

        limit = 0
        offset = 0
        if paginated:
            try:
                limit = int(request.args.get("limit", "10"))
                offset = int(request.args.get("offset", "0"))
            except ValueError as error:
                raise APIError(
                    400, "Parameter limit dan offset harus berupa bilangan bulat."
                ) from error
            if not 1 <= limit <= 500 or offset < 0:
                raise APIError(
                    400, "Limit harus 1–500 dan offset tidak boleh negatif."
                )

        group_columns = (
            BudgetDetail.organizational_unit_id,
            BudgetDetail.program_id,
            BudgetDetail.activity_id,
            BudgetDetail.subactivity_id,
        )
        group_sort_columns = (
            OrganizationalUnit.name.asc(),
            Program.name.asc(),
            Activity.name.asc(),
            Subactivity.name.asc(),
            Subactivity.code.asc(),
        )
        if paginated:
            total_groups = session.scalar(
                select(func.count()).select_from(
                    select(*group_columns).where(*filters).distinct().subquery()
                )
            ) or 0
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
                    .order_by(*group_sort_columns)
                    .limit(limit)
                    .offset(offset)
                ).all()
            ]
            if group_keys:
                aggregate_budget = {
                    tuple(row[:-1]): row[-1]
                    for row in session.execute(
                        select(
                            *group_columns,
                            func.sum(func.coalesce(BudgetDetail.budget, 0)),
                        )
                        .where(
                            BudgetDetail.year_id == year_id,
                            BudgetDetail.stage_id == stage_id,
                            tuple_(*group_columns).in_(group_keys),
                        )
                        .group_by(*group_columns)
                    ).all()
                }
                filters.append(tuple_(*group_columns).in_(group_keys))
            else:
                aggregate_budget = {}
                filters.append(BudgetDetail.id == -1)
        else:
            total_groups = 0
            aggregate_budget = None

        sort_columns = (
            OrganizationalUnit.name.asc(),
            Program.name.asc(),
            Activity.name.asc(),
            Subactivity.name.asc(),
            PackageGroup.name.asc(),
            Account.name.asc(),
            FundingSource.name.asc(),
            BudgetDetail.id.asc(),
        )
        statement = (
            select(
                BudgetDetail,
                OrganizationalUnit,
                Program,
                Activity,
                Subactivity,
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
            .where(*filters)
            .order_by(*sort_columns)
        )
        result_rows = session.execute(statement).all()
        subactivity_keys: set[tuple[int, int]] = set()
        for row in result_rows:
            budget = row[0]
            subactivity_keys.add(
                (budget.organizational_unit_id, budget.subactivity_id)
            )
        tagging_by_subactivity: dict[
            tuple[int, int, int | None], set[str]
        ] = defaultdict(set)
        if subactivity_keys:
            tagging_rows = session.execute(
                select(
                    SubactivityTagging.organizational_unit_id,
                    SubactivityTagging.subactivity_id,
                    SubactivityTagging.package_group_id,
                    TaggingType.code,
                )
                .join(TaggingType)
                .where(
                    SubactivityTagging.year_id == year_id,
                    tuple_(
                        SubactivityTagging.organizational_unit_id,
                        SubactivityTagging.subactivity_id,
                    ).in_(subactivity_keys),
                )
            ).all()
            for (
                organizational_unit_id,
                subactivity_id,
                package_id,
                tagging_code,
            ) in tagging_rows:
                tagging_by_subactivity[
                    (organizational_unit_id, subactivity_id, package_id)
                ].add(str(tagging_code))
        rows, built_group_count = build_hierarchy_rows(
            result_rows,
            limit=limit,
            offset=0 if paginated else offset,
            paginated=paginated,
            aggregate_budget=aggregate_budget,
            number_offset=offset if paginated else 0,
            tagging_by_subactivity=tagging_by_subactivity,
        )
        if not paginated:
            total_groups = built_group_count

    if export_format == "excel":
        workbook = Workbook(write_only=True)
        headers = [
            "Kode",
            "SKPD / Program / Kegiatan / Subkegiatan / Paket/Kelompok",
            "Pagu",
            "Sumber Dana",
        ]
        indentation = {
            "skpd": 0,
            "program": 1,
            "kegiatan": 2,
            "sub_kegiatan": 3,
            "paket": 4,
        }
        worksheets = {}
        used_titles: set[str] = set()

        for item in rows:
            if item["level"] == "rekening":
                continue
            root_code = item.get("root_code") or "Tanpa Sub Unit"
            if sheet_mode == "single":
                worksheet = worksheets.get("all")
                if worksheet is None:
                    worksheet = create_budget_export_sheet(
                        workbook, "Anggaran APBD", used_titles, headers
                    )
                    worksheets["all"] = worksheet
            else:
                worksheet = worksheets.get(root_code)
                if worksheet is None:
                    title = item["name"] if item["level"] == "skpd" else root_code
                    worksheet = create_budget_export_sheet(
                        workbook, title, used_titles, headers
                    )
                    worksheets[root_code] = worksheet
            worksheet.append([
                _excel_safe(item["code"]),
                _excel_safe(
                    f"{' ' * indentation.get(item['level'], 0)}{item['name'].strip()}"
                ),
                item["pagu"],
                _excel_safe(item["sumber_dana"]),
            ])
        if not worksheets:
            create_budget_export_sheet(
                workbook, "Anggaran APBD", used_titles, headers
            )

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"apbd-budget-{year}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return jsonify(
        {
            "year": year,
            "tahapan_id": stage_id,
            "total": total_groups,
            "paginated": paginated,
            "limit": limit if paginated else None,
            "offset": offset if paginated else None,
            "rows": rows,
        }
    )
