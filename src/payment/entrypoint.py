import os
import subprocess
import sys

ROLES = ("api", "consumer", "outbox")


def upgrade() -> None:
    completed = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    role = sys.argv[1] if len(sys.argv) > 1 else "api"
    if role not in ROLES:
        raise SystemExit(f"role must be one of: {', '.join(ROLES)}")

    upgrade()

    if role == "api":
        import uvicorn

        reload = os.getenv("UVICORN_RELOAD") == "1"
        uvicorn.run(
            "payment.main:app",
            host="0.0.0.0",
            port=8000,
            reload=reload,
            reload_dirs=["src"] if reload else None,
        )
        return

    if role == "consumer":
        from payment.messaging.consumer import main as run_consumer

        run_consumer()
        return

    from payment.messaging.outbox import main as run_outbox

    run_outbox()


if __name__ == "__main__":
    main()
