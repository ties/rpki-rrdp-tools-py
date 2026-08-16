"""Date-based output paths."""

from datetime import datetime
from enum import StrEnum
from pathlib import Path


class Shard(StrEnum):
    NONE = "none"
    YEAR_MONTH = "year-month"


def resolve_output_dir(base_dir: Path, shard: Shard, now: datetime) -> Path:
    match shard:
        case Shard.NONE:
            return base_dir
        case Shard.YEAR_MONTH:
            return base_dir / f"{now:%Y}" / f"{now:%m}"


def daily_log_file(output_dir: Path, now: datetime) -> Path:
    return output_dir / f"{now:%Y%m%d}.log"
