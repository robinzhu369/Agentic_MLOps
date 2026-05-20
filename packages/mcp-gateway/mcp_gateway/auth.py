"""JWT authentication service."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from jose import JWTError, jwt
from shared_lib.config import MCPGatewaySettings

from .schemas import JWTPayload, TokenResponse


class AuthError(Exception):
    """Authentication error."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# MVP: in-memory user store (replace with DB in production)
_USERS: dict[str, dict[str, str]] = {
    "admin": {"password": "admin123", "role": "admin"},
    "scientist": {"password": "sci123", "role": "scientist"},
}

# In-memory token blacklist (replace with Redis in production)
_REVOKED_JTIS: set[str] = set()


class JWTAuthService:
    """JWT token creation and verification."""

    def __init__(self, settings: MCPGatewaySettings | None = None) -> None:
        if settings is None:
            settings = MCPGatewaySettings()
        self._secret = settings.jwt_secret_key
        self._algorithm = settings.jwt_algorithm
        self._expire_minutes = settings.jwt_expire_minutes

    def create_token_pair(self, user_id: str, role: str) -> TokenResponse:
        """Create access + refresh token pair.

        Args:
            user_id: The user identifier.
            role: User role (admin/scientist).

        Returns:
            TokenResponse with both tokens.
        """
        now = int(datetime.now(tz=UTC).timestamp())
        access_jti = str(uuid.uuid4())
        refresh_jti = str(uuid.uuid4())

        access_payload: dict[str, Any] = {
            "sub": user_id,
            "role": role,
            "exp": now + self._expire_minutes * 60,
            "iat": now,
            "jti": access_jti,
            "type": "access",
        }
        refresh_payload: dict[str, Any] = {
            "sub": user_id,
            "role": role,
            "exp": now + 7 * 24 * 3600,  # 7 days
            "iat": now,
            "jti": refresh_jti,
            "type": "refresh",
        }

        access_token = jwt.encode(
            access_payload, self._secret, algorithm=self._algorithm
        )
        refresh_token = jwt.encode(
            refresh_payload, self._secret, algorithm=self._algorithm
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._expire_minutes * 60,
        )

    def verify_token(self, token: str) -> JWTPayload:
        """Verify and decode a JWT token.

        Args:
            token: The JWT string.

        Returns:
            Decoded JWTPayload.

        Raises:
            AuthError: If token is invalid, expired, or revoked.
        """
        try:
            payload = jwt.decode(
                token, self._secret, algorithms=[self._algorithm]
            )
        except JWTError as e:
            raise AuthError(f"Invalid token: {e}") from e

        jti = payload.get("jti", "")
        if jti in _REVOKED_JTIS:
            raise AuthError("Token has been revoked")

        return JWTPayload(
            sub=payload["sub"],
            role=payload["role"],
            exp=payload["exp"],
            iat=payload["iat"],
            jti=jti,
        )

    def refresh_token(self, refresh_token_str: str) -> TokenResponse:
        """Issue new access token from refresh token.

        Args:
            refresh_token_str: The refresh JWT string.

        Returns:
            New TokenResponse.

        Raises:
            AuthError: If refresh token is invalid.
        """
        try:
            payload = jwt.decode(
                refresh_token_str, self._secret, algorithms=[self._algorithm]
            )
        except JWTError as e:
            raise AuthError(f"Invalid refresh token: {e}") from e

        if payload.get("type") != "refresh":
            raise AuthError("Not a refresh token")

        # Revoke old refresh token
        old_jti = payload.get("jti", "")
        if old_jti:
            _REVOKED_JTIS.add(old_jti)

        return self.create_token_pair(payload["sub"], payload["role"])

    def revoke_token(self, jti: str) -> None:
        """Revoke a token by its JTI.

        Args:
            jti: The unique token identifier.
        """
        _REVOKED_JTIS.add(jti)

    def authenticate_user(self, username: str, password: str) -> TokenResponse:
        """Authenticate user and return token pair.

        Args:
            username: The username.
            password: The password.

        Returns:
            TokenResponse on success.

        Raises:
            AuthError: If credentials are invalid.
        """
        user = _USERS.get(username)
        if user is None or user["password"] != password:
            raise AuthError("Invalid credentials")
        return self.create_token_pair(username, user["role"])
