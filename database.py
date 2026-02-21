from psycopg_pool import ConnectionPool
import os


class Database:
    def __init__(self, connection_pool):
        self.pool = connection_pool

    def create_user(self, username, email, password_hash):
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                    (username, email, password_hash)
                )
                user_id = cur.fetchone()[0]
                conn.commit()
                return user_id

    def get_user_by_username(self, username):
        with self.pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
                return cur.fetchone()
