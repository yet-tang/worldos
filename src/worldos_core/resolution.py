from __future__ import annotations

import hashlib


class DeterministicResolver:
    """Produces reproducible pseudo-random values from explicit simulation inputs."""

    def __init__(self, world_seed: str | int) -> None:
        self.world_seed = str(world_seed)

    def roll(self, *, intent_id: str, channel: str, low: int = 1, high: int = 100) -> int:
        if low > high:
            raise ValueError("low cannot exceed high")
        material = f"{self.world_seed}:{intent_id}:{channel}".encode()
        value = int(hashlib.sha256(material).hexdigest(), 16)
        return low + value % (high - low + 1)
