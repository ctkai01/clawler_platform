from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from platform_app.api.deps import get_current_user, require_roles
from platform_app.api.schemas import SubAccountCreate, SubAccountOut, SubAccountUpdate
from platform_app.api.security import hash_password
from platform_app.db.pool import get_pool

# Only org_main manages sub-accounts — matches the spec's "Đặc quyền: Tạo
# các tài khoản con ... và phân quyền cho họ" (org_main exclusive).
router = APIRouter(prefix="/org/users", tags=["members"], dependencies=[Depends(require_roles("org_main"))])


def _row_to_out(conn, user_row: dict) -> dict:
    targets = conn.execute(
        "SELECT target_id FROM user_target_access WHERE user_id = %s", (user_row["id"],)
    ).fetchall()
    return {**user_row, "target_ids": [t["target_id"] for t in targets]}


def _validate_target_ids(conn, organization_id: int, target_ids: list[int]) -> None:
    """A sub-account can only be granted access to targets that belong to
    its own organization — otherwise org_main could accidentally (or
    maliciously) leak another org's crawl sources into user_target_access."""
    if not target_ids:
        return
    rows = conn.execute(
        "SELECT id FROM crawl_targets WHERE id = ANY(%s) AND organization_id = %s",
        (target_ids, organization_id),
    ).fetchall()
    valid_ids = {r["id"] for r in rows}
    invalid = set(target_ids) - valid_ids
    if invalid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Nguồn crawl không hợp lệ: {sorted(invalid)}")


@router.get("", response_model=list[SubAccountOut])
def list_members(user: dict = Depends(get_current_user)) -> list[dict]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.email, u.is_active, up.functional_role
            FROM users u
            JOIN user_permissions up ON up.user_id = u.id
            WHERE u.organization_id = %s AND u.role = 'org_sub'
            ORDER BY u.created_at DESC
            """,
            (user["organization_id"],),
        ).fetchall()
        return [_row_to_out(conn, r) for r in rows]


@router.post("", response_model=SubAccountOut, status_code=status.HTTP_201_CREATED)
def create_member(body: SubAccountCreate, user: dict = Depends(get_current_user)) -> dict:
    with get_pool().connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = %s", (body.email,)).fetchone()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được đăng ký")

        _validate_target_ids(conn, user["organization_id"], body.target_ids)

        new_user = conn.execute(
            """
            INSERT INTO users (organization_id, parent_user_id, email, password_hash, role)
            VALUES (%s, %s, %s, %s, 'org_sub')
            RETURNING id, email, is_active
            """,
            (user["organization_id"], user["id"], body.email, hash_password(body.password)),
        ).fetchone()

        conn.execute(
            "INSERT INTO user_permissions (user_id, functional_role) VALUES (%s, %s)",
            (new_user["id"], body.functional_role),
        )
        for target_id in body.target_ids:
            conn.execute(
                "INSERT INTO user_target_access (user_id, target_id, granted_by) VALUES (%s, %s, %s)",
                (new_user["id"], target_id, user["id"]),
            )

        return {**new_user, "functional_role": body.functional_role, "target_ids": body.target_ids}


@router.patch("/{member_id}", response_model=SubAccountOut)
def update_member(member_id: int, body: SubAccountUpdate, user: dict = Depends(get_current_user)) -> dict:
    with get_pool().connection() as conn:
        member = conn.execute(
            "SELECT id FROM users WHERE id = %s AND organization_id = %s AND role = 'org_sub'",
            (member_id, user["organization_id"]),
        ).fetchone()
        if member is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tài khoản con")

        if body.is_active is not None:
            conn.execute("UPDATE users SET is_active = %s WHERE id = %s", (body.is_active, member_id))
        if body.functional_role is not None:
            conn.execute(
                "UPDATE user_permissions SET functional_role = %s WHERE user_id = %s",
                (body.functional_role, member_id),
            )
        if body.target_ids is not None:
            _validate_target_ids(conn, user["organization_id"], body.target_ids)
            conn.execute("DELETE FROM user_target_access WHERE user_id = %s", (member_id,))
            for target_id in body.target_ids:
                conn.execute(
                    "INSERT INTO user_target_access (user_id, target_id, granted_by) VALUES (%s, %s, %s)",
                    (member_id, target_id, user["id"]),
                )

        row = conn.execute(
            """
            SELECT u.id, u.email, u.is_active, up.functional_role
            FROM users u JOIN user_permissions up ON up.user_id = u.id
            WHERE u.id = %s
            """,
            (member_id,),
        ).fetchone()
        return _row_to_out(conn, row)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: int, user: dict = Depends(get_current_user)) -> None:
    with get_pool().connection() as conn:
        result = conn.execute(
            "DELETE FROM users WHERE id = %s AND organization_id = %s AND role = 'org_sub' RETURNING id",
            (member_id, user["organization_id"]),
        ).fetchone()
        if result is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy tài khoản con")
