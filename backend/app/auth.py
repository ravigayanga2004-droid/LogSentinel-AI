import smtplib
from datetime import timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common import create_audit_log, require_auth, serialize
from app.config import get_settings
from app.db import get_db, utcnow
from app.models import AuthSession, Member, Notification, RateBucket, ResetToken, User, Workspace
from app.schemas import ForgotInput, LoginInput, PasswordInput, ProfileInput, ResetInput, SetupInput
from app.security import digest, hash_password, is_expired, rate_limit, token, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
DUMMY = hash_password("unusable-dummy-passphrase")


def issue_session(db: Session, user: User, response: Response):
    raw, csrf = token(), token()
    settings = get_settings()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=digest(raw),
            csrf_hash=digest(csrf),
            expires_at=utcnow() + timedelta(hours=settings.session_hours),
        )
    )
    response.set_cookie(
        "ls_session",
        raw,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        "ls_csrf",
        csrf,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_hours * 3600,
        path="/",
    )


def account(db: Session, user: User):
    workspaces = db.execute(
        select(Workspace, Member.role)
        .join(Member, Workspace.id == Member.workspace_id)
        .where(Member.user_id == user.id)
        .order_by(Workspace.name)
    ).all()
    return {
        **serialize(user),
        "workspaces": [{"id": w.id, "name": w.name, "role": role} for w, role in workspaces],
    }


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {
        "setup_required": not bool(db.scalar(select(func.count()).select_from(User))),
        "password_reset_delivery": bool(get_settings().smtp_host),
    }


@router.post("/setup", status_code=201)
def setup(data: SetupInput, request: Request, response: Response, db: Session = Depends(get_db)):
    rate_limit(db, f"setup:{request.client.host if request.client else 'local'}", 5, 3600)
    if db.scalar(select(User.id).limit(1)):
        raise HTTPException(409, "Initial setup has already been completed")
    try:
        with db.begin_nested():
            db.add(
                RateBucket(
                    key="initial-admin-lock", count=1, expires_at=utcnow() + timedelta(days=36500)
                )
            )
            db.flush()
    except IntegrityError:
        raise HTTPException(409, "Initial setup has already been completed") from None
    user = User(
        email=str(data.email).lower(), name=data.name, password_hash=hash_password(data.password)
    )
    workspace = Workspace(name=data.workspace, settings={})
    db.add_all([user, workspace])
    db.flush()
    db.add(Member(workspace_id=workspace.id, user_id=user.id, role="administrator"))
    from app.detection import seed_rules

    seed_rules(db, workspace.id, user.id)
    db.flush()
    issue_session(db, user, response)
    create_audit_log(db, workspace.id, user.id, "workspace.setup", "workspace", workspace.id)
    return account(db, user)


@router.post("/login")
def login(data: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    host = request.client.host if request.client else "local"
    rate_limit(db, f"login-ip:{host}", 30, 900)
    rate_limit(db, f"login-user:{str(data.email).lower()}", 8, 900)
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    valid = verify_password(data.password, user.password_hash if user else DUMMY)
    if not user or not valid or not user.active:
        if user:
            for member in db.scalars(select(Member).where(Member.user_id == user.id)):
                create_audit_log(
                    db, member.workspace_id, user.id, "auth.login_failed", "user", user.id
                )
            db.commit()
        raise HTTPException(401, "Email or password is incorrect")
    user.last_login_at = utcnow()
    issue_session(db, user, response)
    for member in db.scalars(select(Member).where(Member.user_id == user.id)):
        create_audit_log(db, member.workspace_id, user.id, "auth.login", "user", user.id)
    return account(db, user)


@router.get("/me")
def me(user: User = Depends(require_auth), db: Session = Depends(get_db)):
    return account(db, user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    user: User = Depends(require_auth),
    db: Session = Depends(get_db),
):
    db.delete(request.state.session)
    for member in db.scalars(select(Member).where(Member.user_id == user.id)):
        create_audit_log(db, member.workspace_id, user.id, "auth.logout", "user", user.id)
    response.delete_cookie("ls_session")
    response.delete_cookie("ls_csrf")
    return {"ok": True}


def create_reset(db: Session, user: User) -> str:
    db.execute(delete(ResetToken).where(ResetToken.user_id == user.id))
    raw = token()
    db.add(
        ResetToken(
            user_id=user.id, token_hash=digest(raw), expires_at=utcnow() + timedelta(minutes=30)
        )
    )
    return raw


@router.post("/forgot-password")
def forgot(data: ForgotInput, request: Request, db: Session = Depends(get_db)):
    rate_limit(db, f"reset:{request.client.host if request.client else 'local'}", 5, 900)
    settings = get_settings()
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    if user and settings.smtp_host:
        raw = create_reset(db, user)
        message = EmailMessage()
        message["From"], message["To"], message["Subject"] = (
            settings.smtp_from,
            user.email,
            "Reset your LogSentinel password",
        )
        message.set_content(
            f"Use this link within 30 minutes: {settings.public_origin}/reset-password?token={raw}"
        )
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_tls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException):
            db.rollback()
    return {
        "message": "If the account exists and email delivery is configured, a reset link will be sent. Otherwise contact your installation administrator."
    }


@router.post("/reset-password")
def reset(data: ResetInput, db: Session = Depends(get_db)):
    entry = db.scalar(select(ResetToken).where(ResetToken.token_hash == digest(data.token)))
    if not entry or entry.used or is_expired(entry.expires_at):
        raise HTTPException(400, "Reset link is invalid or expired")
    # Atomic consume prevents concurrent token reuse.
    changed = db.scalar(
        update(ResetToken)
        .where(ResetToken.id == entry.id, ResetToken.used.is_(False))
        .values(used=True)
        .returning(ResetToken.id)
    )
    if not changed:
        raise HTTPException(400, "Reset link is invalid or expired")
    user = db.get(User, entry.user_id)
    if not user:
        raise HTTPException(400, "Account is unavailable")
    user.password_hash = hash_password(data.password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    for member in db.scalars(select(Member).where(Member.user_id == user.id)):
        create_audit_log(db, member.workspace_id, user.id, "auth.password_reset", "user", user.id)
    return {"message": "Password changed. Sign in with your new password."}


@router.patch("/profile")
def profile(data: ProfileInput, user: User = Depends(require_auth), db: Session = Depends(get_db)):
    try:
        ZoneInfo(data.timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(422, "Choose a valid IANA timezone") from None
    user.name, user.timezone = data.name, data.timezone
    return serialize(user)


@router.post("/password")
def password(
    data: PasswordInput, user: User = Depends(require_auth), db: Session = Depends(get_db)
):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(data.password)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    for member in db.scalars(select(Member).where(Member.user_id == user.id)):
        create_audit_log(db, member.workspace_id, user.id, "auth.password_changed", "user", user.id)
        db.add(
            Notification(
                workspace_id=member.workspace_id,
                user_id=user.id,
                title="Your password was changed",
                link="/security",
            )
        )
    return {"message": "Password updated. All sessions have been signed out."}
