"""create model version, run, and artifact tables

Revision ID: 20260810_0001
Revises:
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260810_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "swmm_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dataset_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_swmm_models"),
        sa.UniqueConstraint("name", name="uq_swmm_models_name"),
    )
    op.create_index("ix_swmm_models_dataset_id", "swmm_models", ["dataset_id"])

    op.create_table(
        "model_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("inp_bucket", sa.String(length=100), nullable=False),
        sa.Column("inp_object_key", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("change_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_model_versions_positive_version"),
        sa.ForeignKeyConstraint(["model_id"], ["swmm_models.id"], name="fk_model_versions_model_id_swmm_models", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_version_id"], ["model_versions.id"], name="fk_model_versions_parent_version_id_model_versions", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_model_versions"),
        sa.UniqueConstraint("inp_object_key", name="uq_model_versions_inp_object_key"),
        sa.UniqueConstraint("model_id", "version", name="uq_model_versions_model_version"),
    )
    op.create_index("ix_model_versions_model_id", "model_versions", ["model_id"])

    op.create_table(
        "model_parameter_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("section", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=200), nullable=False),
        sa.Column("field", sa.String(length=100), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["model_versions.id"], name="fk_model_parameter_changes_version_id_model_versions", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_model_parameter_changes"),
    )
    op.create_index("ix_model_parameter_changes_version_id", "model_parameter_changes", ["version_id"])

    op.create_table(
        "simulation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_simulation_runs_valid_progress"),
        sa.ForeignKeyConstraint(["model_id"], ["swmm_models.id"], name="fk_simulation_runs_model_id_swmm_models", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], name="fk_simulation_runs_model_version_id_model_versions", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_simulation_runs"),
    )
    op.create_index("ix_simulation_runs_model_id", "simulation_runs", ["model_id"])
    op.create_index("ix_simulation_runs_model_version_id", "simulation_runs", ["model_version_id"])
    op.create_index("ix_simulation_runs_status", "simulation_runs", ["status"])

    op.create_table(
        "run_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("bucket", sa.String(length=100), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=150), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["simulation_runs.id"], name="fk_run_artifacts_run_id_simulation_runs", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_run_artifacts"),
        sa.UniqueConstraint("object_key", name="uq_run_artifacts_object_key"),
        sa.UniqueConstraint("run_id", "artifact_type", "object_key", name="uq_run_artifact_object"),
    )
    op.create_index("ix_run_artifacts_artifact_type", "run_artifacts", ["artifact_type"])
    op.create_index("ix_run_artifacts_run_id", "run_artifacts", ["run_id"])


def downgrade() -> None:
    op.drop_table("run_artifacts")
    op.drop_table("simulation_runs")
    op.drop_table("model_parameter_changes")
    op.drop_table("model_versions")
    op.drop_table("swmm_models")
