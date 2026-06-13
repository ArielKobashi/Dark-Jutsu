from __future__ import annotations

import argparse
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TXT = Path(r"C:\Users\davi.souza\Desktop\Nova pasta\pedidos_todos_limpo.txt")
DEFAULT_OUT = ROOT / "data" / "historico_cooperat_antigo.json"

REQ_RE = re.compile(
    r"\bR?REQUISICAO\s+N\.\s*(\d+)\s+de\s+(\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)
ITEM_START_RE = re.compile(r"^\s*(\d{1,3})\s+(\d{1,3}(?:\.\d{3})*\.\d)\s+")
UNIT_QTY_RE = re.compile(
    r"\s{2,}(\S{1,5})\s+(\d{1,3}(?:\.\d{3})*,\d{3}|\d+,\d{3})\s+(\d{1,3}(?:\.\d{3})*,\d{3}|\d+,\d{3})\s+"
)
VALUE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})")


def parse_br_date(value: str) -> date:
    day, month, year = (int(part) for part in value.split("/"))
    if year < 100:
        year += 2000 if year < 80 else 1900
    return date(year, month, day)


def parse_br_number(value: str | None) -> float:
    if not value:
        return 0.0
    value = value.strip().replace(".", "").replace(",", ".")
    try:
        number = float(value)
    except ValueError:
        return 0.0
    return number if math.isfinite(number) else 0.0


def normalize_code(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    return digits.lstrip("0") or digits


def round_number(value: Any) -> float:
    return round(float(value or 0), 4)


def add_event(store: dict[str, dict[str, Any]], event: dict[str, Any]) -> None:
    code = event["codigo"]
    if not code:
        return
    rec = store[code]
    rec["codigo"] = code
    rec["totalEventos"] += 1
    rec["totalQuantidadeCompra"] += event["quantidadeCompra"]
    rec["totalQuantidadeSolicitada"] += event["qtdSolicitada"]
    rec["totalQuantidadeFornecida"] += event["qtdFornecida"]
    rec["totalValorBaixa"] += event["valorBaixa"]
    rec["descricaoMaisRecente"] = event["descricao"] or rec["descricaoMaisRecente"]
    rec["primeiraData"] = min(rec["primeiraData"], event["data"]) if rec["primeiraData"] else event["data"]
    rec["ultimaData"] = max(rec["ultimaData"], event["data"]) if rec["ultimaData"] else event["data"]
    rec["eventos"].append(event)


def parse_item_line(line: str) -> dict[str, Any] | None:
    start = ITEM_START_RE.match(line)
    if not start:
        return None
    rest = line[start.end() :]
    qty = UNIT_QTY_RE.search(rest)
    if not qty:
        return None
    description = rest[: qty.start()].rstrip()
    tail = rest[qty.end() :]
    values = VALUE_RE.findall(tail)
    return {
        "codigo": normalize_code(start.group(2)),
        "descricao": description,
        "unidade": qty.group(1).upper(),
        "qtdSolicitada": parse_br_number(qty.group(2)),
        "qtdFornecida": parse_br_number(qty.group(3)),
        "valorBaixa": parse_br_number(values[-1]) if values else 0.0,
    }


def build_history(txt_path: Path, limit_events: int) -> dict[str, Any]:
    store: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "codigo": "",
            "descricaoMaisRecente": "",
            "totalEventos": 0,
            "totalQuantidadeCompra": 0.0,
            "totalQuantidadeSolicitada": 0.0,
            "totalQuantidadeFornecida": 0.0,
            "totalValorBaixa": 0.0,
            "primeiraData": "",
            "ultimaData": "",
            "eventos": [],
        }
    )
    current_req = ""
    current_date: date | None = None
    headers = 0
    events = 0
    ignored = []

    with txt_path.open("r", encoding="utf-8", errors="replace") as src:
        for line_number, raw in enumerate(src, 1):
            line = raw.rstrip("\r\n")
            req_match = REQ_RE.search(line)
            if req_match:
                current_req = req_match.group(1)
                current_date = parse_br_date(req_match.group(2))
                headers += 1
                continue

            item = parse_item_line(line)
            if not item or current_date is None:
                ignored.append({"linha": line_number, "texto": line[:180]})
                continue

            event = {
                "fonte": "cooperat_antigo",
                "origem": "TXT Cooperat consolidado",
                "requisicao": current_req,
                "data": current_date.isoformat(),
                "dataBr": current_date.strftime("%d/%m/%Y"),
                **item,
            }
            event["quantidadeCompra"] = event["qtdSolicitada"]
            add_event(store, event)
            events += 1

    codigos = {}
    for code, rec in store.items():
        rec["eventos"].sort(key=lambda ev: (ev["data"], int(ev["requisicao"] or 0)), reverse=True)
        total = rec["totalEventos"] or 1
        rec["mediaQuantidadeCompra"] = rec["totalQuantidadeCompra"] / total
        rec["mediaQuantidadeSolicitada"] = rec["totalQuantidadeSolicitada"] / total
        rec["mediaQuantidadeFornecida"] = rec["totalQuantidadeFornecida"] / total
        rec["mediaValorBaixa"] = rec["totalValorBaixa"] / total
        rec["eventos"] = rec["eventos"][:limit_events]
        for key in (
            "totalQuantidadeCompra",
            "totalQuantidadeSolicitada",
            "totalQuantidadeFornecida",
            "totalValorBaixa",
            "mediaQuantidadeCompra",
            "mediaQuantidadeSolicitada",
            "mediaQuantidadeFornecida",
            "mediaValorBaixa",
        ):
            rec[key] = round_number(rec[key])
        for event in rec["eventos"]:
            for key in ("qtdSolicitada", "qtdFornecida", "quantidadeCompra", "valorBaixa"):
                event[key] = round_number(event[key])
        codigos[code] = rec

    return {
        "geradoEm": datetime.now().isoformat(timespec="seconds"),
        "descricao": "Historico Cooperat antigo normalizado por codigo a partir do TXT consolidado.",
        "regraQuantidade": "Cooperat: quantidade de compra = Qtd.Solicitada",
        "regraValor": "Cooperat: Vlr Baixa = valor unitario da peca",
        "limiteEventosPorCodigo": limit_events,
        "fontes": [
            {
                "arquivo": str(txt_path),
                "cabecalhosLidos": headers,
                "eventosUsados": events,
                "linhasIgnoradas": ignored[:20],
            }
        ],
        "totalCodigos": len(codigos),
        "totalEventos": events,
        "codigos": codigos,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera historico Cooperat em JSON a partir do TXT limpo.")
    parser.add_argument("--txt", default=str(DEFAULT_TXT), help="TXT limpo com linhas de requisicao e item.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="JSON de saida.")
    parser.add_argument("--limit", type=int, default=12, help="Eventos recentes guardados por codigo.")
    args = parser.parse_args()

    txt_path = Path(args.txt)
    out_path = Path(args.out)
    payload = build_history(txt_path, args.limit)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Arquivo: {out_path}")
    print(f"Codigos: {payload['totalCodigos']}")
    print(f"Eventos: {payload['totalEventos']}")
    print(f"Cabecalhos: {payload['fontes'][0]['cabecalhosLidos']}")
    print(f"Ignoradas: {len(payload['fontes'][0]['linhasIgnoradas'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
