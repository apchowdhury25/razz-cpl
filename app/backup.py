from __future__ import annotations

from app.routers.admin import backup_sqlite


def main() -> None:
    path = backup_sqlite()
    print(f"Backup written to {path}")


if __name__ == "__main__":
    main()
