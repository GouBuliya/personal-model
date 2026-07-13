"""Live formation eval on the frozen golden fixture (spec §3, persome-domain proxy).

Runs the real memory_delta formation over the frozen fixture with a live LLM,
scores precision / recall / calendar / polarity against the gold labels, and
compares completeness-reread OFF vs ON. This is the "one live pass on the
fixture" the spec designed the fixture for — it informs the B1 default without
the full OmniMemEval integration (the harder-signal round).

Usage (needs a configured LLM in <PERSOME_ROOT>/env):
    set -a; source ~/.persome/env; set +a
    uv run python scripts/eval_formation_fixture.py [draws]
"""

from __future__ import annotations

import sys
import tempfile
from unittest.mock import patch

from persome import config as config_mod
from persome.store import fts
from persome.writer import memory_delta as md
from tests.fixtures import formation_golden as gold


def _all_texts(clean: dict) -> list[str]:
    out: list[str] = []
    for a in clean.get("assertions", []):
        out.append(str(a.get("text", "")))
    for e in clean.get("events", []):
        out.append(str(e.get("title", "")))
    return out


def _score(clean: dict) -> dict:
    texts = _all_texts(clean)
    hay = " || ".join(texts)
    present = [g for g in gold.gold_items() if g.present]
    absent = [g for g in gold.gold_items() if not g.present]

    def hit(g) -> bool:
        return any(all(s in t for s in g.must_contain) for t in texts)

    recalled = sum(hit(g) for g in present)
    leaked = sum(hit(g) for g in absent)
    calendar_items = [g for g in present if g.calendar]
    cal_ok = sum(g.calendar in hay for g in calendar_items)
    pol_items = [g for g in present if g.polarity in ("+", "-")]
    pol_ok = 0
    for g in pol_items:
        for a in clean.get("assertions", []):
            if all(s in str(a.get("text", "")) for s in g.must_contain):
                if a.get("polarity") == g.polarity:
                    pol_ok += 1
                break
    return {
        "recall": recalled / max(1, len(present)),
        "precision": 1.0 - leaked / max(1, len(present)),  # leaks penalize precision
        "leaked": leaked,
        "calendar": cal_ok / max(1, len(calendar_items)) if calendar_items else 1.0,
        "polarity": pol_ok / max(1, len(pol_items)) if pol_items else 1.0,
        "n_memories": len(texts),
    }


def _run(reread: bool) -> dict:
    import os
    import shutil
    from pathlib import Path

    # Temp DATA root (writes never touch the real DB) but carry the real LLM
    # profile + key so formation runs against the configured provider.
    root = tempfile.mkdtemp()
    src = Path.home() / ".persome"
    for name in ("config.toml", "env"):
        if (src / name).exists():
            shutil.copy(src / name, Path(root) / name)
    os.environ["PERSOME_ROOT"] = root
    cfg = config_mod.load()
    cfg.memory_delta.enabled = True
    cfg.memory_delta.completeness_reread = reread
    cfg.memory_delta.apply_enabled = False
    captured: dict = {}

    real_gate = md.gate_delta

    def spy_gate(*a, **k):
        clean, dropped = real_gate(*a, **k)
        captured["clean"] = clean
        return clean, dropped

    with (
        patch.object(md.tl_store, "query_range", return_value=gold.golden_blocks()),
        patch.object(md, "gate_delta", spy_gate),
        fts.cursor(),
    ):
        md.run_after_session(
            cfg,
            session_id="fixture-eval",
            start_time=gold.SESSION_DATE,
            end_time=gold.SESSION_DATE,
        )
    return _score(captured.get("clean", {h: [] for h in md._HEADS}))


def main() -> None:
    draws = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    for label, reread in (("B1 OFF (pass-1 only)", False), ("B1 ON (completeness re-read)", True)):
        agg: dict[str, float] = {}
        for _ in range(draws):
            s = _run(reread)
            for k, v in s.items():
                agg[k] = agg.get(k, 0.0) + v
        mean = {k: round(v / draws, 3) for k, v in agg.items()}
        print(f"{label}: {mean}")


if __name__ == "__main__":
    main()
