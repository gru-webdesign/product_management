"""Sve tabele aplikacije.

Pravila:
- ključevi su UUID stringovi (IdMixin), da uvoz/izvoz i komentari sa linka uvek pogode pravi red;
- novac se čuva kao ceo broj u najmanjoj jedinici (para / cent) u poljima *_minor, nikad kao float;
- trošak i prihod pamte i iznos u osnovnoj valuti (amount_base_minor) po kursu na dan unosa.
"""

from __future__ import annotations

import datetime as dt
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime, utcnow


def _enum(cls: type[StrEnum]) -> Enum:
    # Čuva se kao tekst sa CHECK ograničenjem — čitljivo u bazi i lako za migracije.
    return Enum(
        cls,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda e: [m.value for m in e],
        name=cls.__name__.lower(),
    )


# --- Enumi ---------------------------------------------------------------------------------------


class ProjectStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    # Redosled = redosled kolona u Kanbanu.
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    BLOCKED = "blocked"
    ON_HOLD = "on_hold"
    DONE = "done"


class RiskKind(StrEnum):
    RISK = "risk"
    ISSUE = "issue"
    ASSUMPTION = "assumption"
    DEPENDENCY = "dependency"


class RiskStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ACCEPTED = "accepted"
    CLOSED = "closed"


class DocStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    OBSOLETE = "obsolete"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class DependencyType(StrEnum):
    FINISH_TO_START = "FS"
    START_TO_START = "SS"
    FINISH_TO_FINISH = "FF"


# --- Podešavanja ---------------------------------------------------------------------------------


class Setting(Base):
    """Ključ/vrednost podešavanja (ime korisnika, osnovna valuta, tema, jezik, satnica...)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


# --- Projekti i zadaci ---------------------------------------------------------------------------


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    client: Mapped[str] = mapped_column(String(200), default="")  # partner / klijent
    project_type: Mapped[str] = mapped_column(String(80), default="")
    sponsor: Mapped[str] = mapped_column(String(120), default="")  # sponzor / naručilac
    department: Mapped[str] = mapped_column(String(120), default="")  # odeljenje / tim
    manager: Mapped[str] = mapped_column(String(120), default="")  # vođa projekta
    color: Mapped[str] = mapped_column(String(9), default="#2F55D4")
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date)
    status: Mapped[ProjectStatus] = mapped_column(
        _enum(ProjectStatus), default=ProjectStatus.ACTIVE
    )
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    tasks: Mapped[list[Task]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    milestones: Mapped[list[Milestone]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    budgets: Mapped[list[Budget]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    costs: Mapped[list[CostEntry]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    incomes: Mapped[list[IncomeEntry]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    share_links: Mapped[list[ShareLink]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    risks: Mapped[list[Risk]] = relationship(cascade="all, delete-orphan", passive_deletes=True)
    stakeholders: Mapped[list[Stakeholder]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    documents: Mapped[list[ProjectDocument]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    decisions: Mapped[list[Decision]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


task_tags = Table(
    "task_tags",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Task(IdMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        CheckConstraint(
            "start_date IS NULL OR due_date IS NULL OR start_date <= due_date", name="dates_order"
        ),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus), default=TaskStatus.TODO)
    priority: Mapped[Priority] = mapped_column(_enum(Priority), default=Priority.MEDIUM)
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    due_date: Mapped[dt.date | None] = mapped_column(Date)
    estimate_hours: Mapped[float | None] = mapped_column(Float)
    actual_hours: Mapped[float | None] = mapped_column(Float)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    planned_cost_minor: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    work_type: Mapped[str] = mapped_column(String(80), default="")  # analiza, dokumentacija...
    phase: Mapped[str] = mapped_column(String(80), default="")  # inicijacija, planiranje...
    owner: Mapped[str] = mapped_column(String(120), default="")  # nosilac: osoba ili tim

    project: Mapped[Project] = relationship(back_populates="tasks")
    parent: Mapped[Task | None] = relationship(back_populates="subtasks", remote_side="Task.id")
    subtasks: Mapped[list[Task]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", passive_deletes=True
    )
    notes: Mapped[list[Note]] = relationship(
        back_populates="task", cascade="all, delete-orphan", passive_deletes=True
    )
    tags: Mapped[list[Tag]] = relationship(secondary=task_tags, back_populates="tasks")
    time_entries: Mapped[list[TimeEntry]] = relationship(
        back_populates="task", cascade="all, delete-orphan", passive_deletes=True
    )
    predecessors: Mapped[list[TaskDependency]] = relationship(
        foreign_keys="TaskDependency.successor_id",
        back_populates="successor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    successors: Mapped[list[TaskDependency]] = relationship(
        foreign_keys="TaskDependency.predecessor_id",
        back_populates="predecessor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TaskDependency(IdMixin, TimestampMixin, Base):
    """Zavisnost: successor ne može da počne/završi dok predecessor ne počne/završi (po tipu)."""

    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("predecessor_id", "successor_id", name="pair"),
        CheckConstraint("predecessor_id <> successor_id", name="not_self"),
    )

    predecessor_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    successor_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[DependencyType] = mapped_column(
        _enum(DependencyType), default=DependencyType.FINISH_TO_START
    )
    lag_days: Mapped[int] = mapped_column(Integer, default=0)

    predecessor: Mapped[Task] = relationship(
        foreign_keys=[predecessor_id], back_populates="successors"
    )
    successor: Mapped[Task] = relationship(
        foreign_keys=[successor_id], back_populates="predecessors"
    )


class Milestone(IdMixin, TimestampMixin, Base):
    __tablename__ = "milestones"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    date: Mapped[dt.date] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped[Project] = relationship(back_populates="milestones")


class Note(IdMixin, TimestampMixin, Base):
    __tablename__ = "notes"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(Text)

    task: Mapped[Task] = relationship(back_populates="notes")


class Tag(IdMixin, TimestampMixin, Base):
    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(60), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#8B8D98")

    tasks: Mapped[list[Task]] = relationship(secondary=task_tags, back_populates="tags")


class TimeEntry(IdMixin, TimestampMixin, Base):
    """Utrošeno vreme (u v1.0 unosi se ručno; tajmer u v1.1)."""

    __tablename__ = "time_entries"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    date: Mapped[dt.date] = mapped_column(Date)
    hours: Mapped[float] = mapped_column(Float)
    hourly_rate_minor: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")

    task: Mapped[Task] = relationship(back_populates="time_entries")


# --- Budžet --------------------------------------------------------------------------------------


class BudgetCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "budget_categories"

    name: Mapped[str] = mapped_column(String(100), unique=True)
    color: Mapped[str] = mapped_column(String(9), default="#8B8D98")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Budget(IdMixin, TimestampMixin, Base):
    """Planirani iznos za jednu kategoriju u jednom projektu (uvek u osnovnoj valuti)."""

    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("project_id", "category_id", name="project_category"),)

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[str] = mapped_column(
        ForeignKey("budget_categories.id", ondelete="RESTRICT"), index=True
    )
    planned_minor: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="budgets")
    category: Mapped[BudgetCategory] = relationship()


class _MoneyEntry:
    """Zajednička polja za trošak i prihod."""

    date: Mapped[dt.date] = mapped_column(Date)
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="RSD")
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"))
    amount_base_minor: Mapped[int] = mapped_column(Integer)


class CostEntry(IdMixin, TimestampMixin, _MoneyEntry, Base):
    __tablename__ = "cost_entries"
    __table_args__ = (CheckConstraint("amount_minor >= 0", name="amount_positive"),)

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    category_id: Mapped[str] = mapped_column(
        ForeignKey("budget_categories.id", ondelete="RESTRICT"), index=True
    )
    vendor: Mapped[str] = mapped_column(String(200), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    receipt_path: Mapped[str] = mapped_column(String(500), default="")

    project: Mapped[Project] = relationship(back_populates="costs")
    task: Mapped[Task | None] = relationship()
    category: Mapped[BudgetCategory] = relationship()


class IncomeEntry(IdMixin, TimestampMixin, _MoneyEntry, Base):
    __tablename__ = "income_entries"
    __table_args__ = (CheckConstraint("amount_minor >= 0", name="amount_positive"),)

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    description: Mapped[str] = mapped_column(Text, default="")

    project: Mapped[Project] = relationship(back_populates="incomes")


# --- Deljenje linkom -----------------------------------------------------------------------------


class ShareLink(IdMixin, TimestampMixin, Base):
    __tablename__ = "share_links"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True)
    url: Mapped[str] = mapped_column(String(500), default="")
    pin_hash: Mapped[str] = mapped_column(String(200), default="")
    show_budget: Mapped[bool] = mapped_column(Boolean, default=False)
    show_gantt: Mapped[bool] = mapped_column(Boolean, default=True)
    show_list: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_update: Mapped[bool] = mapped_column(Boolean, default=False)
    last_published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped[Project] = relationship(back_populates="share_links")
    comments: Mapped[list[RemoteComment]] = relationship(
        back_populates="share", cascade="all, delete-orphan", passive_deletes=True
    )


class RemoteComment(IdMixin, TimestampMixin, Base):
    """Komentar koji je gledalac ostavio na linku; preuzima se sa Cloudflare-a."""

    __tablename__ = "remote_comments"

    share_id: Mapped[str] = mapped_column(
        ForeignKey("share_links.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    remote_id: Mapped[str] = mapped_column(String(64), unique=True)
    author_name: Mapped[str] = mapped_column(String(120), default="")
    text: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime] = mapped_column(UTCDateTime())
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    share: Mapped[ShareLink] = relationship(back_populates="comments")
    task: Mapped[Task | None] = relationship()


# --- Istorija izmena -----------------------------------------------------------------------------


class ActivityLog(IdMixin, Base):
    __tablename__ = "activity_log"

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(20))  # create / update / delete
    field: Mapped[str] = mapped_column(String(60), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")


# --- Šabloni projekata ---------------------------------------------------------------------------


class ProjectTemplate(IdMixin, TimestampMixin, Base):
    """Šablon koji je korisnik sačuvao iz projekta. Ugrađeni šabloni su u kodu (services)."""

    __tablename__ = "project_templates"

    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[str] = mapped_column(Text)  # JSON: zadaci, zavisnosti, milestone-i, budžet


# --- Registar projekta: rizici, zainteresovane strane, dokumenta, odluke --------------------------


class Risk(IdMixin, TimestampMixin, Base):
    """Rizik, problem, pretpostavka ili spoljna zavisnost (RAID registar)."""

    __tablename__ = "risks"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[RiskKind] = mapped_column(_enum(RiskKind), default=RiskKind.RISK)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    probability: Mapped[int] = mapped_column(Integer, default=2)  # 1 niska .. 4 vrlo visoka
    impact: Mapped[int] = mapped_column(Integer, default=2)  # 1 nizak .. 4 kritičan
    status: Mapped[RiskStatus] = mapped_column(_enum(RiskStatus), default=RiskStatus.OPEN)
    owner: Mapped[str] = mapped_column(String(120), default="")
    mitigation: Mapped[str] = mapped_column(Text, default="")
    due_date: Mapped[dt.date | None] = mapped_column(Date)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))

    task: Mapped[Task | None] = relationship()

    @property
    def score(self) -> int:
        return self.probability * self.impact


class Stakeholder(IdMixin, TimestampMixin, Base):
    """Osoba ili tim uključen u projekat, sa ulogom i RACI odgovornošću."""

    __tablename__ = "stakeholders"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    organization: Mapped[str] = mapped_column(String(200), default="")  # interno, partner...
    role: Mapped[str] = mapped_column(String(200), default="")
    raci: Mapped[str] = mapped_column(String(4), default="I")  # R, A, C ili I
    influence: Mapped[int] = mapped_column(Integer, default=2)  # 1 nizak .. 3 visok
    interest: Mapped[int] = mapped_column(Integer, default=2)
    email: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class ProjectDocument(IdMixin, TimestampMixin, Base):
    """Dokument ili link: specifikacija, ugovor, zapisnik... (putanja ili URL, ne sam fajl)."""

    __tablename__ = "project_documents"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(80), default="")
    location: Mapped[str] = mapped_column(String(1000), default="")
    version: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[DocStatus] = mapped_column(_enum(DocStatus), default=DocStatus.DRAFT)
    owner: Mapped[str] = mapped_column(String(120), default="")
    doc_date: Mapped[dt.date | None] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="")
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))

    task: Mapped[Task | None] = relationship()


class Decision(IdMixin, TimestampMixin, Base):
    """Odluka: šta je odlučeno, zašto, ko je odobrio i kada."""

    __tablename__ = "decisions"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    decided_on: Mapped[dt.date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(300))
    decision: Mapped[str] = mapped_column(Text, default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    approved_by: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[DecisionStatus] = mapped_column(
        _enum(DecisionStatus), default=DecisionStatus.APPROVED
    )
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))

    task: Mapped[Task | None] = relationship()
