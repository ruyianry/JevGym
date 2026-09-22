"""Arena (sequential trading) types.

v0 implements ONE-SHOT TIMING: stepping through a market's trajectory, the policy may enter
a single 1-contract position (bet YES / bet NO) at some step, or wait; once entered it holds
to resolution. Reward is realized P&L in dollars (pay $1 per in-the-money contract minus the
fill cost). The action space and result types are deliberately shaped to extend to
repeated-bet and full-trading modes without breaking callers.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from .base import JevBaseModel


class ActionType(str, Enum):
    WAIT = "wait"
    BET_YES = "bet_yes"
    BET_NO = "bet_no"


# Candidate labels used when the arena action is posed as a typed decision to a provider.
ACTION_CANDIDATES: list[str] = [ActionType.BET_YES.value, ActionType.BET_NO.value, ActionType.WAIT.value]


class Trade(JevBaseModel):
    step_index: int
    timestamp: datetime
    side: str  # "yes" | "no"
    price: float  # fill price in probability units (the ask for the side bought)
    contracts: float = 1.0


class ArenaResult(JevBaseModel):
    market_ticker: str
    domain: str | None = None
    uncertainty_band: str = "unknown"
    provider: str
    model_id: str

    entered: bool = False
    trade: Trade | None = None  # the first/primary fill (kept for one-shot callers)
    trades: list[Trade] = []  # every fill across the episode (repeated / multi-day modes)
    contracts: float = 0.0  # total contracts bought across the episode

    outcome_y: int | None = None  # realized label
    reward: float = 0.0  # realized P&L in dollars (summed over all fills)
    steps: int = 0  # number of decision steps taken

    model_p: float | None = None  # the model's P(YES) that triggered the (first) trade
    edge: float | None = None  # model_p - ask on the side taken (its "adjustment" vs market)

    mode: str = "edge_one_shot"  # "edge_one_shot" | "action_one_shot" | "repeated" (multi-day)

    @property
    def return_per_contract(self) -> float:
        """Realized P&L normalized by position size — the headline % return / contract."""
        return self.reward / self.contracts if self.contracts else 0.0
