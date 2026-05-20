"""Kernel Manager — manages Jupyter Kernel lifecycle and code execution."""
from __future__ import annotations

import uuid
from typing import Any


class KernelError(Exception):
    """Error from kernel operations."""


class KernelInfo:
    """Represents a running kernel."""

    def __init__(
        self,
        kernel_id: str,
        kernel_type: str,
        session_id: str | None = None,
    ) -> None:
        self.kernel_id = kernel_id
        self.kernel_type = kernel_type
        self.session_id = session_id
        self.status = "idle"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kernel_id": self.kernel_id,
            "kernel_type": self.kernel_type,
            "session_id": self.session_id,
            "status": self.status,
        }


class KernelManager:
    """Manages Jupyter Kernel lifecycle.

    MVP implementation: uses in-process execution via exec().
    Production: connects to Jupyter Kernel Gateway via jupyter_client.
    """

    def __init__(self) -> None:
        self._kernels: dict[str, KernelInfo] = {}
        self._namespaces: dict[str, dict[str, Any]] = {}
        self._execution_counts: dict[str, int] = {}

    async def create_kernel(
        self,
        kernel_type: str = "python3",
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new kernel.

        Args:
            kernel_type: Type of kernel (python3 or ir).
            session_id: Optional session ID for lifecycle binding.

        Returns:
            Dict with kernel info.

        Raises:
            KernelError: If kernel type is unsupported.
        """
        if kernel_type not in ("python3", "ir"):
            raise KernelError(
                f"Unsupported kernel type: {kernel_type}. "
                f"Supported: python3, ir"
            )

        kernel_id = f"k_{uuid.uuid4().hex[:12]}"
        info = KernelInfo(
            kernel_id=kernel_id,
            kernel_type=kernel_type,
            session_id=session_id,
        )
        self._kernels[kernel_id] = info
        self._namespaces[kernel_id] = {}
        self._execution_counts[kernel_id] = 0

        return info.to_dict()

    async def execute_code(
        self,
        kernel_id: str,
        code: str,
        timeout_s: int = 300,
    ) -> dict[str, Any]:
        """Execute code in a kernel.

        Args:
            kernel_id: Target kernel ID.
            code: Code string to execute.
            timeout_s: Execution timeout in seconds.

        Returns:
            Dict with stdout, stderr, result, execution_count.

        Raises:
            KernelError: If kernel not found or execution fails.
        """
        if kernel_id not in self._kernels:
            raise KernelError(f"Kernel not found: {kernel_id}")

        namespace = self._namespaces[kernel_id]
        self._execution_counts[kernel_id] += 1
        exec_count = self._execution_counts[kernel_id]

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        result_value: str | None = None

        # Capture print output via custom stdout
        import contextlib
        import io

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_capture), \
                 contextlib.redirect_stderr(stderr_capture):
                # Try as expression first (for result display)
                try:
                    result = eval(code, namespace)  # noqa: S307
                    if result is not None:
                        result_value = repr(result)
                except SyntaxError:
                    # Not an expression, execute as statements
                    exec(code, namespace)  # noqa: S102
        except Exception as e:
            stderr_lines.append(f"{type(e).__name__}: {e}")

        stdout_output = stdout_capture.getvalue()
        stderr_output = stderr_capture.getvalue()
        if stderr_output:
            stderr_lines.insert(0, stderr_output)

        return {
            "stdout": stdout_output + "\n".join(stdout_lines),
            "stderr": "\n".join(stderr_lines),
            "result": result_value,
            "execution_count": exec_count,
        }

    async def list_variables(self, kernel_id: str) -> list[dict[str, Any]]:
        """List variables in kernel namespace.

        Args:
            kernel_id: Target kernel ID.

        Returns:
            List of variable info dicts.

        Raises:
            KernelError: If kernel not found.
        """
        if kernel_id not in self._kernels:
            raise KernelError(f"Kernel not found: {kernel_id}")

        namespace = self._namespaces[kernel_id]
        variables: list[dict[str, Any]] = []

        for name, value in namespace.items():
            if name.startswith("_"):
                continue

            var_info: dict[str, Any] = {
                "name": name,
                "type": type(value).__name__,
            }

            # Add shape for numpy/pandas objects
            if hasattr(value, "shape"):
                var_info["shape"] = str(value.shape)
            elif isinstance(value, (list, dict, str)):
                var_info["shape"] = f"({len(value)},)"

            # Preview (truncated repr)
            preview = repr(value)
            if len(preview) > 100:
                preview = preview[:97] + "..."
            var_info["preview"] = preview

            variables.append(var_info)

        return variables

    async def restart_kernel(self, kernel_id: str) -> None:
        """Restart a kernel and clear its namespace.

        Args:
            kernel_id: Target kernel ID.

        Raises:
            KernelError: If kernel not found.
        """
        if kernel_id not in self._kernels:
            raise KernelError(f"Kernel not found: {kernel_id}")

        self._namespaces[kernel_id] = {}
        self._execution_counts[kernel_id] = 0
        self._kernels[kernel_id].status = "idle"

    async def shutdown_kernel(self, kernel_id: str) -> None:
        """Shutdown and remove a kernel.

        Args:
            kernel_id: Target kernel ID.
        """
        self._kernels.pop(kernel_id, None)
        self._namespaces.pop(kernel_id, None)
        self._execution_counts.pop(kernel_id, None)
