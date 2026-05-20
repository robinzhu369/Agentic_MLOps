"""Audit logging — structured JSON Lines audit trail for all MCP tool calls."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from .pii import PIIMasker
from .schemas import AuditLogEntry, AuditStatus

logger = structlog.get_logger("mcp_gateway.audit")


class AuditLogger:
    """Non-blocking structured audit logger."""

    def __init__(self, masker: PIIMasker | None = None) -> None:
        self._masker = masker or PIIMasker()

    async def log(self, entry: AuditLogEntry) -> None:
        """Write an audit log entry.

        Non-blocking: failures are logged to system error log
        but never propagate to the caller.

        Args:
            entry: The audit log entry to write.
        """
        try:
            log_data = entry.model_dump(mode="json")
            logger.info("audit", **log_data)
        except Exception as e:
            logger.error("audit_write_failed", error=str(e))

    def create_entry(
        self,
        *,
        trace_id: str,
        user_id: str,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        status: AuditStatus,
        duration_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        dry_run: bool = False,
    ) -> AuditLogEntry:
        """Create an audit log entry with masked arguments.

        Args:
            trace_id: Request trace ID.
            user_id: Authenticated user ID.
            session_id: Agent session ID.
            tool_name: MCP tool name.
            arguments: Raw tool arguments (will be masked).
            status: Call status.
            duration_ms: Execution duration.
            error_code: Error code if failed.
            error_message: Error message if failed.
            dry_run: Whether this was a dry run.

        Returns:
            AuditLogEntry ready to be logged.
        """
        # Mask PII in arguments before logging
        masked_args, _ = self._masker.mask_dict(arguments)

        # Summarize large values
        summary = self._summarize_arguments(tool_name, masked_args)

        return AuditLogEntry(
            audit_id=str(uuid.uuid4()),
            trace_id=trace_id,
            timestamp=datetime.now(tz=UTC),
            user_id=user_id,
            session_id=session_id,
            tool_name=tool_name,
            arguments_summary=summary,
            status=status,
            duration_ms=duration_ms,
            error_code=error_code,
            error_message=error_message,
            dry_run=dry_run,
        )

    def _summarize_arguments(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Summarize arguments for audit (truncate large values).

        Args:
            tool_name: The tool name (for context-specific summarization).
            arguments: The masked arguments dict.

        Returns:
            Summarized dict suitable for logging.
        """
        summary: dict[str, Any] = {}
        for key, value in arguments.items():
            if isinstance(value, str) and len(value) > 200:
                summary[key] = f"<{len(value)} chars>"
            elif isinstance(value, list) and len(value) > 10:
                summary[key] = f"<list of {len(value)} items>"
            else:
                summary[key] = value
        return summary
