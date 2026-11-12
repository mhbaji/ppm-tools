"""Define SQLAlchemy models for budget and administrative data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )


class AdminNote(Base):
    __tablename__ = "admin_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Year(Base):
    __tablename__ = "years"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    budget: Mapped[list[BudgetDetail]] = relationship(back_populates="year")
    stages: Mapped[list[Stage]] = relationship(back_populates="year")


class YearMixin:
    year_id: Mapped[int] = mapped_column(
        ForeignKey("years.id"),
        nullable=False,
    )


class MasterMixin(YearMixin):
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Department(MasterMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("code", "year_id"),)

    budget: Mapped[list[BudgetDetail]] = relationship(back_populates="department")
    aliases: Mapped[list[DepartmentAlias]] = relationship(
        back_populates="department",
        cascade="all, delete-orphan",
    )


class DepartmentAlias(Base):
    __tablename__ = "department_aliases"
    __table_args__ = (UniqueConstraint("department_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[Department] = relationship(back_populates="aliases")


class OrganizationalUnit(MasterMixin, Base):
    __tablename__ = "organizational_units"
    __table_args__ = (UniqueConstraint("code", "year_id"),)

    budget: Mapped[list[BudgetDetail]] = relationship(back_populates="organizational_unit")


class Affair(MasterMixin, Base):
    __tablename__ = "affairs"
    __table_args__ = (UniqueConstraint("code", "year_id"),)


class AffairField(MasterMixin, Base):
    __tablename__ = "affair_fields"
    __table_args__ = (UniqueConstraint("code", "year_id"),)


class Program(MasterMixin, Base):
    __tablename__ = "programs"
    __table_args__ = (UniqueConstraint("code", "year_id"),)


class Activity(MasterMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("code", "year_id"),)


class Subactivity(MasterMixin, Base):
    __tablename__ = "subactivities"
    __table_args__ = (UniqueConstraint("code", "year_id"),)

    budget: Mapped[list[BudgetDetail]] = relationship(back_populates="subactivity")
    taggings: Mapped[list[SubactivityTagging]] = relationship(
        back_populates="subactivity"
    )


class FundingSource(MasterMixin, Base):
    __tablename__ = "funding_sources"
    __table_args__ = (UniqueConstraint("code", "year_id"),)


class Account(MasterMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("code", "year_id"),)


class PackageGroup(YearMixin, Base):
    __tablename__ = "package_groups"
    __table_args__ = (UniqueConstraint("name", "year_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    budget: Mapped[list[BudgetDetail]] = relationship(
        back_populates="package_group"
    )
    taggings: Mapped[list[SubactivityTagging]] = relationship(
        back_populates="package_group"
    )


class TaggingType(YearMixin, Base):
    __tablename__ = "tagging_types"
    __table_args__ = (
        UniqueConstraint("code", "year_id"),
        UniqueConstraint("name", "year_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    taggings: Mapped[list[SubactivityTagging]] = relationship(
        back_populates="tagging_type"
    )


class Stage(YearMixin, Base):
    __tablename__ = "stages"
    __table_args__ = (
        UniqueConstraint("code", "year_id"),
        UniqueConstraint("name", "year_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    year: Mapped[Year] = relationship(back_populates="stages")
    budget: Mapped[list[BudgetDetail]] = relationship(back_populates="stage")


class JobLevel(Base):
    __tablename__ = "job_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class Indicator(Base):
    __tablename__ = "indicators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class Unit(Base):
    __tablename__ = "units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class Period(Base):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class SubactivityTagging(YearMixin, Base):
    __tablename__ = "subactivity_taggings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organizational_unit_id: Mapped[int] = mapped_column(ForeignKey("organizational_units.id"), nullable=False)
    subactivity_id: Mapped[int] = mapped_column(
        ForeignKey("subactivities.id"),
        nullable=False,
    )
    tagging_type_id: Mapped[int] = mapped_column(
        ForeignKey("tagging_types.id"),
        nullable=False,
    )
    package_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("package_groups.id")
    )

    organizational_unit: Mapped[OrganizationalUnit] = relationship()
    subactivity: Mapped[Subactivity] = relationship(back_populates="taggings")
    tagging_type: Mapped[TaggingType] = relationship(back_populates="taggings")
    package_group: Mapped[PackageGroup | None] = relationship(
        back_populates="taggings"
    )


class PerformanceTarget(Base):
    __tablename__ = "performance_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organizational_unit_id: Mapped[int] = mapped_column(ForeignKey("organizational_units.id"), nullable=False)
    year_id: Mapped[int] = mapped_column(ForeignKey("years.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    job_level_id: Mapped[int] = mapped_column(
        ForeignKey("job_levels.id"),
        nullable=False,
    )
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicators.id"), nullable=False)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id"), nullable=False)
    target: Mapped[float] = mapped_column(Numeric(20, 4), nullable=False)

    organizational_unit: Mapped[OrganizationalUnit] = relationship()
    year: Mapped[Year] = relationship()
    job_level: Mapped[JobLevel] = relationship()
    indicator: Mapped[Indicator] = relationship()
    unit: Mapped[Unit] = relationship()
    achievement: Mapped[list[PerformanceResult]] = relationship(
        back_populates="performance_target",
        cascade="all, delete-orphan",
    )


class PerformanceResult(Base):
    __tablename__ = "performance_results"
    __table_args__ = (UniqueConstraint("performance_target_id", "period_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    performance_target_id: Mapped[int] = mapped_column(
        ForeignKey("performance_targets.id"),
        nullable=False,
    )
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), nullable=False)
    achievement: Mapped[float | None] = mapped_column(Numeric(20, 4))
    achievement_percentage: Mapped[float | None] = mapped_column(Numeric(12, 4))
    realized_budget: Mapped[float | None] = mapped_column(Numeric(20, 2))

    performance_target: Mapped[PerformanceTarget] = relationship(back_populates="achievement")
    period: Mapped[Period] = relationship()


class LinkCategory(Base):
    __tablename__ = "link_categories"
    __table_args__ = (
        Index(
            "uq_link_categories_root_name",
            text("lower(name)"),
            unique=True,
            sqlite_where=text("parent_id IS NULL"),
        ),
        Index(
            "uq_link_categories_child_name",
            text("parent_id"),
            text("lower(name)"),
            unique=True,
            sqlite_where=text("parent_id IS NOT NULL"),
        ),
        Index(
            "uq_link_categories_custom_alias",
            text("lower(custom_alias)"),
            unique=True,
            sqlite_where=text("custom_alias IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("link_categories.id"))
    custom_alias: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )

    parent: Mapped[LinkCategory | None] = relationship(
        remote_side="LinkCategory.id",
        back_populates="children",
    )
    children: Mapped[list[LinkCategory]] = relationship(back_populates="parent")
    links: Mapped[list[DirectoryLink]] = relationship(back_populates="category")


class DirectoryLink(Base):
    __tablename__ = "directory_links"
    __table_args__ = (
        Index("ix_directory_links_active_category_published", "is_active", "category_id", "published_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year_id: Mapped[int | None] = mapped_column(ForeignKey("years.id"))
    category_id: Mapped[int] = mapped_column(
        ForeignKey("link_categories.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(Text)
    icon: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("admin_users.id"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    category: Mapped[LinkCategory] = relationship(back_populates="links")
    year: Mapped[Year | None] = relationship()
    creator: Mapped[AdminUser] = relationship()


class RequestEvent(Base):
    __tablename__ = "request_events"
    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "route",
            "resolution",
            "bucket_start",
            name="uq_request_events_bucket",
        ),
        Index(
            "ix_request_events_resolution_time_type",
            "resolution",
            "bucket_start",
            "event_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str] = mapped_column(Text, nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class ShortLink(Base):
    __tablename__ = "short_links"
    __table_args__ = (
        Index("uq_short_links_alias", "alias", unique=True),
        Index("ix_short_links_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    target_url: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )


class ShortLinkClick(Base):
    __tablename__ = "short_link_clicks"
    __table_args__ = (
        UniqueConstraint(
            "short_link_id",
            "year",
            name="uq_short_link_clicks_link_year",
        ),
        Index("ix_short_link_clicks_year", "year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_link_id: Mapped[int] = mapped_column(
        ForeignKey("short_links.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    click_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )


class BudgetDetail(YearMixin, Base):
    __tablename__ = "budget_details"
    __table_args__ = (
        Index(
            "ix_budget_details_year_stage_unit_subactivity_package",
            "year_id",
            "stage_id",
            "organizational_unit_id",
            "subactivity_id",
            "package_group_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"), nullable=False)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), nullable=False)
    organizational_unit_id: Mapped[int] = mapped_column(ForeignKey("organizational_units.id"), nullable=False)
    affair_id: Mapped[int] = mapped_column(ForeignKey("affairs.id"), nullable=False)
    affair_field_id: Mapped[int] = mapped_column(
        ForeignKey("affair_fields.id"),
        nullable=False,
    )
    program_id: Mapped[int] = mapped_column(ForeignKey("programs.id"), nullable=False)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id"),
        nullable=False,
    )
    subactivity_id: Mapped[int] = mapped_column(
        ForeignKey("subactivities.id"),
        nullable=False,
    )
    funding_source_id: Mapped[int | None] = mapped_column(ForeignKey("funding_sources.id"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    package_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("package_groups.id")
    )
    budget: Mapped[int | None] = mapped_column(Integer)

    year: Mapped[Year] = relationship(back_populates="budget")
    stage: Mapped[Stage] = relationship(back_populates="budget")
    department: Mapped[Department] = relationship(back_populates="budget")
    organizational_unit: Mapped[OrganizationalUnit] = relationship(back_populates="budget")
    affair: Mapped[Affair] = relationship()
    affair_field: Mapped[AffairField] = relationship()
    program: Mapped[Program] = relationship()
    activity: Mapped[Activity] = relationship()
    subactivity: Mapped[Subactivity] = relationship(back_populates="budget")
    funding_source: Mapped[FundingSource | None] = relationship()
    account: Mapped[Account | None] = relationship()
    package_group: Mapped[PackageGroup | None] = relationship(
        back_populates="budget"
    )


class DatasetInfo(Base):
    __tablename__ = "dataset_info"
    __table_args__ = (UniqueConstraint("year_id", "stage_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    year_id: Mapped[int] = mapped_column(ForeignKey("years.id"), nullable=False)
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class ImportMetadata(Base):
    __tablename__ = "import_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    year_id: Mapped[int] = mapped_column(ForeignKey("years.id"), nullable=False)


class RealizationUpload(Base):
    __tablename__ = "realization_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_filename: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    year_id: Mapped[int] = mapped_column(ForeignKey("years.id"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    imported_rows: Mapped[int] = mapped_column(Integer, nullable=False)

    year: Mapped[Year] = relationship()
    period: Mapped[Period] = relationship()


class AdminUpload(Base):
    __tablename__ = "admin_uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


def full_budget_detail_statement() -> Any:
    from sqlalchemy import select

    return (
        select(
            BudgetDetail,
            Department.name.label("skpd_name"),
            OrganizationalUnit.name.label("sub_unit_name"),
            Affair.name.label("urusan_name"),
            AffairField.name.label("bidang_urusan_name"),
            Program.name.label("program_name"),
            Activity.name.label("kegiatan_name"),
            Subactivity.name.label("sub_kegiatan_name"),
            FundingSource.name.label("sumber_dana_name"),
            Account.name.label("rekening_name"),
            PackageGroup.name.label("paket_kelompok_name"),
        )
        .join(BudgetDetail.department)
        .join(BudgetDetail.organizational_unit)
        .join(BudgetDetail.affair)
        .join(BudgetDetail.affair_field)
        .join(BudgetDetail.program)
        .join(BudgetDetail.activity)
        .join(BudgetDetail.subactivity)
        .outerjoin(BudgetDetail.funding_source)
        .outerjoin(BudgetDetail.account)
        .outerjoin(BudgetDetail.package_group)
    )
