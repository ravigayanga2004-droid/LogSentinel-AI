import argparse

from sqlalchemy import select


def main():
    parser = argparse.ArgumentParser(description="LogSentinel local administration")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    sub.add_parser("worker")
    reset = sub.add_parser("reset-link", help="Create an expiring recovery link for a verified local account")
    reset.add_argument("email")
    member = sub.add_parser("grant-member", help="Grant membership after verifying identity out of band")
    member.add_argument("email")
    member.add_argument("workspace_id")
    member.add_argument("role", choices=["administrator", "analyst", "viewer", "source_admin"])
    args = parser.parse_args()
    if args.command == "seed":
        from app.seed import seed
        print(seed())
    elif args.command == "worker":
        from app.worker import main as work
        work()
    else:
        from app.auth import create_reset
        from app.common import create_audit_log
        from app.config import get_settings
        from app.db import SessionLocal
        from app.models import Member, User, Workspace
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == args.email.lower()))
            if not user:
                parser.error("Account not found")
            if args.command == "reset-link":
                raw = create_reset(db, user)
                db.commit()
                print(f"{get_settings().public_origin}/reset-password?token={raw}")
            else:
                workspace = db.get(Workspace, args.workspace_id)
                if not workspace:
                    parser.error("Workspace not found")
                existing = db.get(Member, (workspace.id, user.id))
                if existing:
                    parser.error("Membership already exists; change its role in the application")
                db.add(Member(workspace_id=workspace.id, user_id=user.id, role=args.role))
                create_audit_log(db, workspace.id, None, "member.cli_granted", "user", user.id, {"role": args.role})
                db.commit()
                print("Membership granted.")


if __name__ == "__main__":
    main()
