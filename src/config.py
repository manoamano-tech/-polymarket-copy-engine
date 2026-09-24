from pathlib import Path
import os
import yaml
from pydantic import BaseModel

class Leader(BaseModel):
    name: str
    wallet: str
    min_trade_usd: float = 2000
    max_slippage: float = 0.02
    category: str | None = None

def load_leaders(path: str = "config/leaders.yaml") -> list[Leader]:
    raw = yaml.safe_load(Path(path).read_text())
    return [Leader(**item) for item in raw["leaders"]]

def setting(name: str, default: str) -> str:
    return os.getenv(name, default)
