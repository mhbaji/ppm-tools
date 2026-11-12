"""Route handlers for authenticated administration and data management."""

from .admin_helpers import (
    ADMIN_UPLOAD_KINDS,
    _admin_upload_json,
    _catalog_item_used,
    _catalog_model,
    _master_item_used,
    _master_model,
    _master_year_id,
    _realization_statement,
    _save_admin_upload,
    _serialize_realization_rows,
    _valid_name,
    _valid_year,
    _year_has_data,
    _year_id,
)

import secrets
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from flask import (
    Blueprint,
    current_app,
    jsonify,
    request,
    send_from_directory,
    session as web_session,
)
from sqlalchemy import case, delete, exists, func, or_, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from ..importing import (
    MAX_IMPORT_SIZE,
    parse_budget_workbook,
    parse_tagging_workbook,
    save_budget_import,
)
from ..realization_importing import (
    parse_realization_workbook,
    save_realization_import,
)
from ..models import (
    BudgetDetail,
    AdminUpload,
    AdminNote,
    AdminUser,
    DatasetInfo,
    TaggingType,
    PackageGroup,
    Period,
    RealizationUpload,
    Department,
    DepartmentAlias,
    Stage,
    Subactivity,
    OrganizationalUnit,
    SubactivityTagging,
    PerformanceTarget,
    RequestEvent,
    ShortLink,
    ShortLinkClick,
    Year,
    DirectoryLink,
    LinkCategory,
)
from .common import (
    APIError,
    admin_required,
    check_csrf_token,
    escape_like,
    get_session,
    requested_stage_id,
    requested_year,
)
from .shortlink_helpers import (
    SHORTLINK_ALIAS_PATTERN,
    parse_shortlink_expiry,
    shortlink_json,
    valid_shortlink_url,
)


admin_blueprint = Blueprint("admin_api", __name__, url_prefix="/api")

STATISTICS_PERIODS = {
    "year": ("day", "%Y-%m-%d", 365),
    "month": ("day", "%Y-%m-%d", 30),
    "week": ("day", "%Y-%m-%d", 7),
    "day": ("hour", "%Y-%m-%dT%H", 24),
    "hour": ("minute", "%Y-%m-%dT%H:%M", 60),
}


def _statistics_bucket_start(value: datetime, resolution: str) -> datetime:
    """Round a UTC timestamp down to the requested reporting interval."""
    if resolution == "minute":
        return value.replace(second=0, microsecond=0)
    if resolution == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def _statistics_interval(resolution: str) -> timedelta:
    """Return the duration of one statistics bucket."""
    return {
        "minute": timedelta(minutes=1),
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
    }[resolution]


@admin_blueprint.get("/admin/statistics")
@admin_required
def get_admin_statistics():
    """Aggregate public page and API requests for a rolling time window."""
    period = request.args.get("period", "")
    if period not in STATISTICS_PERIODS:
        raise APIError(400, "Periode statistik tidak valid.")

    resolution, bucket_format, bucket_count = STATISTICS_PERIODS[period]
    until = datetime.now(timezone.utc).replace(tzinfo=None)
    bucket_end = _statistics_bucket_start(until, resolution)
    interval = _statistics_interval(resolution)
    since = bucket_end - interval * (bucket_count - 1)
    buckets = []
    current = since
    while len(buckets) < bucket_count:
        buckets.append(current.strftime(bucket_format))
        current += interval

    reports = {}
    with get_session() as database_session:
        for event_type in ("web", "api"):
            bucket_column = func.strftime(
                bucket_format, RequestEvent.bucket_start
            ).label("bucket")
            bucket_rows = database_session.execute(
                select(bucket_column, func.sum(RequestEvent.request_count))
                .where(
                    RequestEvent.event_type == event_type,
                    RequestEvent.resolution == resolution,
                    RequestEvent.bucket_start >= since,
                    RequestEvent.bucket_start <= bucket_end,
                )
                .group_by(bucket_column)
                .order_by(bucket_column)
            ).all()
            counts_by_bucket = {
                bucket: count for bucket, count in bucket_rows if bucket is not None
            }
            top_rows = database_session.execute(
                select(
                    RequestEvent.route,
                    func.sum(RequestEvent.request_count).label("count"),
                )
                .where(
                    RequestEvent.event_type == event_type,
                    RequestEvent.resolution == resolution,
                    RequestEvent.bucket_start >= since,
                    RequestEvent.bucket_start <= bucket_end,
                )
                .group_by(RequestEvent.route)
                .order_by(
                    func.sum(RequestEvent.request_count).desc(),
                    RequestEvent.route,
                )
                .limit(10)
            ).all()
            reports[event_type] = {
                "total": sum(counts_by_bucket.values()),
                "series": [
                    {"bucket": bucket, "count": counts_by_bucket.get(bucket, 0)}
                    for bucket in buckets
                ],
                "top_routes": [
                    {"route": route, "count": count} for route, count in top_rows
                ],
            }

    return jsonify(
        {
            "period": period,
            "timezone": "UTC",
            "since": since.isoformat(sep=" "),
            "until": until.isoformat(sep=" "),
            "resolution": resolution,
            "web": reports["web"],
            "api": reports["api"],
        }
    )


def _shortlink_year_counts(database_session, timestamp_column, model, year: int) -> dict:
    """Aggregate a timestamp column into the four requested calendar-year buckets."""
    current_start = datetime(year, 1, 1)
    previous_start = datetime(year - 1, 1, 1)
    older_start = datetime(year - 2, 1, 1)
    counts = database_session.execute(
        select(
            func.sum(
                case(
                    (timestamp_column >= current_start, 1),
                    else_=0,
                )
            ).label("this_year"),
            func.sum(
                case(
                    (
                        (timestamp_column >= previous_start)
                        & (timestamp_column < current_start),
                        1,
                    ),
                    else_=0,
                )
            ).label("year_minus_1"),
            func.sum(
                case(
                    (
                        (timestamp_column >= older_start)
                        & (timestamp_column < previous_start),
                        1,
                    ),
                    else_=0,
                )
            ).label("year_minus_2"),
            func.sum(
                case((timestamp_column < older_start, 1), else_=0)
            ).label("before_year_minus_2"),
        )
        .select_from(model)
    ).one()
    return {
        "this_year": counts.this_year or 0,
        "year_minus_1": counts.year_minus_1 or 0,
        "year_minus_2": counts.year_minus_2 or 0,
        "before_year_minus_2": counts.before_year_minus_2 or 0,
    }


def _shortlink_click_year_counts(database_session, year: int) -> dict:
    """Sum yearly click counters into the requested four calendar buckets."""
    counts = database_session.execute(
        select(
            func.sum(
                case(
                    (ShortLinkClick.year == year, ShortLinkClick.click_count),
                    else_=0,
                )
            ).label("this_year"),
            func.sum(
                case(
                    (
                        ShortLinkClick.year == year - 1,
                        ShortLinkClick.click_count,
                    ),
                    else_=0,
                )
            ).label("year_minus_1"),
            func.sum(
                case(
                    (
                        ShortLinkClick.year == year - 2,
                        ShortLinkClick.click_count,
                    ),
                    else_=0,
                )
            ).label("year_minus_2"),
            func.sum(
                case(
                    (
                        ShortLinkClick.year < year - 2,
                        ShortLinkClick.click_count,
                    ),
                    else_=0,
                )
            ).label("before_year_minus_2"),
        )
        .select_from(ShortLinkClick)
    ).one()
    return {
        "this_year": counts.this_year or 0,
        "year_minus_1": counts.year_minus_1 or 0,
        "year_minus_2": counts.year_minus_2 or 0,
        "before_year_minus_2": counts.before_year_minus_2 or 0,
    }


@admin_blueprint.get("/admin/shortlinks/summary")
@admin_required
def get_admin_shortlink_summary():
    """Return shortlink status counts and creation/click totals by calendar year."""
    year = datetime.now(timezone.utc).year
    with get_session() as database_session:
        counts = database_session.execute(
            select(
                func.count().label("total"),
                func.sum(case((ShortLink.is_active.is_(True), 1), else_=0)).label(
                    "active"
                ),
                func.sum(case((ShortLink.is_active.is_(False), 1), else_=0)).label(
                    "inactive"
                ),
            )
        ).one()
        created = _shortlink_year_counts(
            database_session, ShortLink.created_at, ShortLink, year
        )
        clicks = _shortlink_click_year_counts(database_session, year)
    return jsonify(
        {
            "year": year,
            "total": counts.total or 0,
            "active": counts.active or 0,
            "inactive": counts.inactive or 0,
            "created": created,
            "clicks": clicks,
        }
    )


@admin_blueprint.get("/admin/shortlinks")
@admin_required
def get_admin_shortlinks():
    """Search and paginate shortlinks with their click totals."""
    search = request.args.get("q", "").strip()
    try:
        limit = int(request.args.get("limit", "25"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise APIError(400, "Limit dan offset harus berupa bilangan bulat.") from error
    if not 1 <= limit <= 100 or offset < 0:
        raise APIError(400, "Limit harus 1–100 dan offset tidak boleh negatif.")

    filters = []
    if search:
        pattern = f"%{escape_like(search)}%"
        filters.append(
            or_(
                ShortLink.alias.ilike(pattern, escape="\\"),
                ShortLink.title.ilike(pattern, escape="\\"),
                ShortLink.target_url.ilike(pattern, escape="\\"),
            )
        )
    click_counts = (
        select(
            ShortLinkClick.short_link_id.label("short_link_id"),
            func.sum(ShortLinkClick.click_count).label("click_count"),
        )
        .group_by(ShortLinkClick.short_link_id)
        .subquery()
    )
    with get_session() as database_session:
        total = database_session.scalar(
            select(func.count()).select_from(ShortLink).where(*filters)
        ) or 0
        rows = database_session.execute(
            select(ShortLink, func.coalesce(click_counts.c.click_count, 0))
            .outerjoin(click_counts, click_counts.c.short_link_id == ShortLink.id)
            .where(*filters)
            .order_by(ShortLink.created_at.desc(), ShortLink.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    return jsonify(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [shortlink_json(link, clicks) for link, clicks in rows],
        }
    )


@admin_blueprint.post("/admin/shortlinks")
@admin_required
def create_admin_shortlink():
    """Create a shortlink from the authenticated admin page."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data shortlink tidak valid.")

    alias = body.get("alias")
    title = body.get("title")
    target_url = body.get("target_url")
    if not isinstance(alias, str) or not SHORTLINK_ALIAS_PATTERN.fullmatch(alias):
        raise APIError(400, "Alias shortlink tidak valid.")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        raise APIError(400, "Judul wajib diisi (maksimal 200 karakter).")
    if not valid_shortlink_url(target_url):
        raise APIError(400, "URL tujuan harus menggunakan HTTP atau HTTPS.")
    try:
        expires_at = parse_shortlink_expiry(body.get("expires_at"))
    except ValueError as error:
        raise APIError(400, str(error)) from error

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with get_session() as database_session:
        with database_session.begin():
            item = ShortLink(
                alias=alias,
                title=title.strip(),
                target_url=target_url.strip(),
                is_active=True,
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            database_session.add(item)
            try:
                database_session.flush()
            except IntegrityError as error:
                raise APIError(409, "Alias shortlink tersebut sudah digunakan.") from error
            result = shortlink_json(item)
    return jsonify({"created": True, "shortlink": result}), 201


@admin_blueprint.patch("/admin/shortlinks/<int:shortlink_id>")
@admin_required
def update_admin_shortlink(shortlink_id: int):
    """Edit a shortlink's alias, title, destination, or expiration time."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data shortlink tidak valid.")
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(ShortLink, shortlink_id)
            if item is None:
                raise APIError(404, "Shortlink tidak ditemukan.")
            alias = body.get("alias", item.alias)
            title = body.get("title", item.title)
            target_url = body.get("target_url", item.target_url)
            if (
                not isinstance(alias, str)
                or not SHORTLINK_ALIAS_PATTERN.fullmatch(alias)
            ):
                raise APIError(400, "Alias shortlink tidak valid.")
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
                raise APIError(400, "Judul wajib diisi (maksimal 200 karakter).")
            if not valid_shortlink_url(target_url):
                raise APIError(400, "URL tujuan harus menggunakan HTTP atau HTTPS.")
            if "expires_at" in body:
                try:
                    expires_at = parse_shortlink_expiry(body["expires_at"])
                except ValueError as error:
                    raise APIError(400, str(error)) from error
                item.expires_at = expires_at
            duplicate = database_session.scalar(
                select(ShortLink.id).where(
                    ShortLink.alias == alias,
                    ShortLink.id != shortlink_id,
                )
            )
            if duplicate is not None:
                raise APIError(409, "Alias shortlink tersebut sudah digunakan.")
            item.alias = alias
            item.title = title.strip()
            item.target_url = target_url.strip()
            item.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            try:
                database_session.flush()
            except IntegrityError as error:
                raise APIError(409, "Alias shortlink tersebut sudah digunakan.") from error
            result = shortlink_json(item)
    return jsonify({"updated": True, "shortlink": result})


@admin_blueprint.patch("/admin/shortlinks/<int:shortlink_id>/status")
@admin_required
def update_admin_shortlink_status(shortlink_id: int):
    """Enable or disable a shortlink."""
    body = request.get_json(silent=True)
    is_active = body.get("is_active") if isinstance(body, dict) else None
    if not isinstance(is_active, bool):
        raise APIError(400, "Status harus aktif atau nonaktif.")
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(ShortLink, shortlink_id)
            if item is None:
                raise APIError(404, "Shortlink tidak ditemukan.")
            item.is_active = is_active
            item.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return jsonify({"updated": True, "id": shortlink_id, "is_active": is_active})


@admin_blueprint.delete("/admin/shortlinks/<int:shortlink_id>")
@admin_required
def delete_admin_shortlink(shortlink_id: int):
    """Permanently remove a shortlink and its click history."""
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(ShortLink, shortlink_id)
            if item is None:
                raise APIError(404, "Shortlink tidak ditemukan.")
            database_session.execute(
                delete(ShortLinkClick).where(
                    ShortLinkClick.short_link_id == shortlink_id
                )
            )
            database_session.delete(item)
    return jsonify({"deleted": True, "id": shortlink_id})


@admin_blueprint.get("/admin/uploads")
@admin_required
def get_admin_uploads():
    """List uploaded admin workbooks with search and pagination."""
    kind = request.args.get("kind", "")
    search = request.args.get("q", "").strip()
    try:
        limit = int(request.args.get("limit", "10"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise APIError(400, "Limit dan offset harus berupa bilangan bulat.") from error
    if kind not in ADMIN_UPLOAD_KINDS:
        raise APIError(400, "Jenis file unggahan tidak valid.")
    if limit not in {10, 25, 50, 100} or offset < 0:
        raise APIError(400, "Limit harus 10, 25, 50, atau 100.")

    filters = [AdminUpload.kind == kind]
    if search:
        filters.append(
            AdminUpload.original_filename.ilike(
                f"%{escape_like(search)}%",
                escape="\\",
            )
        )
    with get_session() as database_session:
        total = database_session.scalar(
            select(func.count()).select_from(AdminUpload).where(*filters)
        ) or 0
        items = database_session.scalars(
            select(AdminUpload)
            .where(*filters)
            .order_by(AdminUpload.uploaded_at.desc(), AdminUpload.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
    return jsonify(
        {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [_admin_upload_json(item) for item in items],
        }
    )


@admin_blueprint.get("/admin/uploads/<kind>/<path:stored_filename>")
@admin_required
def download_admin_upload(kind: str, stored_filename: str):
    """Serve a stored admin workbook after authentication."""
    if kind not in ADMIN_UPLOAD_KINDS:
        raise APIError(404, "File unggahan tidak ditemukan.")
    url = f"/api/admin/uploads/{kind}/{stored_filename}"
    with get_session() as database_session:
        item = database_session.scalar(
            select(AdminUpload).where(AdminUpload.url == url)
        )
        if item is None:
            raise APIError(404, "File unggahan tidak ditemukan.")
        original_filename = item.original_filename
        storage_name = item.url.rsplit("/", 1)[-1]
    return send_from_directory(
        current_app.config["ADMIN_UPLOAD_DIR"],
        storage_name,
        as_attachment=True,
        download_name=original_filename,
        mimetype=item.file_type,
    )


@admin_blueprint.delete("/admin/uploads/<int:upload_id>")
@admin_required
def delete_admin_upload(upload_id: int):
    """Delete an uploaded workbook and its stored file."""
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(AdminUpload, upload_id)
            if item is None:
                raise APIError(404, "File unggahan tidak ditemukan.")
            storage_name = item.url.rsplit("/", 1)[-1]
            stored_path = Path(current_app.config["ADMIN_UPLOAD_DIR"]) / storage_name
            try:
                stored_path.unlink(missing_ok=True)
            except OSError as error:
                raise APIError(500, "File unggahan tidak dapat dihapus dari storage.") from error
            database_session.delete(item)
    return jsonify({"deleted": True, "id": upload_id})


@admin_blueprint.post("/admin/realisasi/import")
@admin_required
def import_admin_realization():
    """Validate and import a realization workbook."""
    upload = request.files.get("file")
    year_value = request.form.get("year", "")
    period_value = request.form.get("period_id", "")
    filename = secure_filename(upload.filename or "") if upload else ""
    if upload is None or not filename or Path(filename).suffix.lower() != ".xlsx":
        raise APIError(400, "Pilih file Excel berformat .xlsx.")
    if not year_value.isdecimal() or not 1900 <= int(year_value) <= 2200:
        raise APIError(400, "Tahun impor harus berupa tahun yang valid.")
    if not period_value.isdecimal():
        raise APIError(400, "Pilih periode yang tersedia.")
    if request.content_length and request.content_length > MAX_IMPORT_SIZE + 1024 * 1024:
        raise APIError(413, "Ukuran file maksimal 30 MB.")

    try:
        file_bytes = upload.read(MAX_IMPORT_SIZE + 1)
        import_rows = parse_realization_workbook(file_bytes)
    except ValueError as error:
        raise APIError(400, str(error)) from error

    stored_filename = f"{uuid4().hex}.xlsx"
    upload_directory = Path(current_app.config["REALIZATION_UPLOAD_DIR"])
    upload_directory.mkdir(parents=True, exist_ok=True)
    stored_path = upload_directory / stored_filename
    stored_path.write_bytes(file_bytes)

    try:
        with get_session() as database_session:
            with database_session.begin():
                year = int(year_value)
                period_id = int(period_value)
                year_record = database_session.scalar(
                    select(Year).where(Year.name == year)
                )
                period = database_session.get(Period, period_id)
                if year_record is None:
                    raise APIError(404, f"Tahun {year} tidak tersedia.")
                if period is None:
                    raise APIError(404, "Periode tidak ditemukan.")
                imported, warnings = save_realization_import(
                    database_session,
                    import_rows,
                    year,
                    period_id,
                )
                metadata = RealizationUpload(
                    original_filename=upload.filename or filename,
                    stored_filename=stored_filename,
                    year_id=year_record.id,
                    period_id=period_id,
                    uploaded_at=datetime.now(),
                    imported_rows=imported,
                )
                database_session.add(metadata)
                database_session.flush()
                result = {
                    "id": metadata.id,
                    "year": year,
                    "period_id": period_id,
                    "period": period.name,
                    "filename": metadata.original_filename,
                    "uploaded_at": metadata.uploaded_at.isoformat(sep=" "),
                    "imported_rows": imported,
                    "warnings": warnings,
                }
    except (APIError, SQLAlchemyError):
        stored_path.unlink(missing_ok=True)
        raise

    return jsonify(result), 201


@admin_blueprint.get("/admin/realisasi/uploads")
@admin_required
def get_admin_realization_uploads():
    """List realization imports and their metadata."""
    year_value = request.args.get("year", "")
    if not year_value.isdecimal():
        raise APIError(400, "Parameter year harus berupa tahun yang valid.")
    with get_session() as database_session:
        year_id = _year_id(database_session, int(year_value))
        if year_id is None:
            raise APIError(404, f"Tahun {year_value} tidak tersedia.")
        uploads = database_session.execute(
            select(RealizationUpload, Period.name)
            .join(Period, Period.id == RealizationUpload.period_id)
            .where(RealizationUpload.year_id == year_id)
            .order_by(RealizationUpload.uploaded_at.desc(), RealizationUpload.id.desc())
        ).all()
    return jsonify(
        {
            "uploads": [
                {
                    "id": item.id,
                    "filename": item.original_filename,
                    "uploaded_at": item.uploaded_at.isoformat(sep=" "),
                    "year": int(year_value),
                    "period_id": item.period_id,
                    "period": period_name,
                    "imported_rows": item.imported_rows,
                    "download_url": f"/api/admin/realisasi/uploads/{item.id}/download",
                }
                for item, period_name in uploads
            ]
        }
    )


@admin_blueprint.get("/admin/realisasi/uploads/<int:upload_id>/download")
@admin_required
def download_admin_realization_upload(upload_id: int):
    """Download a previously imported realization workbook."""
    with get_session() as database_session:
        item = database_session.get(RealizationUpload, upload_id)
        if item is None:
            raise APIError(404, "File impor tidak ditemukan.")
        stored_filename = item.stored_filename
        original_filename = item.original_filename
    return send_from_directory(
        current_app.config["REALIZATION_UPLOAD_DIR"],
        stored_filename,
        as_attachment=True,
        download_name=original_filename,
    )


@admin_blueprint.get("/admin/realisasi")
@admin_required
def get_admin_realization():
    """Return realization and performance data for the admin dashboard."""
    year_value = request.args.get("year", "")
    period_value = request.args.get("period_id", "")
    if not year_value.isdecimal() or not period_value.isdecimal():
        raise APIError(400, "Tahun dan periode wajib dipilih.")
    try:
        limit = int(request.args.get("limit", "10"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise APIError(400, "Limit dan offset harus berupa bilangan bulat.") from error
    if not 1 <= limit <= 1000 or offset < 0:
        raise APIError(400, "Limit harus 1–1000 dan offset tidak boleh negatif.")

    with get_session() as database_session:
        year = int(year_value)
        year_id = _year_id(database_session, year)
        period_id = int(period_value)
        if year_id is None:
            raise APIError(404, f"Tahun {year} tidak tersedia.")
        if database_session.get(Period, period_id) is None:
            raise APIError(404, "Periode tidak ditemukan.")
        statement = _realization_statement(
            year_id,
            period_id,
            request.args.get("q", "").strip(),
        )
        total = database_session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        ) or 0
        rows = database_session.execute(
            statement.limit(limit).offset(offset)
        ).all()
    serialized_rows = _serialize_realization_rows(rows)
    return jsonify(
        {
            "year": year,
            "period_id": period_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "rows": serialized_rows,
        }
    )


@admin_blueprint.get("/admin/sub-kegiatan/summary")
@admin_required
def get_admin_subactivity_summary():
    """Summarize imported subactivities for the admin interface."""
    with get_session() as database_session:
        year = requested_year(database_session)
        year_id = _year_id(database_session, year)
        stage_id = requested_stage_id(database_session, year)
        filters = (
            BudgetDetail.year_id == year_id,
            BudgetDetail.stage_id == stage_id,
        )
        summary = database_session.execute(
            select(
                func.count(func.distinct(BudgetDetail.department_id)),
                func.count(func.distinct(BudgetDetail.program_id)),
                func.count(func.distinct(BudgetDetail.activity_id)),
                func.count(func.distinct(BudgetDetail.subactivity_id)),
            ).where(*filters)
        ).one()
    return jsonify(
        {
            "year": year,
            "tahapan_id": stage_id,
            "skpd": summary[0],
            "program": summary[1],
            "kegiatan": summary[2],
            "sub_kegiatan": summary[3],
        }
    )


@admin_blueprint.post("/admin/sub-kegiatan/import")
@admin_required
def import_admin_subactivities():
    """Validate and import a budget workbook for subactivities."""
    upload = request.files.get("file")
    year_value = request.form.get("year", "")
    stage_value = request.form.get("tahapan_id", "")
    filename = secure_filename(upload.filename or "") if upload else ""
    if upload is None or not filename or Path(filename).suffix.lower() != ".xlsx":
        raise APIError(400, "Pilih file Excel berformat .xlsx.")
    if not year_value.isdecimal() or not 1900 <= int(year_value) <= 2200:
        raise APIError(400, "Tahun impor harus berupa tahun yang valid.")
    if not stage_value.isdecimal():
        raise APIError(400, "Pilih jenis tahapan yang tersedia.")
    if request.content_length and request.content_length > MAX_IMPORT_SIZE + 1024 * 1024:
        raise APIError(413, "Ukuran file maksimal 30 MB.")

    file_bytes = upload.read(MAX_IMPORT_SIZE + 1)
    if len(file_bytes) > MAX_IMPORT_SIZE:
        raise APIError(413, "Ukuran file maksimal 30 MB.")
    try:
        rows = parse_budget_workbook(file_bytes, int(year_value))
        with get_session() as database_session:
            with database_session.begin():
                stage = database_session.get(Stage, int(stage_value))
                if stage is None or stage.year.name != int(year_value):
                    raise APIError(400, "Jenis tahapan tidak tersedia untuk tahun tersebut.")
                imported, stage_name = save_budget_import(
                    database_session,
                    rows,
                    int(year_value),
                    int(stage_value),
                )
                metadata = _save_admin_upload(
                    database_session,
                    upload,
                    file_bytes,
                    "sub_kegiatan",
                )
    except ValueError as error:
        raise APIError(400, str(error)) from error
    except OSError as error:
        raise APIError(500, "File impor tidak dapat disimpan ke storage.") from error

    return jsonify(
        {
            "imported": imported,
            "year": int(year_value),
            "tahapan_id": int(stage_value),
            "tahapan_name": stage_name,
            "file": _admin_upload_json(metadata),
        }
    ), 201


@admin_blueprint.post("/admin/tagging-sub-kegiatan/import")
@admin_required
def import_admin_tagging():
    """Validate and import tagging assignments from a workbook."""
    upload = request.files.get("file")
    year_value = request.form.get("year", "")
    tagging_code_value = request.form.get("tagging_code", "")
    scope = request.form.get("scope", "both")
    filename = secure_filename(upload.filename or "") if upload else ""
    if upload is None or not filename or Path(filename).suffix.lower() != ".xlsx":
        raise APIError(400, "Pilih file Excel berformat .xlsx.")
    if (
        not year_value.isdecimal()
        or not tagging_code_value.isdecimal()
        or scope not in {"sub_kegiatan", "paket_kelompok", "both"}
    ):
        raise APIError(400, "Tahun dan jenis tagging wajib dipilih.")
    if request.content_length and request.content_length > MAX_IMPORT_SIZE + 1024 * 1024:
        raise APIError(413, "Ukuran file maksimal 30 MB.")
    year = int(year_value)
    tagging_code = int(tagging_code_value)

    file_bytes = upload.read(MAX_IMPORT_SIZE + 1)
    if len(file_bytes) > MAX_IMPORT_SIZE:
        raise APIError(413, "Ukuran file maksimal 30 MB.")
    try:
        import_rows = parse_tagging_workbook(file_bytes, scope)
    except ValueError as error:
        raise APIError(400, str(error)) from error

    with get_session() as database_session:
        with database_session.begin():
            year_id = _year_id(database_session, year)
            tagging_type = database_session.scalar(
                select(TaggingType).where(
                    TaggingType.code == tagging_code,
                    TaggingType.year_id == year_id,
                )
            )
            if tagging_type is None:
                raise APIError(400, "Jenis tagging tidak tersedia untuk tahun tersebut.")

            tagged_items: set[tuple[int, int, int | None]] = set()
            warnings: list[str] = []
            for import_row in import_rows:
                row_number = import_row["row_number"]
                unit_statement = select(OrganizationalUnit).where(OrganizationalUnit.year_id == year_id)
                if import_row["sub_unit_code"]:
                    unit_statement = unit_statement.where(
                        OrganizationalUnit.code == import_row["sub_unit_code"]
                    )
                else:
                    unit_statement = unit_statement.where(
                        func.lower(OrganizationalUnit.name)
                        == import_row["sub_unit_name"].casefold()
                    )
                units = database_session.scalars(unit_statement).all()
                if len(units) != 1:
                    warnings.append(
                        f"Baris {row_number}: sub unit "
                        f"{import_row['sub_unit_code'] or import_row['sub_unit_name']} "
                        "tidak ditemukan atau ambigu."
                    )
                    continue
                unit = units[0]
                if (
                    import_row["sub_unit_name"]
                    and unit.name.strip().casefold()
                    != import_row["sub_unit_name"].strip().casefold()
                ):
                    warnings.append(
                        f"Baris {row_number}: nama sub unit berbeda; kode sub unit digunakan."
                    )

                activity_statement = select(Subactivity).where(
                    Subactivity.year_id == year_id
                )
                if import_row["sub_kegiatan_code"]:
                    activity_statement = activity_statement.where(
                        Subactivity.code == import_row["sub_kegiatan_code"]
                    )
                else:
                    activity_statement = activity_statement.where(
                        func.lower(Subactivity.name)
                        == import_row["sub_kegiatan_name"].casefold()
                    )
                activities = database_session.scalars(activity_statement).all()
                if len(activities) != 1:
                    warnings.append(
                        f"Baris {row_number}: sub kegiatan "
                        f"{import_row['sub_kegiatan_code'] or import_row['sub_kegiatan_name']} "
                        "tidak ditemukan atau ambigu."
                    )
                    continue
                activity = activities[0]
                if (
                    import_row["sub_kegiatan_name"]
                    and activity.name.strip().casefold()
                    != import_row["sub_kegiatan_name"].strip().casefold()
                ):
                    warnings.append(
                        f"Baris {row_number}: nama sub kegiatan berbeda; "
                        "kode sub kegiatan digunakan."
                    )

                package_name = import_row["paket_kelompok_name"]
                include_package = scope in {"paket_kelompok", "both"} and bool(package_name)
                statement = (
                    select(BudgetDetail.package_group_id)
                    .where(
                        BudgetDetail.year_id == year_id,
                        BudgetDetail.organizational_unit_id == unit.id,
                        BudgetDetail.subactivity_id == activity.id,
                    )
                    .distinct()
                )
                if include_package:
                    statement = (
                        statement.join(
                            PackageGroup,
                            PackageGroup.id == BudgetDetail.package_group_id,
                        )
                        .where(PackageGroup.name == package_name)
                    )
                package_ids = database_session.scalars(statement).all()
                if not package_ids:
                    warnings.append(
                        f"Baris {row_number}: tidak ditemukan rincian anggaran untuk "
                        f"{unit.code}/{activity.code}"
                        + (f"/{package_name}" if include_package else "")
                        + "."
                    )
                    continue
                for package_id in package_ids:
                    if not include_package:
                        package_id = None
                    tagged_items.add((unit.id, activity.id, package_id))

            imported = 0
            ignored = 0
            for organizational_unit_id, subactivity_id, package_id in tagged_items:
                exact_match = database_session.scalar(
                    select(SubactivityTagging).where(
                        SubactivityTagging.year_id == year_id,
                        SubactivityTagging.organizational_unit_id == organizational_unit_id,
                        SubactivityTagging.subactivity_id == subactivity_id,
                        SubactivityTagging.tagging_type_id == tagging_type.id,
                        SubactivityTagging.package_group_id == package_id,
                    )
                )
                if exact_match is not None:
                    ignored += 1
                    continue
                base_match = database_session.scalar(
                    select(SubactivityTagging).where(
                        SubactivityTagging.year_id == year_id,
                        SubactivityTagging.organizational_unit_id == organizational_unit_id,
                        SubactivityTagging.subactivity_id == subactivity_id,
                        SubactivityTagging.tagging_type_id == tagging_type.id,
                        SubactivityTagging.package_group_id.is_(None),
                    )
                )
                if package_id is not None and base_match is not None:
                    base_match.package_group_id = package_id
                else:
                    database_session.add(
                        SubactivityTagging(
                            year_id=year_id,
                            organizational_unit_id=organizational_unit_id,
                            subactivity_id=subactivity_id,
                            tagging_type_id=tagging_type.id,
                            package_group_id=package_id,
                        )
                    )
                imported += 1
            metadata = _save_admin_upload(
                database_session,
                upload,
                file_bytes,
                "tagging_sub_kegiatan",
            )

    return jsonify(
        {
            "imported": imported,
            "ignored": ignored,
            "year": year,
            "tagging_code": tagging_code,
            "scope": scope,
            "warnings": warnings[:200],
            "file": _admin_upload_json(metadata),
        }
    ), 201


@admin_blueprint.get("/auth/session")
def get_auth_session():
    """Report the current admin session and its CSRF token."""
    csrf_token = web_session.get("csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        web_session["csrf_token"] = csrf_token

    admin_id = web_session.get("admin_user_id")
    username = None
    if isinstance(admin_id, int):
        with get_session() as database_session:
            admin = database_session.get(AdminUser, admin_id)
            if admin is not None and admin.is_active:
                username = admin.username
            else:
                web_session.clear()
                csrf_token = secrets.token_urlsafe(32)
                web_session["csrf_token"] = csrf_token

    return jsonify(
        {
            "authenticated": username is not None,
            "username": username,
            "csrf_token": csrf_token,
        }
    )

@admin_blueprint.post("/auth/login")
def login():
    """Authenticate an administrator and establish a protected session."""
    if not check_csrf_token():
        return jsonify({"error": "Token keamanan tidak valid. Muat ulang halaman."}), 403
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data login tidak valid.")

    username = body.get("username")
    password = body.get("password")
    if not isinstance(username, str) or not isinstance(password, str):
        raise APIError(400, "Username dan password wajib diisi.")
    username = username.strip()
    if not username or not password or len(username) > 200 or len(password) > 1024:
        return jsonify({"error": "Username atau password salah."}), 401

    with get_session() as database_session:
        admin = database_session.scalar(
            select(AdminUser).where(AdminUser.username == username)
        )
        if (
            admin is None
            or not admin.is_active
            or not check_password_hash(admin.password_hash, password)
        ):
            return jsonify({"error": "Username atau password salah."}), 401
        admin_id = admin.id
        admin_username = admin.username

    session_csrf_token = secrets.token_urlsafe(32)
    web_session.clear()
    web_session["admin_user_id"] = admin_id
    web_session["csrf_token"] = session_csrf_token
    return jsonify(
        {
            "authenticated": True,
            "username": admin_username,
            "csrf_token": session_csrf_token,
        }
    )

@admin_blueprint.post("/auth/logout")
@admin_required
def logout():
    """Clear the authenticated administrator session."""
    web_session.clear()
    return jsonify({"authenticated": False})

@admin_blueprint.get("/admin/edit-policy")
@admin_required
def get_admin_edit_policy():
    """Return the current admin editing policy."""
    with get_session() as database_session:
        notes = database_session.scalars(
            select(AdminNote).order_by(AdminNote.key)
        ).all()
    return jsonify(
        {
            "editable_data": [
                {"key": note.key, "description": note.description}
                for note in notes
            ]
        }
    )


@admin_blueprint.get("/admin/years")
@admin_required
def get_admin_years():
    """List years available for admin data management."""
    with get_session() as database_session:
        years = database_session.scalars(
            select(Year).order_by(Year.name.desc())
        ).all()
    return jsonify(
        {"years": [{"id": item.id, "year": item.name} for item in years]}
    )


@admin_blueprint.post("/admin/years")
@admin_required
def create_admin_year():
    """Create a supported calendar year."""
    body = request.get_json(silent=True)
    year = body.get("year") if isinstance(body, dict) else None
    if not _valid_year(year):
        raise APIError(400, "Tahun harus berupa angka antara 1900 dan 2200.")
    with get_session() as database_session:
        with database_session.begin():
            if _year_id(database_session, year) is not None:
                raise APIError(409, "Tahun tersebut sudah tersedia.")
            item = Year(name=year)
            database_session.add(item)
            database_session.flush()
            result = {"id": item.id, "year": item.name}
    return jsonify({"created": True, **result}), 201


@admin_blueprint.patch("/admin/years/<int:year_id>")
@admin_required
def update_admin_year(year_id: int):
    """Update an existing calendar year."""
    body = request.get_json(silent=True)
    year = body.get("year") if isinstance(body, dict) else None
    if not _valid_year(year):
        raise APIError(400, "Tahun harus berupa angka antara 1900 dan 2200.")
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(Year, year_id)
            if item is None:
                raise APIError(404, "Tahun tidak ditemukan.")
            duplicate = database_session.scalar(
                select(Year.id).where(Year.name == year, Year.id != year_id)
            )
            if duplicate is not None:
                raise APIError(409, "Tahun tersebut sudah tersedia.")
            if item.name != year and _year_has_data(database_session, year_id):
                raise APIError(409, "Tahun tidak dapat diubah karena sudah digunakan.")
            item.name = year
            result = {"id": item.id, "year": item.name}
    return jsonify({"updated": True, **result})


@admin_blueprint.delete("/admin/years/<int:year_id>")
@admin_required
def delete_admin_year(year_id: int):
    """Delete a year only when its data can be safely removed."""
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(Year, year_id)
            if item is None:
                raise APIError(404, "Tahun tidak ditemukan.")
            if _year_has_data(database_session, year_id):
                raise APIError(409, "Tahun tidak dapat dihapus karena sudah digunakan.")
            database_session.delete(item)
    return jsonify({"deleted": True, "id": year_id})


@admin_blueprint.get("/admin/tahapan")
@admin_required
def get_admin_stage():
    """List budget stages for the selected year."""
    year_value = request.args.get("year", "")
    if not year_value.isdecimal():
        raise APIError(400, "Parameter year harus berupa tahun yang valid.")
    with get_session() as database_session:
        year_id = _year_id(database_session, int(year_value))
        stages = database_session.scalars(
            select(Stage)
            .where(Stage.year_id == year_id)
            .order_by(Stage.code, Stage.name)
        ).all()
    return jsonify(
        {
            "tahapan": [
                {
                    "id": stage.id,
                    "code": stage.code,
                    "name": stage.name,
                    "year": int(year_value),
                }
                for stage in stages
            ]
        }
    )


@admin_blueprint.post("/admin/tahapan")
@admin_required
def create_admin_stage():
    """Create a budget stage for a selected year."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data tahapan tidak valid.")
    code = body.get("code")
    name = body.get("name")
    year = body.get("year")
    if (
        not isinstance(code, int)
        or isinstance(code, bool)
        or code < 0
        or not isinstance(name, str)
        or not name.strip()
        or len(name.strip()) > 200
        or not _valid_year(year)
    ):
        raise APIError(400, "Kode, nama, dan tahun tahapan wajib diisi dengan benar.")
    with get_session() as database_session:
        with database_session.begin():
            year_id = _year_id(database_session, year)
            if year_id is None:
                raise APIError(400, "Tahun belum tersedia.")
            duplicate = database_session.scalar(
                select(Stage.id).where(
                    Stage.year_id == year_id,
                    or_(
                        Stage.code == code,
                        func.lower(Stage.name) == name.strip().lower(),
                    ),
                )
            )
            if duplicate is not None:
                raise APIError(409, "Kode atau nama tahapan sudah digunakan.")
            stage = Stage(code=code, name=name.strip(), year_id=year_id)
            database_session.add(stage)
            database_session.flush()
            result = {"id": stage.id, "code": stage.code, "name": stage.name, "year": year}
    return jsonify({"created": True, **result}), 201


@admin_blueprint.patch("/admin/tahapan/<int:tahapan_id>")
@admin_required
def update_admin_stage(stage_id: int):
    """Update a budget stage and its year association."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data tahapan tidak valid.")
    code = body.get("code")
    name = body.get("name")
    year = body.get("year")
    if (
        not isinstance(code, int)
        or isinstance(code, bool)
        or code < 0
        or not isinstance(name, str)
        or not name.strip()
        or len(name.strip()) > 200
        or not _valid_year(year)
    ):
        raise APIError(400, "Kode, nama, dan tahun tahapan wajib diisi dengan benar.")
    with get_session() as database_session:
        with database_session.begin():
            stage = database_session.get(Stage, stage_id)
            year_id = _year_id(database_session, year)
            if stage is None:
                raise APIError(404, "Tahapan tidak ditemukan.")
            if year_id is None:
                raise APIError(400, "Tahun belum tersedia.")
            duplicate = database_session.scalar(
                select(Stage.id).where(
                    Stage.year_id == year_id,
                    or_(
                        Stage.code == code,
                        func.lower(Stage.name) == name.strip().lower(),
                    ),
                    Stage.id != stage_id,
                )
            )
            if duplicate is not None:
                raise APIError(409, "Kode atau nama tahapan sudah digunakan.")
            has_budget = database_session.scalar(
                select(BudgetDetail.id).where(BudgetDetail.stage_id == stage_id).limit(1)
            )
            if has_budget is not None and stage.year_id != year_id:
                raise APIError(409, "Tahun tahapan tidak dapat diubah karena memiliki data anggaran.")
            stage.code = code
            stage.name = name.strip()
            stage.year_id = year_id
            result = {"id": stage.id, "code": stage.code, "name": stage.name, "year": year}
    return jsonify({"updated": True, **result})


@admin_blueprint.delete("/admin/tahapan/<int:tahapan_id>")
@admin_required
def delete_admin_stage(stage_id: int):
    """Delete a budget stage when it is safe to remove."""
    with get_session() as database_session:
        with database_session.begin():
            stage = database_session.get(Stage, stage_id)
            if stage is None:
                raise APIError(404, "Tahapan tidak ditemukan.")
            has_budget = database_session.scalar(
                select(BudgetDetail.id).where(BudgetDetail.stage_id == stage_id).limit(1)
            )
            if has_budget is not None:
                raise APIError(409, "Tahapan tidak dapat dihapus karena memiliki data anggaran.")
            database_session.execute(
                delete(DatasetInfo).where(DatasetInfo.stage_id == stage_id)
            )
            database_session.delete(stage)
    return jsonify({"deleted": True, "id": stage_id})


@admin_blueprint.get("/admin/sub-kegiatan/imports")
@admin_required
def get_admin_imports():
    """List subactivity imports and their source workbooks."""
    year_value = request.args.get("year", "")
    if not year_value.isdecimal():
        raise APIError(400, "Parameter year harus berupa tahun yang valid.")
    with get_session() as database_session:
        year_id = _year_id(database_session, int(year_value))
        imports = database_session.execute(
            select(
                DatasetInfo.id,
                Stage.id,
                Stage.code,
                Stage.name,
                DatasetInfo.updated_at,
                func.count(BudgetDetail.id),
            )
            .join(Stage, Stage.id == DatasetInfo.stage_id)
            .outerjoin(
                BudgetDetail,
                (BudgetDetail.year_id == DatasetInfo.year_id)
                & (BudgetDetail.stage_id == DatasetInfo.stage_id),
            )
            .where(DatasetInfo.year_id == year_id)
            .group_by(
                DatasetInfo.id,
                Stage.id,
                Stage.code,
                Stage.name,
                DatasetInfo.updated_at,
            )
            .order_by(Stage.code, Stage.name)
        ).all()
    return jsonify(
        {
            "imports": [
                {
                    "id": row[0],
                    "tahapan_id": row[1],
                    "code": row[2],
                    "name": row[3],
                    "updated_at": row[4].isoformat(sep=" "),
                    "rows": row[5],
                    "year": int(year_value),
                }
                for row in imports
            ]
        }
    )


@admin_blueprint.delete("/admin/sub-kegiatan/imports/<int:tahapan_id>")
@admin_required
def delete_admin_import(stage_id: int):
    """Remove an imported subactivity dataset and its metadata."""
    year_value = request.args.get("year", "")
    if not year_value.isdecimal():
        raise APIError(400, "Parameter year harus berupa tahun yang valid.")
    with get_session() as database_session:
        with database_session.begin():
            year_id = _year_id(database_session, int(year_value))
            if year_id is None:
                raise APIError(404, "Tahun tidak ditemukan.")
            info = database_session.scalar(
                select(DatasetInfo).where(
                    DatasetInfo.year_id == year_id,
                    DatasetInfo.stage_id == stage_id,
                )
            )
            if info is None:
                raise APIError(404, "Riwayat impor tidak ditemukan.")
            database_session.execute(
                delete(BudgetDetail).where(
                    BudgetDetail.year_id == year_id,
                    BudgetDetail.stage_id == stage_id,
                )
            )
            database_session.delete(info)
    return jsonify({"deleted": True, "year": int(year_value), "tahapan_id": stage_id})


@admin_blueprint.get("/admin/tagging")
@admin_blueprint.get("/admin/tagging-sub-kegiatan")
@admin_required
def get_admin_tagging():
    """Return tagging assignments with filters and pagination."""
    try:
        limit = int(request.args.get("limit", "10"))
        offset = int(request.args.get("offset", "0"))
    except ValueError as error:
        raise APIError(400, "Parameter limit dan offset harus berupa bilangan bulat.") from error
    if not 1 <= limit <= 200 or offset < 0:
        raise APIError(400, "Limit harus 1–200 dan offset tidak boleh negatif.")

    search = request.args.get("q", "").strip()
    tagging_code_value = request.args.get("tagging_code", "")
    scope = request.args.get("scope", "sub_kegiatan")
    if scope not in {"sub_kegiatan", "paket_kelompok"}:
        raise APIError(400, "Parameter scope tidak valid.")
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

        item_columns = [
            OrganizationalUnit.id,
            OrganizationalUnit.code,
            OrganizationalUnit.name,
            Subactivity.id,
            Subactivity.code,
            Subactivity.name,
            Department.name,
        ]
        item_statement = (
            select(*item_columns)
            .join(BudgetDetail, BudgetDetail.organizational_unit_id == OrganizationalUnit.id)
            .join(Subactivity, Subactivity.id == BudgetDetail.subactivity_id)
            .join(Department, Department.id == BudgetDetail.department_id)
            .where(*filters)
        )
        if scope == "paket_kelompok":
            item_statement = item_statement.add_columns(
                PackageGroup.id,
                PackageGroup.name,
            ).join(
                PackageGroup,
                PackageGroup.id == BudgetDetail.package_group_id,
            )

        if tagging_code_value:
            tagging_code = int(tagging_code_value)
            tagging_type = database_session.scalar(
                select(TaggingType).where(
                    TaggingType.code == tagging_code,
                    TaggingType.year_id == year_id,
                )
            )
            if tagging_type is None:
                raise APIError(400, "Jenis tagging tidak tersedia untuk tahun yang dipilih.")
            tag_exists = exists(
                select(1).where(
                    SubactivityTagging.year_id == year_id,
                    SubactivityTagging.tagging_type_id == tagging_type.id,
                    SubactivityTagging.organizational_unit_id == OrganizationalUnit.id,
                    SubactivityTagging.subactivity_id == Subactivity.id,
                    (
                        SubactivityTagging.package_group_id.is_not(None)
                        if scope == "paket_kelompok"
                        else SubactivityTagging.package_group_id.is_(None)
                    ),
                )
            )
            if scope == "paket_kelompok":
                tag_exists = exists(
                    select(1).where(
                        SubactivityTagging.year_id == year_id,
                        SubactivityTagging.tagging_type_id == tagging_type.id,
                        SubactivityTagging.organizational_unit_id == OrganizationalUnit.id,
                        SubactivityTagging.subactivity_id == Subactivity.id,
                        SubactivityTagging.package_group_id == PackageGroup.id,
                    )
                )
            item_statement = item_statement.where(tag_exists)

        item_statement = item_statement.distinct()
        total = database_session.scalar(
            select(func.count()).select_from(item_statement.subquery())
        ) or 0
        tagging_type = database_session.execute(
            select(TaggingType.code, TaggingType.name)
            .where(TaggingType.year_id == year_id)
            .order_by(TaggingType.name.asc(), TaggingType.code.asc())
        ).all()
        sort_columns = [OrganizationalUnit.name.asc(), Subactivity.name.asc()]
        if scope == "paket_kelompok":
            sort_columns.append(PackageGroup.name.asc())
        items = database_session.execute(
            item_statement.order_by(*sort_columns).limit(limit).offset(offset)
        ).all()

        organizational_unit_ids = [item[0] for item in items]
        subactivity_ids = [item[3] for item in items]
        tagging_rows = []
        if items:
            tag_statement = (
                select(
                    SubactivityTagging.organizational_unit_id,
                    SubactivityTagging.subactivity_id,
                    SubactivityTagging.package_group_id,
                    TaggingType.code,
                )
                .join(TaggingType)
                .where(
                    SubactivityTagging.year_id == year_id,
                    SubactivityTagging.organizational_unit_id.in_(organizational_unit_ids),
                    SubactivityTagging.subactivity_id.in_(subactivity_ids),
                    (
                        SubactivityTagging.package_group_id.is_not(None)
                        if scope == "paket_kelompok"
                        else SubactivityTagging.package_group_id.is_(None)
                    ),
                )
            )
            tagging_rows = database_session.execute(tag_statement).all()

    tags_by_item: dict[tuple[int, int, int | None], list[str]] = defaultdict(list)
    for organizational_unit_id, subactivity_id, package_id, tagging_code in tagging_rows:
        tags_by_item[(organizational_unit_id, subactivity_id, package_id)].append(
            str(tagging_code)
        )
    return jsonify(
        {
            "year": year,
            "tahapan_id": stage_id,
            "scope": scope,
            "total": total,
            "limit": limit,
            "offset": offset,
            "tagging_types": [
                {"code": str(code), "name": name} for code, name in tagging_type
            ],
            "items": [
                {
                    "sub_unit_id": item[0],
                    "sub_unit_code": item[1],
                    "sub_unit_name": item[2],
                    "sub_kegiatan_id": item[3],
                    "sub_kegiatan_code": item[4],
                    "sub_kegiatan_name": item[5],
                    "skpd_name": item[6],
                    "paket_kelompok_id": item[7] if scope == "paket_kelompok" else None,
                    "paket_kelompok_name": item[8] if scope == "paket_kelompok" else None,
                    "tagging_codes": sorted(
                        tags_by_item.get(
                            (
                                item[0],
                                item[3],
                                item[7] if scope == "paket_kelompok" else None,
                            ),
                            [],
                        )
                    ),
                }
                for item in items
            ],
        }
    )


@admin_blueprint.get("/admin/tagging-types")
@admin_required
def get_admin_tagging_types():
    """List tagging types available for admin management."""
    year_value = request.args.get("year")
    if year_value is not None and not year_value.isdecimal():
        raise APIError(400, "Parameter year harus berupa tahun yang valid.")

    with get_session() as database_session:
        statement = select(TaggingType)
        if year_value is not None:
            year_id = _year_id(database_session, int(year_value))
            statement = statement.where(TaggingType.year_id == year_id)
        tagging_type = database_session.execute(
            statement.order_by(
                TaggingType.year_id.desc(),
                TaggingType.name.asc(),
                TaggingType.code.asc(),
            )
        ).all()
        years_by_id = dict(
            database_session.execute(select(Year.id, Year.name)).all()
        )
    return jsonify(
        {
            "tagging_types": [
                {
                    "code": tagging_type.code,
                    "name": tagging_type.name,
                    "year": years_by_id[tagging_type.year_id],
                }
                for (tagging_type,) in tagging_type
            ]
        }
    )

@admin_blueprint.post("/admin/tagging-types")
@admin_required
def create_admin_tagging_type():
    """Create a tagging type after validating its code and name."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data jenis tagging tidak valid.")

    name = body.get("name")
    year = body.get("year")
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name.strip()) > 200
        or not _valid_year(year)
    ):
        raise APIError(
            400,
            "Nama dan tahun jenis tagging wajib diisi dengan format yang valid.",
        )

    name = name.strip()
    with get_session() as database_session:
        with database_session.begin():
            year_id = _year_id(database_session, year)
            if year_id is None:
                raise APIError(400, "Tahun belum tersedia.")
            duplicate = database_session.scalar(
                select(TaggingType.code)
                .where(
                    TaggingType.year_id == year_id,
                    func.lower(TaggingType.name) == name.lower(),
                )
                .limit(1)
            )
            if duplicate is not None:
                raise APIError(
                    409,
                    "Nama jenis tagging sudah digunakan pada tahun tersebut.",
                )
            last_id = database_session.scalar(
                text("SELECT seq FROM sqlite_sequence WHERE name='tagging_types'")
            ) or 0
            last_code = database_session.scalar(
                select(func.max(TaggingType.code))
            ) or 0
            next_code = max(last_id, last_code) + 1
            tagging_type = TaggingType(
                code=next_code,
                name=name,
                year_id=year_id,
            )
            database_session.add(tagging_type)
            database_session.flush()
            code = tagging_type.code

    return jsonify({"created": True, "code": code, "name": name, "year": year}), 201

@admin_blueprint.patch("/admin/tagging-types/<int:code>")
@admin_required
def update_admin_tagging_type(code: int):
    """Update a tagging type while preserving its references."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data jenis tagging tidak valid.")

    name = body.get("name")
    year = body.get("year")
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name.strip()) > 200
        or not isinstance(year, int)
        or isinstance(year, bool)
        or not 1900 <= year <= 2200
    ):
        raise APIError(
            400,
            "Nama dan tahun jenis tagging wajib diisi dengan format yang valid.",
        )

    name = name.strip()
    with get_session() as database_session:
        with database_session.begin():
            tagging_type = database_session.scalar(
                select(TaggingType).where(TaggingType.code == code)
            )
            if tagging_type is None:
                raise APIError(404, "Jenis tagging tidak ditemukan.")
            duplicate = database_session.scalar(
                select(TaggingType.code)
                .where(
                    TaggingType.year_id == _year_id(database_session, year),
                    func.lower(TaggingType.name) == name.lower(),
                    TaggingType.code != code,
                )
                .limit(1)
            )
            if duplicate is not None:
                raise APIError(
                    409,
                    "Nama jenis tagging sudah digunakan pada tahun tersebut.",
                )
            year_id = _year_id(database_session, year)
            if year_id is None:
                raise APIError(400, "Tahun belum tersedia.")
            if year_id != tagging_type.year_id:
                is_in_use = database_session.scalar(
                    select(SubactivityTagging.id)
                    .where(SubactivityTagging.tagging_type_id == tagging_type.id)
                    .limit(1)
                )
                if is_in_use is not None:
                    raise APIError(
                        409,
                        "Tahun tidak dapat diubah karena jenis tagging sudah digunakan.",
                    )

            tagging_type.name = name
            tagging_type.year_id = year_id
            result = {
                "updated": True,
                "code": tagging_type.code,
                "name": tagging_type.name,
                "year": year,
            }
    return jsonify(result)

@admin_blueprint.delete("/admin/tagging-types/<int:code>")
@admin_required
def delete_admin_tagging_type(code: int):
    """Delete a tagging type when it is no longer referenced."""
    with get_session() as database_session:
        with database_session.begin():
            tagging_type = database_session.scalar(
                select(TaggingType).where(TaggingType.code == code)
            )
            if tagging_type is None:
                raise APIError(404, "Jenis tagging tidak ditemukan.")
            database_session.execute(
                delete(SubactivityTagging).where(
                    SubactivityTagging.tagging_type_id == tagging_type.id,
                    SubactivityTagging.year_id == tagging_type.year_id,
                )
            )
            database_session.delete(tagging_type)
    return jsonify({"deleted": True, "code": code})

@admin_blueprint.put("/admin/tagging")
@admin_blueprint.put("/admin/tagging-sub-kegiatan")
@admin_required
def update_admin_tagging():
    """Save validated tagging assignments for the selected year."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data tagging tidak valid.")

    year = body.get("year")
    scope = body.get("scope", "sub_kegiatan")
    organizational_unit_id = body.get("sub_unit_id")
    subactivity_id = body.get("sub_kegiatan_id")
    package_id = body.get("paket_kelompok_id")
    tagging_codes = body.get("tagging_codes")
    if (
        not _valid_year(year)
        or scope not in {"sub_kegiatan", "paket_kelompok"}
        or not isinstance(organizational_unit_id, int)
        or isinstance(organizational_unit_id, bool)
        or not isinstance(subactivity_id, int)
        or isinstance(subactivity_id, bool)
        or (
            scope == "paket_kelompok"
            and (
                not isinstance(package_id, int)
                or isinstance(package_id, bool)
            )
        )
        or not isinstance(tagging_codes, list)
        or any(
            not isinstance(code, str) or not code.isdecimal()
            for code in tagging_codes
        )
        or len(tagging_codes) > 100
    ):
        raise APIError(400, "Data tagging tidak valid.")

    tagging_codes = list(dict.fromkeys(int(code) for code in tagging_codes))
    with get_session() as database_session:
        with database_session.begin():
            year_id = _year_id(database_session, year)
            availability_filters = [
                BudgetDetail.year_id == year_id,
                BudgetDetail.organizational_unit_id == organizational_unit_id,
                BudgetDetail.subactivity_id == subactivity_id,
            ]
            if scope == "paket_kelompok":
                availability_filters.append(
                    BudgetDetail.package_group_id == package_id
                )
            available_subactivity = database_session.scalar(
                select(BudgetDetail.id)
                .where(*availability_filters)
                .limit(1)
            )
            if available_subactivity is None:
                raise APIError(404, "Data tagging tidak tersedia pada tahun tersebut.")

            if tagging_codes:
                available_codes = set(
                    database_session.scalars(
                        select(TaggingType.code).where(
                            TaggingType.year_id == year_id,
                            TaggingType.code.in_(tagging_codes),
                        )
                    ).all()
                )
                if available_codes != set(tagging_codes):
                    raise APIError(400, "Terdapat jenis tagging yang tidak tersedia.")

            database_session.execute(
                delete(SubactivityTagging).where(
                    SubactivityTagging.year_id == year_id,
                    SubactivityTagging.organizational_unit_id == organizational_unit_id,
                    SubactivityTagging.subactivity_id == subactivity_id,
                    (
                        SubactivityTagging.package_group_id == package_id
                        if scope == "paket_kelompok"
                        else SubactivityTagging.package_group_id.is_(None)
                    ),
                )
            )
            database_session.add_all(
                [
                    SubactivityTagging(
                        year_id=year_id,
                        organizational_unit_id=organizational_unit_id,
                        subactivity_id=subactivity_id,
                        tagging_type_id=database_session.scalar(
                            select(TaggingType.id).where(
                                TaggingType.code == tagging_code,
                                TaggingType.year_id == year_id,
                            )
                        ),
                        package_group_id=(
                            package_id if scope == "paket_kelompok" else None
                        ),
                    )
                    for tagging_code in tagging_codes
                ]
            )

    return jsonify(
        {
            "saved": True,
            "year": year,
            "scope": scope,
            "sub_unit_id": organizational_unit_id,
            "sub_kegiatan_id": subactivity_id,
            "paket_kelompok_id": package_id if scope == "paket_kelompok" else None,
            "tagging_codes": tagging_codes,
        }
    )


@admin_blueprint.get("/admin/catalog/<catalog>")
@admin_required
def get_admin_catalog(catalog: str):
    """List values in a supported reference catalog."""
    model = _catalog_model(catalog)
    year_value = request.args.get("year", "")
    with get_session() as database_session:
        statement = select(model)
        if year_value:
            if not year_value.isdecimal():
                raise APIError(400, "Parameter year harus berupa tahun yang valid.")
            year_id = database_session.scalar(
                select(Year.id).where(Year.name == int(year_value))
            )
            if year_id is None:
                raise APIError(404, f"Tahun {year_value} tidak tersedia.")
            reference_column = {
                "indikator": PerformanceTarget.indicator_id,
                "satuan": PerformanceTarget.unit_id,
            }.get(catalog)
            if reference_column is not None:
                statement = (
                    statement.join(PerformanceTarget, reference_column == model.id)
                    .where(PerformanceTarget.year_id == year_id)
                    .distinct()
                )
        items = database_session.scalars(
            statement.order_by(func.lower(model.name), model.id)
        ).all()
    return jsonify({"items": [{"id": item.id, "name": item.name} for item in items]})


@admin_blueprint.post("/admin/catalog/<catalog>")
@admin_required
def create_admin_catalog_item(catalog: str):
    """Add a validated value to a reference catalog."""
    model = _catalog_model(catalog)
    body = request.get_json(silent=True)
    name = body.get("name") if isinstance(body, dict) else None
    if not _valid_name(name):
        raise APIError(400, "Nama wajib diisi (maksimal 200 karakter).")
    name = name.strip()
    with get_session() as database_session:
        with database_session.begin():
            duplicate = database_session.scalar(
                select(model.id).where(func.lower(model.name) == name.lower()).limit(1)
            )
            if duplicate is not None:
                raise APIError(409, "Nama tersebut sudah tersedia.")
            item = model(name=name)
            database_session.add(item)
            database_session.flush()
            result = {"id": item.id, "name": item.name}
    return jsonify({"created": True, **result}), 201


@admin_blueprint.patch("/admin/catalog/<catalog>/<int:item_id>")
@admin_required
def update_admin_catalog_item(catalog: str, item_id: int):
    """Update a reference value without breaking existing links."""
    model = _catalog_model(catalog)
    body = request.get_json(silent=True)
    name = body.get("name") if isinstance(body, dict) else None
    if not _valid_name(name):
        raise APIError(400, "Nama wajib diisi (maksimal 200 karakter).")
    name = name.strip()
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(model, item_id)
            if item is None:
                raise APIError(404, "Data referensi tidak ditemukan.")
            duplicate = database_session.scalar(
                select(model.id)
                .where(func.lower(model.name) == name.lower(), model.id != item_id)
                .limit(1)
            )
            if duplicate is not None:
                raise APIError(409, "Nama tersebut sudah tersedia.")
            item.name = name
            result = {"id": item.id, "name": item.name}
    return jsonify({"updated": True, **result})


@admin_blueprint.delete("/admin/catalog/<catalog>/<int:item_id>")
@admin_required
def delete_admin_catalog_item(catalog: str, item_id: int):
    """Delete a reference value only when it is unused."""
    model = _catalog_model(catalog)
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(model, item_id)
            if item is None:
                raise APIError(404, "Data referensi tidak ditemukan.")
            if _catalog_item_used(database_session, catalog, item_id):
                raise APIError(409, "Data referensi tidak dapat dihapus karena sudah digunakan.")
            database_session.delete(item)
    return jsonify({"deleted": True, "id": item_id})


@admin_blueprint.get("/admin/perangkat-daerah")
@admin_required
def get_admin_department():
    """Return departments, aliases, and organizational units for management."""
    year_value = request.args.get("year", "")
    if not year_value.isdecimal():
        raise APIError(400, "Parameter year harus berupa tahun yang valid.")
    year = int(year_value)
    with get_session() as database_session:
        year_id = _year_id(database_session, year)
        if year_id is None:
            raise APIError(404, f"Tahun {year} tidak tersedia.")
        department_items = database_session.scalars(
            select(Department).where(Department.year_id == year_id).order_by(Department.code)
        ).all()
        organizational_units = database_session.scalars(
            select(OrganizationalUnit).where(OrganizationalUnit.year_id == year_id).order_by(OrganizationalUnit.code)
        ).all()
        result = {
            "skpd": [
                {
                    "id": item.id,
                    "code": item.code,
                    "name": item.name,
                    "aliases": [
                        {"id": alias.id, "name": alias.name}
                        for alias in item.aliases
                    ],
                }
                for item in department_items
            ],
            "sub_units": [
                {"id": item.id, "code": item.code, "name": item.name}
                for item in organizational_units
            ],
        }
    return jsonify(result)


@admin_blueprint.post("/admin/perangkat-daerah/<resource>")
@admin_required
def create_admin_department_item(resource: str):
    """Create a department or organizational unit."""
    model = _master_model(resource)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data perangkat daerah tidak valid.")
    code = body.get("code")
    name = body.get("name")
    if not isinstance(code, str) or not code.strip() or len(code.strip()) > 100:
        raise APIError(400, "Kode wajib diisi (maksimal 100 karakter).")
    if not _valid_name(name):
        raise APIError(400, "Nama wajib diisi (maksimal 200 karakter).")
    with get_session() as database_session:
        with database_session.begin():
            year_id = _master_year_id(database_session, body.get("year"))
            code = code.strip()
            name = name.strip()
            duplicate = database_session.scalar(
                select(model.id)
                .where(model.year_id == year_id, model.code == code)
                .limit(1)
            )
            if duplicate is not None:
                raise APIError(409, "Kode sudah digunakan pada tahun tersebut.")
            item = model(code=code, name=name, year_id=year_id)
            database_session.add(item)
            database_session.flush()
            result = {"id": item.id, "code": item.code, "name": item.name}
    return jsonify({"created": True, **result}), 201


@admin_blueprint.patch("/admin/perangkat-daerah/<resource>/<int:item_id>")
@admin_required
def update_admin_department_item(resource: str, item_id: int):
    """Update a department or organizational unit."""
    model = _master_model(resource)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data perangkat daerah tidak valid.")
    code = body.get("code")
    name = body.get("name")
    if not isinstance(code, str) or not code.strip() or len(code.strip()) > 100:
        raise APIError(400, "Kode wajib diisi (maksimal 100 karakter).")
    if not _valid_name(name):
        raise APIError(400, "Nama wajib diisi (maksimal 200 karakter).")
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(model, item_id)
            if item is None:
                raise APIError(404, "Data perangkat daerah tidak ditemukan.")
            year_id = _master_year_id(database_session, body.get("year"))
            code = code.strip()
            name = name.strip()
            duplicate = database_session.scalar(
                select(model.id)
                .where(
                    model.year_id == year_id,
                    model.code == code,
                    model.id != item_id,
                )
                .limit(1)
            )
            if duplicate is not None:
                raise APIError(409, "Kode sudah digunakan pada tahun tersebut.")
            if (
                item.year_id != year_id
                and _master_item_used(database_session, resource, item_id)
            ):
                raise APIError(409, "Tahun tidak dapat diubah karena data sudah digunakan.")
            item.code = code
            item.name = name
            item.year_id = year_id
            result = {"id": item.id, "code": item.code, "name": item.name}
    return jsonify({"updated": True, **result})


@admin_blueprint.delete("/admin/perangkat-daerah/<resource>/<int:item_id>")
@admin_required
def delete_admin_department_item(resource: str, item_id: int):
    """Delete a department resource only when it is unused."""
    model = _master_model(resource)
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(model, item_id)
            if item is None:
                raise APIError(404, "Data perangkat daerah tidak ditemukan.")
            if _master_item_used(database_session, resource, item_id):
                raise APIError(409, "Data tidak dapat dihapus karena sudah digunakan.")
            database_session.delete(item)
    return jsonify({"deleted": True, "id": item_id})


@admin_blueprint.post("/admin/skpd/<int:skpd_id>/aliases")
@admin_required
def create_admin_department_alias(department_id: int):
    """Add an alternate name for a department."""
    body = request.get_json(silent=True)
    name = body.get("name") if isinstance(body, dict) else None
    if not _valid_name(name):
        raise APIError(400, "Nama alias wajib diisi (maksimal 200 karakter).")
    name = name.strip()
    with get_session() as database_session:
        with database_session.begin():
            department = database_session.get(Department, department_id)
            if department is None:
                raise APIError(404, "SKPD tidak ditemukan.")
            duplicate = database_session.scalar(
                select(DepartmentAlias.id)
                .where(
                    DepartmentAlias.department_id == department_id,
                    func.lower(DepartmentAlias.name) == name.lower(),
                )
                .limit(1)
            )
            if duplicate is not None:
                raise APIError(409, "Alias sudah tersedia untuk SKPD tersebut.")
            alias = DepartmentAlias(department_id=department_id, name=name)
            database_session.add(alias)
            database_session.flush()
            result = {"id": alias.id, "name": alias.name}
    return jsonify({"created": True, **result}), 201


@admin_blueprint.patch("/admin/skpd-aliases/<int:alias_id>")
@admin_required
def update_admin_department_alias(alias_id: int):
    """Change an alternate department name."""
    body = request.get_json(silent=True)
    name = body.get("name") if isinstance(body, dict) else None
    if not _valid_name(name):
        raise APIError(400, "Nama alias wajib diisi (maksimal 200 karakter).")
    name = name.strip()
    with get_session() as database_session:
        with database_session.begin():
            alias = database_session.get(DepartmentAlias, alias_id)
            if alias is None:
                raise APIError(404, "Alias SKPD tidak ditemukan.")
            duplicate = database_session.scalar(
                select(DepartmentAlias.id)
                .where(
                    DepartmentAlias.department_id == alias.department_id,
                    func.lower(DepartmentAlias.name) == name.lower(),
                    DepartmentAlias.id != alias_id,
                )
                .limit(1)
            )
            if duplicate is not None:
                raise APIError(409, "Alias sudah tersedia untuk SKPD tersebut.")
            alias.name = name
            result = {"id": alias.id, "name": alias.name, "skpd_id": alias.department_id}
    return jsonify({"updated": True, **result})


@admin_blueprint.delete("/admin/skpd-aliases/<int:alias_id>")
@admin_required
def delete_admin_department_alias(alias_id: int):
    """Remove an alternate department name."""
    with get_session() as database_session:
        with database_session.begin():
            alias = database_session.get(DepartmentAlias, alias_id)
            if alias is None:
                raise APIError(404, "Alias SKPD tidak ditemukan.")
            database_session.delete(alias)
    return jsonify({"deleted": True, "id": alias_id})


def _link_category_json(category: LinkCategory) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "description": category.description,
        "parent_id": category.parent_id,
        "custom_alias": category.custom_alias,
        "is_active": category.is_active,
        "created_at": category.created_at.isoformat(sep=" "),
    }


def _directory_link_json(link: DirectoryLink, admin_id: int) -> dict:
    return {
        "id": link.id,
        "category_id": link.category_id,
        "title": link.title,
        "url": link.url,
        "description": link.description,
        "image_url": link.image_url,
        "icon": link.icon,
        "tags": json.loads(link.tags),
        "is_active": link.is_active,
        "created_by": link.created_by,
        "can_edit": link.created_by == admin_id,
        "year": link.year.name if link.year else None,
        "published_at": link.published_at.isoformat(sep=" "),
        "created_at": link.created_at.isoformat(sep=" "),
        "updated_at": link.updated_at.isoformat(sep=" "),
    }


def _valid_external_url(value: object, *, optional: bool = False) -> bool:
    if optional and value in (None, ""):
        return True
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value.strip())
        return (
            parsed.scheme in {"http", "https"}
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        return False


def _category_custom_alias(value: object) -> str:
    if not isinstance(value, str) or not SHORTLINK_ALIAS_PATTERN.fullmatch(value):
        raise APIError(
            400,
            "Alias custom wajib 3–63 karakter: huruf kecil, angka, tanda hubung, atau garis bawah.",
        )
    return value


def _link_tags(value: object) -> list[str] | None:
    if not isinstance(value, list) or len(value) > 12:
        return None
    tags = []
    for tag in value:
        if not isinstance(tag, str) or not tag.strip() or len(tag.strip()) > 30:
            return None
        if tag.strip() not in tags:
            tags.append(tag.strip())
    return tags


@admin_blueprint.get("/admin/link-categories")
@admin_required
def get_admin_link_categories():
    with get_session() as database_session:
        categories = database_session.scalars(
            select(LinkCategory).order_by(LinkCategory.created_at.desc(), LinkCategory.id.desc())
        ).all()
    return jsonify({"categories": [_link_category_json(item) for item in categories]})


@admin_blueprint.post("/admin/link-categories")
@admin_required
def create_admin_link_category():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not _valid_name(body.get("name")):
        raise APIError(400, "Nama topik wajib diisi (maksimal 200 karakter).")
    description = body.get("description", "")
    parent_id = body.get("parent_id")
    custom_alias = _category_custom_alias(body.get("custom_alias"))
    if not isinstance(description, str) or len(description) > 1000:
        raise APIError(400, "Deskripsi topik maksimal 1000 karakter.")
    if parent_id is not None and (
        not isinstance(parent_id, int) or isinstance(parent_id, bool) or parent_id <= 0
    ):
        raise APIError(400, "Topik utama tidak valid.")
    with get_session() as database_session:
        with database_session.begin():
            parent = database_session.get(LinkCategory, parent_id) if parent_id else None
            if parent_id and (parent is None or parent.parent_id is not None):
                raise APIError(400, "Topik rincian harus berada di bawah topik utama.")
            duplicate = database_session.scalar(
                select(LinkCategory.id).where(
                    LinkCategory.parent_id == parent_id,
                    func.lower(LinkCategory.name) == body["name"].strip().lower(),
                )
            )
            if duplicate is not None:
                raise APIError(409, "Nama topik tersebut sudah tersedia.")
            duplicate_alias = database_session.scalar(
                select(LinkCategory.id).where(
                    func.lower(LinkCategory.custom_alias) == custom_alias.lower()
                )
            )
            if duplicate_alias is not None:
                raise APIError(409, "Alias custom tersebut sudah digunakan.")
            item = LinkCategory(
                name=body["name"].strip(),
                description=description.strip(),
                parent_id=parent_id,
                custom_alias=custom_alias,
            )
            database_session.add(item)
            try:
                database_session.flush()
            except IntegrityError as error:
                raise APIError(
                    409, "Nama topik atau alias custom sudah digunakan."
                ) from error
            result = _link_category_json(item)
    return jsonify({"created": True, "category": result}), 201


@admin_blueprint.patch("/admin/link-categories/<int:category_id>")
@admin_required
def update_admin_link_category(category_id: int):
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not _valid_name(body.get("name")):
        raise APIError(400, "Nama topik wajib diisi (maksimal 200 karakter).")
    if "custom_alias" not in body:
        raise APIError(400, "Alias custom wajib diisi.")
    description = body.get("description", "")
    parent_id = body.get("parent_id")
    custom_alias = _category_custom_alias(body.get("custom_alias"))
    if not isinstance(description, str) or len(description) > 1000:
        raise APIError(400, "Deskripsi topik maksimal 1000 karakter.")
    if parent_id is not None and (
        not isinstance(parent_id, int) or isinstance(parent_id, bool) or parent_id <= 0
    ):
        raise APIError(400, "Topik utama tidak valid.")
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(LinkCategory, category_id)
            if item is None:
                raise APIError(404, "Topik tidak ditemukan.")
            parent = database_session.get(LinkCategory, parent_id) if parent_id else None
            children_exist = database_session.scalar(
                select(LinkCategory.id).where(LinkCategory.parent_id == category_id).limit(1)
            )
            if parent_id == category_id or (
                parent_id and (parent is None or parent.parent_id is not None)
            ) or (children_exist is not None and parent_id is not None):
                raise APIError(400, "Hierarki topik hanya mendukung dua tingkat.")
            if item.parent_id is not None and parent_id is None:
                has_links = database_session.scalar(
                    select(DirectoryLink.id)
                    .where(DirectoryLink.category_id == category_id)
                    .limit(1)
                )
                if has_links is not None:
                    raise APIError(
                        409,
                        "Topik rincian yang memiliki tautan tidak dapat dijadikan topik utama.",
                    )
            duplicate = database_session.scalar(
                select(LinkCategory.id).where(
                    LinkCategory.parent_id == parent_id,
                    func.lower(LinkCategory.name) == body["name"].strip().lower(),
                    LinkCategory.id != category_id,
                )
            )
            if duplicate is not None:
                raise APIError(409, "Nama topik tersebut sudah tersedia.")
            duplicate_alias = database_session.scalar(
                select(LinkCategory.id).where(
                    func.lower(LinkCategory.custom_alias) == custom_alias.lower(),
                    LinkCategory.id != category_id,
                )
            )
            if duplicate_alias is not None:
                raise APIError(409, "Alias custom tersebut sudah digunakan.")
            item.name = body["name"].strip()
            item.description = description.strip()
            item.parent_id = parent_id
            item.custom_alias = custom_alias
            try:
                database_session.flush()
            except IntegrityError as error:
                raise APIError(
                    409, "Nama topik atau alias custom sudah digunakan."
                ) from error
            result = _link_category_json(item)
    return jsonify({"updated": True, "category": result})


@admin_blueprint.patch("/admin/link-categories/<int:category_id>/status")
@admin_required
def update_admin_link_category_status(category_id: int):
    body = request.get_json(silent=True)
    is_active = body.get("is_active") if isinstance(body, dict) else None
    if not isinstance(is_active, bool):
        raise APIError(400, "Status topik harus aktif atau nonaktif.")
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(LinkCategory, category_id)
            if item is None:
                raise APIError(404, "Topik tidak ditemukan.")
            item.is_active = is_active
    return jsonify({"updated": True, "id": category_id, "is_active": is_active})


@admin_blueprint.delete("/admin/link-categories/<int:category_id>")
@admin_required
def delete_admin_link_category(category_id: int):
    body = request.get_json(silent=True)
    confirm_contents = isinstance(body, dict) and body.get("confirm_contents") is True
    with get_session() as database_session:
        with database_session.begin():
            # Keep the ownership check and all deletes in one SQLite write transaction.
            database_session.execute(text("BEGIN IMMEDIATE"))
            item = database_session.get(LinkCategory, category_id)
            if item is None:
                raise APIError(404, "Topik tidak ditemukan.")
            category_ids = select(LinkCategory.id).where(
                or_(LinkCategory.id == category_id, LinkCategory.parent_id == category_id)
            )
            has_children = database_session.scalar(
                select(LinkCategory.id).where(LinkCategory.parent_id == category_id).limit(1)
            )
            has_links = database_session.scalar(
                select(DirectoryLink.id).where(DirectoryLink.category_id.in_(category_ids)).limit(1)
            )
            if (has_children is not None or has_links is not None) and not confirm_contents:
                raise APIError(409, "Konfirmasi diperlukan untuk menghapus topik beserta isinya.")
            other_admin_link = database_session.scalar(
                select(DirectoryLink.id).where(
                    DirectoryLink.category_id.in_(category_ids),
                    DirectoryLink.created_by != web_session["admin_user_id"],
                ).limit(1)
            )
            if other_admin_link is not None:
                raise APIError(403, "Topik tidak dapat dihapus karena berisi tautan milik admin lain.")
            database_session.execute(
                delete(DirectoryLink).where(DirectoryLink.category_id.in_(category_ids))
            )
            database_session.execute(
                delete(LinkCategory).where(LinkCategory.parent_id == category_id)
            )
            database_session.delete(item)
    return jsonify({"deleted": True, "id": category_id})


@admin_blueprint.get("/admin/links")
@admin_required
def get_admin_links():
    admin_id = web_session["admin_user_id"]
    with get_session() as database_session:
        links = database_session.scalars(
            select(DirectoryLink)
            .options(selectinload(DirectoryLink.year))
            .order_by(DirectoryLink.published_at.desc(), DirectoryLink.id.desc())
        ).all()
        result = [_directory_link_json(item, admin_id) for item in links]
    return jsonify({"links": result})


@admin_blueprint.post("/admin/links")
@admin_required
def create_admin_link():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data tautan tidak valid.")
    title = body.get("title")
    description = body.get("description", "")
    category_id = body.get("category_id")
    year_value = body.get("year")
    image_url = body.get("image_url")
    icon = body.get("icon")
    tags = _link_tags(body.get("tags", []))
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        raise APIError(400, "Judul tautan wajib diisi (maksimal 200 karakter).")
    if not _valid_external_url(body.get("url")):
        raise APIError(400, "URL tautan harus menggunakan HTTP atau HTTPS.")
    if not isinstance(description, str) or len(description) > 1000:
        raise APIError(400, "Deskripsi tautan maksimal 1000 karakter.")
    if not _valid_external_url(image_url, optional=True):
        raise APIError(400, "URL gambar harus menggunakan HTTP atau HTTPS.")
    if icon is not None and (not isinstance(icon, str) or len(icon.strip()) > 40):
        raise APIError(400, "Ikon maksimal 40 karakter.")
    if not isinstance(category_id, int) or isinstance(category_id, bool) or tags is None:
        raise APIError(400, "Kategori atau tag tautan tidak valid.")
    if not isinstance(year_value, int) or isinstance(year_value, bool):
        raise APIError(400, "Tahun tautan tidak valid.")
    with get_session() as database_session:
        with database_session.begin():
            category = database_session.get(LinkCategory, category_id)
            if category is None or category.parent_id is None:
                raise APIError(400, "Tautan harus dimasukkan ke topik rincian.")
            year = database_session.scalar(
                select(Year).where(Year.name == year_value)
            )
            if year is None:
                raise APIError(400, "Tahun tautan tidak tersedia.")
            item = DirectoryLink(
                category_id=category_id,
                year_id=year.id,
                title=title.strip(),
                url=body["url"].strip(),
                description=description.strip(),
                image_url=image_url.strip() if image_url else None,
                icon=icon.strip() if icon else None,
                tags=json.dumps(tags, ensure_ascii=False),
                created_by=web_session["admin_user_id"],
                is_active=False,
            )
            database_session.add(item)
            database_session.flush()
            result = _directory_link_json(item, web_session["admin_user_id"])
    return jsonify({"created": True, "link": result}), 201


@admin_blueprint.patch("/admin/links/<int:link_id>")
@admin_required
def update_admin_link(link_id: int):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise APIError(400, "Data tautan tidak valid.")
    admin_id = web_session["admin_user_id"]
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(DirectoryLink, link_id)
            if item is None:
                raise APIError(404, "Tautan tidak ditemukan.")
            if item.created_by != admin_id:
                raise APIError(403, "Hanya pembuat tautan yang dapat mengubah rinciannya.")
            title = body.get("title", item.title)
            url = body.get("url", item.url)
            description = body.get("description", item.description)
            image_url = body.get("image_url", item.image_url)
            icon = body.get("icon", item.icon)
            category_id = body.get("category_id", item.category_id)
            tags = _link_tags(body.get("tags", json.loads(item.tags)))
            if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
                raise APIError(400, "Judul tautan wajib diisi (maksimal 200 karakter).")
            if not _valid_external_url(url) or not _valid_external_url(image_url, optional=True):
                raise APIError(400, "URL tautan dan gambar harus menggunakan HTTP atau HTTPS.")
            if icon is not None and (not isinstance(icon, str) or len(icon.strip()) > 40):
                raise APIError(400, "Ikon maksimal 40 karakter.")
            if not isinstance(description, str) or len(description) > 1000:
                raise APIError(400, "Deskripsi tautan maksimal 1000 karakter.")
            if not isinstance(category_id, int) or isinstance(category_id, bool) or tags is None:
                raise APIError(400, "Kategori atau tag tautan tidak valid.")
            year = item.year
            if "year" in body:
                year_value = body["year"]
                if not isinstance(year_value, int) or isinstance(year_value, bool):
                    raise APIError(400, "Tahun tautan tidak valid.")
                year = database_session.scalar(
                    select(Year).where(Year.name == year_value)
                )
                if year is None:
                    raise APIError(400, "Tahun tautan tidak tersedia.")
            category = database_session.get(LinkCategory, category_id)
            if category is None or category.parent_id is None:
                raise APIError(400, "Tautan harus dimasukkan ke topik rincian.")
            item.title = title.strip()
            item.url = url.strip()
            item.description = description.strip()
            item.image_url = image_url.strip() if image_url else None
            item.icon = icon.strip() if icon else None
            item.category_id = category_id
            item.tags = json.dumps(tags, ensure_ascii=False)
            item.year = year
            item.updated_at = datetime.now()
            item.published_at = item.updated_at
            result = _directory_link_json(item, admin_id)
    return jsonify({"updated": True, "link": result})


@admin_blueprint.patch("/admin/links/<int:link_id>/status")
@admin_required
def update_admin_link_status(link_id: int):
    body = request.get_json(silent=True)
    is_active = body.get("is_active") if isinstance(body, dict) else None
    if not isinstance(is_active, bool):
        raise APIError(400, "Status tautan harus aktif atau nonaktif.")
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(DirectoryLink, link_id)
            if item is None:
                raise APIError(404, "Tautan tidak ditemukan.")
            item.is_active = is_active
            item.updated_at = datetime.now()
            if is_active:
                item.published_at = item.updated_at
            result = {"id": item.id, "is_active": item.is_active}
    return jsonify({"updated": True, **result})


@admin_blueprint.delete("/admin/links/<int:link_id>")
@admin_required
def delete_admin_link(link_id: int):
    admin_id = web_session["admin_user_id"]
    with get_session() as database_session:
        with database_session.begin():
            item = database_session.get(DirectoryLink, link_id)
            if item is None:
                raise APIError(404, "Tautan tidak ditemukan.")
            if item.created_by != admin_id:
                raise APIError(403, "Hanya pembuat tautan yang dapat menghapusnya.")
            database_session.delete(item)
    return jsonify({"deleted": True, "id": link_id})
