"""CLI del agente.

Ejemplos:
  python -m aml.agent.run --input ejemplo.json --dry-run              # revisa con Claude, no envía
  python -m aml.agent.run --input ejemplo.json --offline --dry-run    # sin API key (reglas)
  python -m aml.agent.run --input ejemplo.json --offline              # sin API key y envía a detalert
"""
from __future__ import annotations

import argparse
import json
import sys

from .ingest import send, to_event
from .offline import OfflineClient
from .reviewer import review


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="JSON con transaction_id, transaction y model")
    ap.add_argument("--dry-run", action="store_true", help="No envía a detalert")
    ap.add_argument("--out", help="Guarda el veredicto completo en este archivo")
    ap.add_argument("--offline", action="store_true", help="Sin API key: reglas fijas en vez de Claude")
    a = ap.parse_args(argv)

    payload = json.load(open(a.input, encoding="utf-8"))
    items = payload if isinstance(payload, list) else [payload]
    events = []
    for it in items:
        client = OfflineClient(it["transaction"], it["model"], str(it["transaction_id"])) if a.offline else None
        res = review(it["transaction"], it["model"], str(it["transaction_id"]), client=client)
        if a.offline:
            res["model"] = "offline-rules"
        events.append(to_event(it["transaction"], it["model"], res, str(it["transaction_id"])))
        print(json.dumps(res["verdict"], ensure_ascii=False, indent=2))

    if a.out:
        json.dump([e["context"]["aml"] for e in events], open(a.out, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
    if a.dry_run:
        print("\n--- payload /api/ingest (dry-run) ---")
        print(json.dumps({"events": events}, ensure_ascii=False, indent=2, default=str))
    else:
        print(send(events))
    return 0


if __name__ == "__main__":
    sys.exit(main())