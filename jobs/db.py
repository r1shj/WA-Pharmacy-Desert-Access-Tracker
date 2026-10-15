"""
One place that decides which database to connect to. No credentials
live in code - in order of precedence:

  1. DATABASE_URL (a full postgres:// URL - what Render is configured with)
  2. libpq's standard PG* variables (PGHOST, PGUSER, PGPASSWORD, ...) -
     what the GitHub Actions workflow sets, so a password containing
     URL-special characters never needs escaping
  3. The local development database
"""
import os

import psycopg2
import psycopg2.extras


def connect(dict_cursor=False):
    kwargs = {"cursor_factory": psycopg2.extras.RealDictCursor} if dict_cursor else {}
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url, **kwargs)
    if os.environ.get("PGHOST"):
        return psycopg2.connect("", **kwargs)
    return psycopg2.connect(dbname="pharmacy_tracker", **kwargs)
