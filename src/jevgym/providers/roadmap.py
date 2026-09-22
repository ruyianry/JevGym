"""Roadmap provider stubs — one small adapter each, in the agreed order.

Each stub carries the *exact* integration contract discovered during research, so filling it
in is mechanical. They raise ``NotImplementedError`` (with guidance) if invoked, so the CLI
can list them and fail clearly rather than silently. Order of implementation:
NanoJev (DONE — see providers/nanojev.py) -> SemIf -> Decider(native) / Laya / Nimble /
AlexWortega.

Note: Von, Decider(server), and razorback16/OpenJev are already supported *today* via
``JevWireProvider`` (identical `/v1/systemone` wire) — they are not stubs.
"""

from __future__ import annotations

from ..models import DecisionResult


class _RoadmapStub:
    kind = "roadmap"

    def __init__(self, name: str, model_id: str, contract: str):
        self.name = name
        self.model_id = model_id
        self.contract = contract

    def decide(self, state: str, question: str, candidates: list[str]) -> DecisionResult:
        raise NotImplementedError(
            f"Provider '{self.name}' is a roadmap stub and not implemented yet.\n"
            f"Integration contract:\n{self.contract}"
        )


def semif() -> _RoadmapStub:
    return _RoadmapStub(
        "semif",
        "semif-qwen3.5-4b",
        "Python lib / JSONL CLI (formerly OpenJev). Input {id,state,question,options:[{id,"
        "description}]} -> native option logits->probabilities. Backends CUDA/MLX/llama.cpp. "
        "Adapter can shell out to `semif-score` or import the package in-process.",
    )


def decider_native() -> _RoadmapStub:
    return _RoadmapStub(
        "decider_native",
        "Mapika/decider-2b",
        "Python: d = Decider('Mapika/decider-2b'); d.system_one(state, questions) where "
        "questions is the Jev-shaped dict. Returns answers[qid]['probabilities']. (Decider "
        "also has a `/v1/systemone` server usable via JevWireProvider under the name "
        "'decider'.)",
    )


def laya() -> _RoadmapStub:
    return _RoadmapStub(
        "laya",
        "convaiinnovations/laya",
        "Python: Router(preload=True).predict(state, questions) with Jev-shaped questions -> "
        "answers[qid] with choice/score/noul + distribution. Auto language routing.",
    )


def nimble() -> _RoadmapStub:
    return _RoadmapStub(
        "nimble",
        "bespokelabs/Bespoke-Nimble-9B",
        "Python: NimbleModel().score(context, schema) where schema uses enum/boolean types. "
        "Map YES/NO -> enum choices; read per-choice probability. Modal serving available.",
    )


def alexwortega() -> _RoadmapStub:
    return _RoadmapStub(
        "alexwortega",
        "AlexWortega/openjev",
        "NLI cross-encoder (entailment/contradiction/neutral) — a DIFFERENT primitive. "
        "Adapter must phrase each candidate as a hypothesis vs. the state premise and map "
        "entailment probability to the candidate's probability, then normalize.",
    )


ROADMAP_FACTORIES = {
    "semif": semif,
    "decider_native": decider_native,
    "laya": laya,
    "nimble": nimble,
    "alexwortega": alexwortega,
}
