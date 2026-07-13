from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "_migration_runs" / "firebase_audit_latest"
TARGET_FILES = [
    "index.html",
    "dashboard.html",
    "label-editor.html",
    "medidores.html",
    "api",
    "scripts",
    "Automus",
]
EXCLUDED_PARTS = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    "build",
    "dist",
    "pyinstaller",
    "_migration_runs",
}
EXCLUDED_FILES = {
    "scripts/auditar_firebase_restante.py",
}
PATTERNS = [
    ("import", re.compile(r"firebasejs|getDatabase|getAuth|initializeApp|databaseURL")),
    ("read", re.compile(r"\bget\s*\(\s*ref\s*\(|window\.get\s*\(\s*window\.ref\s*\(")),
    ("write", re.compile(r"\bset\s*\(\s*ref\s*\(|window\.set\s*\(\s*window\.ref\s*\(|firebaseSet|firebaseUpdate")),
    ("update", re.compile(r"\bupdate\s*\(\s*ref\s*\(|window\.update\s*\(\s*window\.ref\s*\(")),
    ("push", re.compile(r"\bpush\s*\(\s*ref\s*\(|window\.push\s*\(\s*window\.ref\s*\(")),
    ("transaction", re.compile(r"runTransaction|window\.runTransaction")),
    ("listener", re.compile(r"\bonValue\s*\(|window\.onValue\s*\(")),
    ("rest", re.compile(r"https://.*firebase|firebaseio|databaseURL|firebase_config|/[^\\s\"']+\\.json\\{|\\.json\\?")),
]
PATH_RE = re.compile(r"ref\s*\([^,]+,\s*`([^`]+)`|ref\s*\([^,]+,\s*\"([^\"]+)\"|ref\s*\([^,]+,\s*'([^']+)'")


@dataclass
class Finding:
    file: str
    line: int
    kind: str
    target: str
    text: str


def iter_files() -> list[Path]:
    files: list[Path] = []
    for item in TARGET_FILES:
        path = ROOT / item
        if path.is_file():
            rel = path.relative_to(ROOT).as_posix()
            if rel not in EXCLUDED_FILES:
                files.append(path)
        elif path.is_dir():
            for child in path.rglob("*"):
                rel = child.relative_to(ROOT).as_posix()
                if rel in EXCLUDED_FILES or any(part in EXCLUDED_PARTS for part in child.relative_to(ROOT).parts):
                    continue
                if child.suffix.lower() in {".html", ".js", ".py", ".bat", ".ps1", ".json"}:
                    files.append(child)
    return sorted(set(files))


def target_from_line(line: str) -> str:
    match = PATH_RE.search(line)
    if match:
        return next((group for group in match.groups() if group), "")
    for marker in (
        "estoqueGlobal",
        "usuarios",
        "usuariosBanidos",
        "solicitacoesCadastro",
        "nicknames",
        "contagens",
        "contagemAtual",
        "contagemStatusMaquinas",
        "contagemControle",
        "chatRooms",
        "chatReadState",
        "dashboardConfig",
        "ocorrencias",
        "etiquetasGeradas",
        "rankingEtiquetas",
        "automus",
    ):
        if marker in line:
            return marker
    return ""


def audit() -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            for kind, pattern in PATTERNS:
                if pattern.search(stripped):
                    findings.append(
                        Finding(
                            file=rel,
                            line=idx,
                            kind=kind,
                            target=target_from_line(stripped),
                            text=stripped[:240],
                        )
                    )
                    break
    return findings


def write_reports(findings: list[Finding], output_dir: Path = DEFAULT_OUTPUT) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().isoformat(timespec="seconds")
    grouped: dict[str, int] = {}
    by_target: dict[str, int] = {}
    for finding in findings:
        grouped[finding.kind] = grouped.get(finding.kind, 0) + 1
        target = finding.target or "(sem destino detectado)"
        by_target[target] = by_target.get(target, 0) + 1

    payload = {
        "generated_at": generated_at,
        "total": len(findings),
        "by_kind": grouped,
        "by_target": by_target,
        "findings": [asdict(item) for item in findings],
    }
    (output_dir / "firebase_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Auditoria de Firebase restante",
        "",
        f"Gerado em: `{generated_at}`",
        f"Total de ocorrencias: `{len(findings)}`",
        "",
        "## Por tipo",
        "",
    ]
    for kind, count in sorted(grouped.items()):
        lines.append(f"- `{kind}`: {count}")
    lines.extend(["", "## Por destino", ""])
    for target, count in sorted(by_target.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- `{target}`: {count}")
    lines.extend(["", "## Ocorrencias", ""])
    for finding in findings:
        target = f" destino=`{finding.target}`" if finding.target else ""
        lines.append(f"- `{finding.kind}` [{finding.file}:{finding.line}](../../{finding.file}){target} - `{finding.text}`")
    (output_dir / "firebase_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    findings = audit()
    write_reports(findings)
    print(f"output_dir={DEFAULT_OUTPUT}")
    print(f"findings={len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
