"""User-Agent rotation — round-robin with shuffle for entropy."""

from __future__ import annotations

import random
from pathlib import Path
from loguru import logger


class UserAgentRotator:
    """Load and cycle through realistic browser User-Agent strings."""

    def __init__(self, path: str = "data/user_agents.txt") -> None:
        self.agents = self._load(path)
        self._idx = 0

    def _load(self, path: str) -> list[str]:
        p = Path(path)
        if not p.exists():
            logger.warning(f"UA file {path} not found — using fallback UA")
            return ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]
        lines = [l.strip() for l in p.read_text().splitlines()
                 if l.strip() and not l.startswith("#")]
        if not lines:
            logger.warning(f"UA file {path} is empty — using fallback UA")
            return ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]
        return lines

    def next(self) -> str:
        """Round-robin UA with occasional random shuffle for entropy."""
        ua = self.agents[self._idx % len(self.agents)]
        self._idx += 1
        if self._idx % len(self.agents) == 0:
            random.shuffle(self.agents)
        return ua

    def random(self) -> str:
        """Return a random UA."""
        return random.choice(self.agents)

    @property
    def count(self) -> int:
        return len(self.agents)
