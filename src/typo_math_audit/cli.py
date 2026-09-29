import argparse
import sys
from .common import ASSETS, canonical, digest, read_json, utcnow, write_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Auditable paired CPU arithmetic typo experiment")
    commands = parser.add_subparsers(dest="command", required=True)
    acquire = commands.add_parser("acquire", help="Download revision-pinned public model files and verify SHA-256")
    acquire.add_argument("--model-dir", required=True)
    verify_model = commands.add_parser("verify-model")
    verify_model.add_argument("--model-dir", required=True)
    for name in ("pilot", "run"):
        p = commands.add_parser(name)
        p.add_argument("--model-dir", required=True)
        p.add_argument("--out", required=True)
        p.add_argument("--limit", type=int, help="Checkpoint after this many new records; exit 2 until complete")
        if name == "run":
            p.add_argument("--split", choices=["dev", "eval"], default="eval")
    p = commands.add_parser("freeze", help="Freeze once, only after a completed development pilot")
    p.add_argument("--pilot", required=True)
    for name in ("audit", "report"):
        p = commands.add_parser(name)
        p.add_argument("--run", required=True)
        p.add_argument("--allow-partial", action="store_true")
    p = commands.add_parser("compare", help="Compare deterministic scientific fields, excluding timings")
    p.add_argument("reference")
    p.add_argument("replay")
    args = parser.parse_args(argv)
    try:
        if args.command in ("acquire", "verify-model"):
            from .model import acquire, verify_model
            result = acquire(args.model_dir) if args.command == "acquire" else verify_model(args.model_dir)
            print(f"Verified {len(result['files'])} files at {result['revision']}")
        elif args.command in ("run", "pilot"):
            from .runner import run
            return run(args.out, args.model_dir, split="dev" if args.command == "pilot" else args.split,
                       pilot=args.command == "pilot", limit=args.limit)
        elif args.command == "freeze":
            from pathlib import Path
            from .audit import audit_run
            from .protocol import specification
            if (ASSETS / "protocol.json").exists():
                raise ValueError("Protocol already frozen; use a new version for a new experiment")
            result = audit_run(args.pilot)
            config = read_json(Path(args.pilot) / "run.json")
            spec = specification()
            if not config["pilot"] or config["split"] != "dev" or config["specification"] != spec:
                raise ValueError("Freeze requires a completed pilot with current settings and code")
            write_json(ASSETS / "protocol.json", dict(frozen_utc=utcnow(), specification=spec,
                       specification_sha256=digest(canonical(spec)), pilot_evidence=result))
            print("Frozen protocol before evaluation")
        elif args.command == "audit":
            from .audit import audit_run
            print(canonical(audit_run(args.run, args.allow_partial)))
        elif args.command == "report":
            from .analysis import report
            print(report(args.run, args.allow_partial))
        elif args.command == "compare":
            from .audit import compare_runs
            print(canonical(compare_runs(args.reference, args.replay)))
        return 0
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
