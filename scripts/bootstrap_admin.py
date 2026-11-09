"""Bootstrap local admin (run once); for institution-wide usage replace with campus SSO."""
from sqlalchemy import select
from database.connection import SessionLocal
from database.config import settings
from database.models import User
from api.auth.security import hash_password

def main():
    cfg = settings()
    if not cfg.admin_bootstrap_email or len(cfg.admin_bootstrap_password) < 12:
        raise ValueError('Set ADMIN_BOOTSTRAP_EMAIL and a strong ADMIN_BOOTSTRAP_PASSWORD (12+ characters)')
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.email == cfg.admin_bootstrap_email))
        if user: print('Admin account already exists; no changes made'); return
        db.add(User(email=cfg.admin_bootstrap_email, password_hash=hash_password(cfg.admin_bootstrap_password), role='admin'))
    print('Admin account created')
if __name__ == '__main__': main()
