from pathlib import Path

from ..core.config import settings


class SQLiteDatabase:
    """SQLite bootstrap scaffold. Real persistence can plug in here later."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @property
    def path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// URLs are supported in this scaffold.")

        raw_path = self.database_url.removeprefix(prefix)
        path = Path(raw_path)
        if not path.is_absolute():
            api_root = Path(__file__).resolve().parents[2]
            path = api_root / raw_path
        return path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)


sqlite_database = SQLiteDatabase(settings.database_url)
