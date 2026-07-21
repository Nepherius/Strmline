"""Persist TorBox traffic and resolver protection settings.

Revision ID: 20260721_0022
Revises: 20260718_0021
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0022"
down_revision: str | None = "20260718_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "application_settings",
        sa.Column("torbox_requests_per_minute", sa.Integer(), server_default="250", nullable=False),
    )
    op.add_column(
        "application_settings",
        sa.Column(
            "resolver_negative_cache_seconds",
            sa.Integer(),
            server_default="30",
            nullable=False,
        ),
    )
    op.add_column(
        "application_settings",
        sa.Column(
            "resolver_circuit_breaker_failures",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
    )
    op.add_column(
        "application_settings",
        sa.Column(
            "resolver_circuit_breaker_window_seconds",
            sa.Integer(),
            server_default="120",
            nullable=False,
        ),
    )
    op.add_column(
        "application_settings",
        sa.Column(
            "resolver_circuit_breaker_cooldown_seconds",
            sa.Integer(),
            server_default="60",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_application_settings_torbox_requests_per_minute",
        "application_settings",
        "torbox_requests_per_minute BETWEEN 1 AND 1000",
    )
    op.create_check_constraint(
        "ck_application_settings_resolver_negative_cache_seconds",
        "application_settings",
        "resolver_negative_cache_seconds BETWEEN 1 AND 300",
    )
    op.create_check_constraint(
        "ck_application_settings_resolver_circuit_breaker_failures",
        "application_settings",
        "resolver_circuit_breaker_failures BETWEEN 1 AND 20",
    )
    op.create_check_constraint(
        "ck_application_settings_resolver_circuit_breaker_window_seconds",
        "application_settings",
        "resolver_circuit_breaker_window_seconds BETWEEN 1 AND 3600",
    )
    op.create_check_constraint(
        "ck_application_settings_resolver_circuit_breaker_cooldown_seconds",
        "application_settings",
        "resolver_circuit_breaker_cooldown_seconds BETWEEN 1 AND 3600",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_application_settings_resolver_circuit_breaker_cooldown_seconds",
        "application_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_settings_resolver_circuit_breaker_window_seconds",
        "application_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_settings_resolver_circuit_breaker_failures",
        "application_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_settings_resolver_negative_cache_seconds",
        "application_settings",
        type_="check",
    )
    op.drop_constraint(
        "ck_application_settings_torbox_requests_per_minute",
        "application_settings",
        type_="check",
    )
    op.drop_column("application_settings", "resolver_circuit_breaker_cooldown_seconds")
    op.drop_column("application_settings", "resolver_circuit_breaker_window_seconds")
    op.drop_column("application_settings", "resolver_circuit_breaker_failures")
    op.drop_column("application_settings", "resolver_negative_cache_seconds")
    op.drop_column("application_settings", "torbox_requests_per_minute")
