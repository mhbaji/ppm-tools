"""Serve frontend pages and static assets through Flask routes."""

from pathlib import Path

from flask import Blueprint, request, send_from_directory


def pages_blueprint(frontend_dir: Path) -> Blueprint:
    """Register page and static-file routes for the frontend directory."""
    pages_dir = frontend_dir / "pages"
    blueprint = Blueprint(
        "pages",
        __name__,
        static_folder=str(frontend_dir),
        static_url_path="",
    )

    @blueprint.after_request
    def cache_versioned_assets(response):
        """Cache explicitly versioned frontend assets for one year."""
        if (
            request.endpoint == "pages.static"
            and response.status_code == 200
            and request.args.get("v")
            and request.path.startswith(("/js/", "/css/"))
            and request.path.endswith((".js", ".css"))
        ):
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable"
            )
        return response

    @blueprint.get("/")
    def index():
        """Serve the public dashboard page."""
        return send_from_directory(pages_dir, "index.html")

    @blueprint.get("/tagging")
    def public_tagging_page():
        """Serve the public tagging page."""
        return send_from_directory(pages_dir, "tagging.html")

    @blueprint.get("/realisasi")
    def public_realization_page():
        """Serve the public realization and achievement page."""
        return send_from_directory(pages_dir, "public-realization.html")

    @blueprint.get("/tautan")
    def public_link_directory_page():
        """Serve the combined public link directory and shortlink page."""
        return send_from_directory(pages_dir, "link-directory.html")

    @blueprint.get("/t/<alias>")
    @blueprint.get("/tautan/<alias>")
    def public_link_directory_alias_page(alias: str):
        """Serve the public directory page for a current or legacy topic alias."""
        return send_from_directory(pages_dir, "link-directory.html")

    @blueprint.get("/shortlink")
    def public_shortlink_page():
        """Serve the combined public link directory and shortlink page."""
        return send_from_directory(pages_dir, "link-directory.html")

    @blueprint.get("/perbandingan-anggaran")
    def public_budget_comparison_page():
        """Serve the public budget-comparison page."""
        return send_from_directory(pages_dir, "budget-comparison.html")

    @blueprint.get("/login")
    def login_page():
        """Serve the administrator login page."""
        return send_from_directory(pages_dir, "login.html")

    @blueprint.get("/admin")
    def admin_page():
        """Serve the default admin tagging page."""
        return send_from_directory(pages_dir, "subactivity-tagging.html")

    @blueprint.get("/admin/dashboard")
    def admin_dashboard_page():
        """Serve the admin dashboard page."""
        return send_from_directory(pages_dir, "admin-dashboard.html")

    @blueprint.get("/admin/statistics")
    def admin_statistics_page():
        """Serve the web and API statistics page."""
        return send_from_directory(pages_dir, "web-api-statistics.html")

    @blueprint.get("/admin/shortlinks")
    def admin_shortlinks_page():
        """Serve combined link and shortlink management for administrators."""
        return send_from_directory(pages_dir, "shortlinks-admin.html")

    @blueprint.get("/admin/tagging-sub-kegiatan")
    def tagging_subactivity_page():
        """Serve the subactivity-tagging management page."""
        return send_from_directory(pages_dir, "subactivity-tagging.html")

    @blueprint.get("/admin/sub-kegiatan")
    def admin_subactivity_page():
        """Serve the subactivity import and management page."""
        return send_from_directory(pages_dir, "subactivities.html")

    @blueprint.get("/admin/realisasi")
    def admin_realization_page():
        """Serve the realization management page."""
        return send_from_directory(pages_dir, "realization.html")

    @blueprint.get("/admin/tagging-types")
    def admin_tagging_types_page():
        """Serve the tagging-type management page."""
        return send_from_directory(pages_dir, "stages.html")

    @blueprint.get("/admin/tahapan")
    def admin_stage_page():
        """Serve the budget-stage management page."""
        return send_from_directory(pages_dir, "stages.html")

    @blueprint.get("/admin/tautan")
    def admin_link_directory_page():
        """Serve combined link and shortlink management for administrators."""
        return send_from_directory(pages_dir, "shortlinks-admin.html")

    @blueprint.get("/admin/perangkat-daerah")
    def admin_department_page():
        """Serve the department management page."""
        return send_from_directory(pages_dir, "departments.html")

    @blueprint.get("/admin/level-pekerjaan")
    @blueprint.get("/admin/referensi")
    @blueprint.get("/admin/indikator")
    @blueprint.get("/admin/satuan")
    def admin_master_catalog_page():
        """Serve the master-reference catalog management page."""
        return send_from_directory(pages_dir, "master-catalog.html")

    return blueprint
