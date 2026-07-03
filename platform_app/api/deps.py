from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from platform_app.api.security import decode_access_token
from platform_app.db.pool import get_pool

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict:
    """Resolve the JWT into a full user row (+ functional_role, +
    accessible_target_ids for org_sub). Raises 401 on any auth failure —
    callers layer role/permission checks (403) on top of this."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Thiếu access token")
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token không hợp lệ hoặc đã hết hạn") from exc

    user_id = int(payload["sub"])
    with get_pool().connection() as conn:
        user = conn.execute(
            """
            SELECT u.id, u.email, u.role, u.organization_id, u.is_active,
                   o.name AS organization_name,
                   up.functional_role
            FROM users u
            LEFT JOIN organizations o ON o.id = u.organization_id
            LEFT JOIN user_permissions up ON up.user_id = u.id
            WHERE u.id = %s
            """,
            (user_id,),
        ).fetchone()

        if user is None or not user["is_active"]:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tài khoản không tồn tại hoặc đã bị khoá")

        if user["role"] == "org_sub":
            rows = conn.execute(
                "SELECT target_id FROM user_target_access WHERE user_id = %s", (user_id,)
            ).fetchall()
            user["accessible_target_ids"] = [r["target_id"] for r in rows]
        else:
            user["accessible_target_ids"] = None

    return user


def require_roles(*roles: str):
    """Dependency factory: 403s unless the caller's role is in `roles`."""

    def _check(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền truy cập")
        return user

    return _check
