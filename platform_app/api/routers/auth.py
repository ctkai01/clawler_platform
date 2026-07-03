from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from platform_app.api.deps import get_current_user
from platform_app.api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut
from platform_app.api.security import create_access_token, hash_password, verify_password
from platform_app.db.pool import get_pool

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
def register(body: RegisterRequest) -> TokenResponse:
    """Public self-registration always creates an org_main account tied to
    a brand-new organization — matches the spec's "Tài khoản Chủ ... đăng ký
    tài khoản gắn với một Tổ chức/Thương hiệu cụ thể". system_admin and
    org_sub accounts are never created here (admin: seeded manually;
    org_sub: created by org_main via a members endpoint, not auth)."""
    with get_pool().connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = %s", (body.email,)).fetchone()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được đăng ký")

        org = conn.execute(
            "INSERT INTO organizations (name, tier) VALUES (%s, %s) RETURNING id",
            (body.organization_name, body.tier),
        ).fetchone()
        user = conn.execute(
            """
            INSERT INTO users (organization_id, email, password_hash, role)
            VALUES (%s, %s, %s, 'org_main')
            RETURNING id, role
            """,
            (org["id"], body.email, hash_password(body.password)),
        ).fetchone()

    token = create_access_token(user_id=user["id"], role=user["role"])
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    with get_pool().connection() as conn:
        user = conn.execute(
            "SELECT id, role, password_hash, is_active FROM users WHERE email = %s",
            (body.email,),
        ).fetchone()

    if user is None or not user["is_active"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")

    token = create_access_token(user_id=user["id"], role=user["role"])
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)) -> UserOut:
    return UserOut(**user)
