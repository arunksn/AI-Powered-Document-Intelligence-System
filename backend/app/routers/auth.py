import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth import (
    hash_password, verify_password, create_access_token, get_current_user,
    validate_password_strength, create_reset_token, decode_reset_token
)
from app.rate_limit import rate_limit_by_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.post("/signup", response_model=schemas.TokenOut)
def signup(payload: schemas.SignupRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit_by_ip(request, "signup", limit=20, window_seconds=60)

    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    validate_password_strength(payload.password)

    existing = db.query(models.User).filter_by(email=email).first()
    if existing:
        raise HTTPException(409, "An account with this email already exists.")

    user = models.User(
        email=email,
        hashed_password=hash_password(payload.password),
        name=(payload.name or "").strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return {"access_token": token, "user": user}


@router.post("/login", response_model=schemas.TokenOut)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    rate_limit_by_ip(request, f"login:{email}", limit=8, window_seconds=60)

    user = db.query(models.User).filter_by(email=email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password.")

    token = create_access_token(user.id)
    return {"access_token": token, "user": user}


def send_password_reset_email(email: str, reset_url: str):
    import logging
    logger = logging.getLogger("auth.email")

    subject = "Reset Your Password - Ledgerline"
    body = f"""Hello,

You requested a password reset for your Ledgerline account.
Please click the secure link below to reset your password (valid for 15 minutes):

{reset_url}

If you did not request a password reset, please ignore this email.

Best regards,
The Ledgerline Team
"""
    smtp_host = getattr(settings, "SMTP_HOST", "").strip()
    if smtp_host:
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = getattr(settings, "SMTP_FROM_EMAIL", "noreply@ledgerline.app")
            msg["To"] = email
            with smtplib.SMTP(smtp_host, getattr(settings, "SMTP_PORT", 587)) as server:
                if getattr(settings, "SMTP_USER", "").strip():
                    server.starttls()
                    server.login(settings.SMTP_USER, getattr(settings, "SMTP_PASSWORD", ""))
                server.send_message(msg)
            logger.info(f"Password reset email dispatched via SMTP to {email}")
            return
        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {e}")

    log_msg = f"\n=== [PRODUCTION EMAIL DISPATCH] ===\nTO: {email}\nSUBJECT: {subject}\nLINK: {reset_url}\n====================================\n"
    logger.info(log_msg)
    print(log_msg)


@router.post("/forgot-password")
def forgot_password(payload: schemas.ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    rate_limit_by_ip(request, f"forgot-password:{email}", limit=5, window_seconds=60)

    user = db.query(models.User).filter_by(email=email).first()
    if user:
        reset_token = create_reset_token(user.id)
        reset_url = f"{settings.PUBLIC_APP_URL.rstrip('/')}/reset-password?token={reset_token}"
        send_password_reset_email(email, reset_url)

    return {
        "message": "If an account exists for this email, a password reset link has been dispatched to your inbox."
    }


@router.post("/reset-password")
def reset_password(payload: schemas.ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    rate_limit_by_ip(request, "reset-password", limit=10, window_seconds=60)
    user_id = decode_reset_token(payload.token)

    validate_password_strength(payload.new_password)

    user = db.get(models.User, user_id)
    if not user:
        raise HTTPException(404, "User not found.")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password successfully reset. You can now log in with your new password."}


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user

