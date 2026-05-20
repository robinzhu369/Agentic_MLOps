"""RBAC — Role-Based Access Control for MCP tools."""
from __future__ import annotations

from .schemas import Role, ToolPermission


class PermissionDeniedError(Exception):
    """Raised when user lacks required role for a tool."""

    def __init__(self, tool_name: str, required_role: Role, user_role: Role) -> None:
        self.tool_name = tool_name
        self.required_role = required_role
        self.user_role = user_role
        super().__init__(
            f"Role '{user_role.value}' cannot access '{tool_name}' "
            f"(requires '{required_role.value}')"
        )


# Role hierarchy: admin > scientist
_ROLE_LEVEL: dict[Role, int] = {
    Role.SCIENTIST: 1,
    Role.ADMIN: 2,
}


class RBACService:
    """Role-based access control for MCP tool calls."""

    def __init__(
        self, tool_permissions: list[ToolPermission] | None = None
    ) -> None:
        self._permissions: dict[str, Role] = {}
        if tool_permissions:
            for perm in tool_permissions:
                self._permissions[perm.tool_name] = perm.required_role

    def check_permission(self, tool_name: str, user_role: str) -> None:
        """Check if user role can access the tool.

        Args:
            tool_name: The MCP tool name (e.g., "jupyter.execute_code").
            user_role: The user's role string.

        Raises:
            PermissionDeniedError: If user lacks required role.
        """
        try:
            role = Role(user_role)
        except ValueError:
            role = Role.SCIENTIST

        required = self._permissions.get(tool_name, Role.SCIENTIST)
        user_level = _ROLE_LEVEL.get(role, 0)
        required_level = _ROLE_LEVEL.get(required, 0)

        if user_level < required_level:
            raise PermissionDeniedError(tool_name, required, role)

    def set_permission(self, tool_name: str, required_role: Role) -> None:
        """Set or update permission for a tool.

        Args:
            tool_name: The MCP tool name.
            required_role: Minimum role required.
        """
        self._permissions[tool_name] = required_role

    def get_accessible_tools(
        self, user_role: str, all_tools: list[str]
    ) -> list[str]:
        """Filter tools list to those accessible by user role.

        Args:
            user_role: The user's role string.
            all_tools: List of all available tool names.

        Returns:
            Filtered list of accessible tool names.
        """
        accessible = []
        for tool in all_tools:
            try:
                self.check_permission(tool, user_role)
                accessible.append(tool)
            except PermissionDeniedError:
                continue
        return accessible
