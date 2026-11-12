"""Configure the Flask application, database, and route blueprints."""

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from flask import Flask, g, has_request_context, request
from sqlalchemy import create_engine, delete, event, or_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from .models import AdminNote, AdminUser, Base, BudgetDetail, RequestEvent
from .routes import (
    admin_blueprint,
    pages_blueprint,
    public_blueprint,
    shortlink_redirect_blueprint,
)
from .schema_migration import (
    initialize_database_file,
    migrate_database,
    migrate_english_schema,
    migrate_feature_schema,
    migrate_link_directory_schema,
)


BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
DEFAULT_DATABASE_PATH = PROJECT_DIR / "data" / "ppm_tools.sqlite3"
LEGACY_DATABASE_PATH = (
    PROJECT_DIR / "data" / "Penetapan APBD Pergeseran II 2026.sqlite3"
)


def _request_bucket_start(value: datetime, resolution: str) -> datetime:
    """Round a UTC timestamp down for bounded request-count aggregation."""
    if resolution == "minute":
        return value.replace(second=0, microsecond=0)
    if resolution == "hour":
        return value.replace(minute=0, second=0, microsecond=0)
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        static_folder=None,
    )
    app.config.from_mapping(
        DATABASE_PATH=Path(
            os.environ.get("APBD_DATABASE", DEFAULT_DATABASE_PATH)
        ),
        ADMIN_UPLOAD_DIR=PROJECT_DIR / "data" / "admin_uploads",
        REALIZATION_UPLOAD_DIR=PROJECT_DIR / "data" / "realization_uploads",
        APBD_ENV=os.environ.get("APBD_ENV", "development").strip().lower(),
        SECRET_KEY=os.environ.get("APBD_SECRET_KEY"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("APBD_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
        PERFORMANCE_LOGGING=os.environ.get(
            "APBD_PERFORMANCE_LOGGING", ""
        ).lower()
        in {"1", "true", "yes"},
    )
    if test_config:
        app.config.update(test_config)
    secret_key = app.config["SECRET_KEY"]
    if not secret_key or (isinstance(secret_key, str) and not secret_key.strip()):
        if app.config["APBD_ENV"] == "production":
            raise RuntimeError("APBD_SECRET_KEY wajib diatur pada mode produksi.")
        app.config["SECRET_KEY"] = secrets.token_hex(32)
        app.logger.warning(
            "APBD_SECRET_KEY belum diatur; sesi tidak bertahan setelah aplikasi dimulai ulang."
        )
    if app.config["PERFORMANCE_LOGGING"]:
        app.logger.setLevel("INFO")

    database_path = Path(app.config["DATABASE_PATH"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        "DATABASE_PATH" not in (test_config or {})
        and not os.environ.get("APBD_DATABASE")
    ):
        initialize_database_file(database_path, LEGACY_DATABASE_PATH)
    migrate_database(database_path)
    migrate_feature_schema(database_path)
    migrate_link_directory_schema(database_path)
    migrate_english_schema(database_path)
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    next(
        index
        for index in BudgetDetail.__table__.indexes
        if index.name
        == "ix_budget_details_year_stage_unit_subactivity_package"
    ).create(engine, checkfirst=True)

    @event.listens_for(engine, "before_cursor_execute")
    def start_query_timer(
        _connection,
        _cursor,
        _statement,
        _parameters,
        context,
        _executemany,
    ):
        if (
            app.config["PERFORMANCE_LOGGING"]
            and has_request_context()
            and getattr(g, "_apbd_perf_start", None) is not None
        ):
            context._apbd_query_started_at = perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def finish_query_timer(
        _connection,
        _cursor,
        _statement,
        _parameters,
        context,
        _executemany,
    ):
        started_at = getattr(context, "_apbd_query_started_at", None)
        if started_at is not None and has_request_context():
            g._apbd_db_duration_ms += (perf_counter() - started_at) * 1000
            g._apbd_db_query_count += 1

    @app.before_request
    def start_api_request_timer():
        if (
            app.config["PERFORMANCE_LOGGING"]
            and request.endpoint
            in {
                "public_api.get_years",
                "public_api.get_stage",
                "public_api.get_tagging_summary",
                "public_api.get_public_tagging",
                "public_api.get_budget",
            }
        ):
            g._apbd_perf_start = perf_counter()
            g._apbd_db_duration_ms = 0.0
            g._apbd_db_query_count = 0

    @app.after_request
    def log_api_request_performance(response):
        started_at = getattr(g, "_apbd_perf_start", None)
        if started_at is not None:
            app.logger.info(
                "api_performance endpoint=%s status=%s duration_ms=%.1f "
                "db_execute_duration_ms=%.1f db_query_count=%d "
                "response_bytes=%s",
                request.endpoint,
                response.status_code,
                (perf_counter() - started_at) * 1000,
                g._apbd_db_duration_ms,
                g._apbd_db_query_count,
                response.content_length,
            )
        if (
            request.method == "GET"
            and response.status_code == 200
            and request.endpoint
            in {
                "public_api.get_years",
                "public_api.get_stage",
                "public_api.get_public_tagging_types",
                "public_api.get_tagging_summary",
            }
        ):
            response.headers["Cache-Control"] = "public, max-age=30"
        if request.path.startswith(("/api/auth/", "/api/admin/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.after_request
    def record_public_request(response):
        """Record public page and API requests without storing caller identifiers."""
        endpoint = request.endpoint or ""
        public_pages = {
            "pages.index",
            "pages.public_tagging_page",
            "pages.public_realization_page",
            "pages.public_link_directory_page",
            "pages.public_budget_comparison_page",
            "pages.public_shortlink_page",
        }
        if endpoint in public_pages:
            event_type = "web"
        elif endpoint.startswith("public_api."):
            event_type = "api"
        else:
            return response

        route = request.url_rule.rule if request.url_rule is not None else request.path
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        cleanup_due = False
        try:
            with app.extensions["apbd_session_factory"].begin() as database_session:
                for resolution in ("minute", "hour", "day"):
                    statement = sqlite_insert(RequestEvent).values(
                        event_type=event_type,
                        route=route,
                        resolution=resolution,
                        bucket_start=_request_bucket_start(now, resolution),
                        request_count=1,
                    )
                    database_session.execute(
                        statement.on_conflict_do_update(
                            index_elements=[
                                RequestEvent.event_type,
                                RequestEvent.route,
                                RequestEvent.resolution,
                                RequestEvent.bucket_start,
                            ],
                            set_={
                                "request_count": RequestEvent.request_count + 1,
                            },
                        )
                    )

                last_cleanup = app.extensions["request_event_cleanup_at"]
                if last_cleanup is None or now - last_cleanup >= timedelta(hours=24):
                    database_session.execute(
                        delete(RequestEvent).where(
                            or_(
                                (
                                    RequestEvent.resolution == "minute"
                                )
                                & (
                                    RequestEvent.bucket_start
                                    < now - timedelta(hours=25)
                                ),
                                (
                                    RequestEvent.resolution == "hour"
                                )
                                & (
                                    RequestEvent.bucket_start
                                    < now - timedelta(days=8)
                                ),
                                (
                                    RequestEvent.resolution == "day"
                                )
                                & (
                                    RequestEvent.bucket_start
                                    < now - timedelta(days=366)
                                ),
                            )
                        )
                    )
                    cleanup_due = True
        except SQLAlchemyError:
            app.logger.exception(
                "Tidak dapat mencatat request publik untuk route=%s", route
            )
        else:
            if cleanup_due:
                app.extensions["request_event_cleanup_at"] = now
        return response

    policy_description = (
        "Admin dapat mengelola jenis tagging dan penandaan subkegiatan atau "
        "paket/kelompok. Data APBD dan referensi diperbarui melalui impor Excel."
    )
    with engine.begin() as connection:
        connection.execute(
            AdminNote.__table__.update()
            .where(AdminNote.key == "subkegiatan_tagging")
            .values(description=policy_description)
        )
        connection.execute(
            AdminNote.__table__.insert().prefix_with("OR IGNORE"),
            {
                "key": "subkegiatan_tagging",
                "description": policy_description,
            },
        )

    admin_username = os.environ.get("APBD_ADMIN_USERNAME")
    admin_password = os.environ.get("APBD_ADMIN_PASSWORD")
    if bool(admin_username) != bool(admin_password):
        raise ValueError(
            "APBD_ADMIN_USERNAME dan APBD_ADMIN_PASSWORD harus diatur bersama."
        )
    if admin_username and admin_password:
        with engine.begin() as connection:
            existing_admin = connection.execute(
                AdminUser.__table__.select().where(
                    AdminUser.username == admin_username
                )
            ).first()
            if existing_admin is None:
                connection.execute(
                    AdminUser.__table__.insert(),
                    {
                        "username": admin_username,
                        "password_hash": generate_password_hash(admin_password),
                        "is_active": True,
                    },
                )

    app.extensions["apbd_engine"] = engine
    app.extensions["apbd_session_factory"] = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    app.extensions["request_event_cleanup_at"] = None

    app.register_blueprint(
        pages_blueprint(FRONTEND_DIR),
    )
    app.register_blueprint(public_blueprint)
    app.register_blueprint(admin_blueprint)
    app.register_blueprint(shortlink_redirect_blueprint)
    return app
