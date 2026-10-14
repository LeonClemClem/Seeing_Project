import os
from urllib.parse import quote


def database_url() -> str:
    """SQLAlchemy URL from DATABASE_URL, or from the DB_* variables set on Cloud Run."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    try:
        host = os.environ["DB_HOST"]
        name = os.environ["DB_NAME"]
        user = os.environ["DB_USER"]
        password = os.environ["DB_PASSWORD"]
    except KeyError as exc:
        raise RuntimeError(
            f"Database not configured: set DATABASE_URL or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD ({exc} missing)"
        ) from None
    port = os.environ.get("DB_PORT", "5432")
    return f"postgresql+psycopg://{quote(user)}:{quote(password)}@{host}:{port}/{name}"
