"""Shared utilities package.

Modules here are pure helpers with no dependency on either the domain
or the infra layer. They exist so that domain code (e.g.
``core.domain.data_loss_log``) can use path-scrubbing without importing
from ``core.infra.utils_logging`` — that import was a layering
violation (TD-007) because domain must not depend on infra.
"""
