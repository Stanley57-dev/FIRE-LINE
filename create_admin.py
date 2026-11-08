import os
import getpass
import psycopg
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise SystemExit("DATABASE_URL is missing from your .env file.")

username = input("Admin username: ").strip()
password = getpass.getpass(
    "Admin password (minimum 10 characters): "
)

if not username:
    raise SystemExit("Username is required.")

if len(password) < 10:
    raise SystemExit("Password must contain at least 10 characters.")

try:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (username, password_hash, role)
                VALUES (%s, %s, 'admin')
            """, (
                username,
                generate_password_hash(password)
            ))

    print("Administrator account created successfully.")

except psycopg.errors.UniqueViolation:
    print("This username already exists.")

except Exception as error:
    print("Unable to create administrator account.")
    print(error)