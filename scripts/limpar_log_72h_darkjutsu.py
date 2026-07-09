from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    path = Path(sys.argv[1])
    if not path.exists():
        return 0

    cutoff = datetime.now() - timedelta(hours=72)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept: list[str] = []
    changed = False

    for line in lines:
        try:
            stamp = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            kept.append(line)
            continue
        if stamp >= cutoff:
            kept.append(line)
        else:
            changed = True

    if changed:
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
