import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")

    # The operational data is spread across four databases on the same server.
    # See docs/database.md for what lives in each.
    db_operational: str = os.getenv("MONGODB_DB_OPERATIONAL", "winicari")
    db_tickets_archive: str = os.getenv("MONGODB_DB_TICKETS_ARCHIVE", "Historique_Tickets")
    db_pos_archive: str = os.getenv("MONGODB_DB_POS_ARCHIVE", "Historique_pos")
    db_opendata: str = os.getenv("MONGODB_DB_OPENDATA", "OpenData")

    data_raw_dir: str = os.getenv("DATA_RAW_DIR", "./data/raw")
    data_processed_dir: str = os.getenv("DATA_PROCESSED_DIR", "./data/processed")
    data_features_dir: str = os.getenv("DATA_FEATURES_DIR", "./data/features")

    @property
    def all_databases(self) -> list[str]:
        return [self.db_operational, self.db_tickets_archive, self.db_pos_archive, self.db_opendata]


settings = Settings()
