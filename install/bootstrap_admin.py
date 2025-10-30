#!/usr/bin/env python3
import getpass
import os
import sys
from datetime import datetime

import psycopg

# Local imports without package setup
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.config import settings  # noqa: E402
from utils.idgen_ut import gen_id  # noqa: E402
from utils.security_ut import hash_password  # noqa: E402


def main() -> None:
    print("YurTube admin bootstrap")
    email = input("Admin email: ").strip()
    username = input("Admin username: ").strip()
    password = getpass.getpass("Admin password: ").strip()

    if not email or not username or not password:
        print("All fields are required.")
        sys.exit(1)

    user_uid = gen_id(20)
    channel_id = gen_id(24)
    password_hash = hash_password(password)

    with psycopg.connect(settings.DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (user_uid, username, channel_id, email, password_hash, role, created_at)
                VALUES (%s, %s, %s, %s, %s, 'admin', %s)
                """,
                (user_uid, username, channel_id, email, password_hash, datetime.utcnow()),
            )
        conn.commit()

    print("Admin user created.")
    print(f"user_uid={user_uid}")
    print(f"channel_id={channel_id}")


if __name__ == "__main__":
    main()