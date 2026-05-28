import argparse
import base64
import hashlib
import json
import logging
import math
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openpyxl import load_workbook

FILE_MAP = {
    "mata105": "incluir.xlsx",
    "mata225": "Saldo Atual.xlsx",
    "mata226": "Saldo por Endereco.xlsx",
    "estoque_minimo": "estoque_minimo.xlsx",
    "mata110": "mata110.xlsx",
    "mata111": "mata111.xlsx",
    "mata112": "mata112.xlsx",
}


def _json_hash(value: Any) -> str:
    raw = _json_payload(value, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _sanitize_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(v) for v in value]
    return value


def _json_payload(value: Any, sort_keys: bool = False, indent: int | None = None) -> str:
    return json.dumps(
        _sanitize_json_value(value),
        ensure_ascii=False,
        sort_keys=sort_keys,
        separators=None if indent is not None else (",", ":"),
        indent=indent,
        allow_nan=False,
    )


def _http_json(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any] | list[Any] | None:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = _json_payload(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url=url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code} em {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Falha de rede em {url}: {exc}") from exc


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) < 2:
        return {}
    raw = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _id_token_expired(token: str, skew_seconds: int = 120) -> bool:
    payload = _decode_jwt_payload(token)
    exp = payload.get("exp")
    try:
        return int(exp) <= int(time.time()) + skew_seconds
    except Exception:
        return False


def _extract_firebase_config(index_html_path: Path) -> tuple[str, str]:
    bundled_root = Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False) else None
    candidates = [index_html_path.parent / "scripts" / "firebase_config.json"]
    if bundled_root:
        candidates.append(bundled_root / "scripts" / "firebase_config.json")
    for scripts_config in candidates:
        if not scripts_config or not scripts_config.exists():
            continue
        cfg = json.loads(scripts_config.read_text(encoding="utf-8-sig"))
        api_key = _safe_text(cfg.get("apiKey"))
        db_url = _safe_text(cfg.get("databaseURL")).rstrip("/")
        if api_key and db_url:
            return api_key, db_url
    html = index_html_path.read_text(encoding="utf-8", errors="replace")
    api_match = re.search(r'apiKey:\s*"([^"]+)"', html)
    db_match = re.search(r'databaseURL:\s*"([^"]+)"', html)
    if not api_match or not db_match:
        raise RuntimeError("Nao foi possivel extrair apiKey/databaseURL do index.html")
    return api_match.group(1), db_match.group(1).rstrip("/")


def _sheet_name_key(value: Any) -> str:
    txt = _safe_text(value).lower()
    normalized = unicodedata.normalize("NFKD", txt)
    return normalized.encode("ascii", "ignore").decode("ascii").strip()


def _read_sheet(path: Path, sheet_name: str | None = None) -> list[list[Any]]:
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        ws_name = wb.sheetnames[0]
        if sheet_name:
            if sheet_name in wb.sheetnames:
                ws_name = sheet_name
            else:
                alvo = _sheet_name_key(sheet_name)
                ws_name = next(
                    (
                        name for name in wb.sheetnames
                        if _sheet_name_key(name) == alvo
                        or alvo in _sheet_name_key(name)
                        or _sheet_name_key(name) in alvo
                    ),
                    ws_name,
                )
        ws = wb[ws_name]
        out: list[list[Any]] = []
        for row in ws.iter_rows(values_only=True):
            out.append(list(row))
        return out
    finally:
        wb.close()


def _is_endereco_valido(value: Any) -> bool:
    txt = ("" if value is None else str(value)).strip()
    if not txt:
        return False
    lower = txt.lower()
    invalid = {"sem endereco", "sem endereço", "nd", "n/d", "na", "n/a", "-", "--"}
    if lower in invalid:
        return False
    return True


def _num(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value).strip()
    if not txt:
        return 0.0
    txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return 0.0


def _optional_num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    txt = str(value).strip()
    if not txt:
        return None
    txt = txt.replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except ValueError:
        return None


def _optional_limit_num(value: Any) -> float | None:
    num = _optional_num(value)
    if num is None or num == 0:
        return None
    return num


def _reposicao_media(minimo: Any, maximo: Any) -> float | None:
    min_num = _optional_limit_num(minimo)
    max_num = _optional_limit_num(maximo)
    if min_num is None or max_num is None:
        return None
    if max_num <= min_num:
        return None
    return max_num - min_num


def _ceil_positive(value: Any) -> int | None:
    num = _optional_num(value)
    if num is None or num <= 0:
        return None
    return max(1, int(math.ceil(num)))


def _historico_consumo_stats(item: dict[str, Any], historico: dict[str, Any]) -> dict[str, float]:
    hist = historico.get(_ajuste_key(_item_key(item)))
    saidas: list[float] = []
    if isinstance(hist, list):
        for ent in hist[-12:]:
            if not isinstance(ent, dict):
                continue
            delta = _optional_num(ent.get("delta"))
            if delta is not None and delta < 0:
                saidas.append(abs(delta))
    if not saidas:
        return {"media": 0.0, "pico": 0.0, "desvio": 0.0, "eventos": 0.0}
    media = sum(saidas) / len(saidas)
    variancia = sum((v - media) ** 2 for v in saidas) / len(saidas)
    return {
        "media": media,
        "pico": max(saidas),
        "desvio": math.sqrt(variancia),
        "eventos": float(len(saidas)),
    }


def _sugerir_limites_estoque(
    item: dict[str, Any],
    historico: dict[str, Any],
    pedidos_compra: dict[str, Any],
) -> dict[str, Any] | None:
    consumo = _historico_consumo_stats(item, historico)
    saldo_atual = _optional_num(item.get("saldo")) or 0.0
    limites_cooperat = item.get("limitesCooperat") if isinstance(item.get("limitesCooperat"), dict) else {}
    saldo_anterior = _optional_num(limites_cooperat.get("saldoAnterior") if isinstance(limites_cooperat, dict) else None)
    consumo_entre_planilhas = max(0.0, (saldo_anterior or 0.0) - saldo_atual) if saldo_anterior is not None else 0.0

    codigo = _ascii_lower(item.get("protheus") or item.get("protheusKey") or item.get("cooperat"))
    pedido = pedidos_compra.get(_ajuste_key(codigo)) if codigo else None
    if not isinstance(pedido, dict) and codigo:
        pedido = pedidos_compra.get(codigo)
    media_pedido = _optional_num(pedido.get("mediaPedido")) if isinstance(pedido, dict) else None
    media_pedido = media_pedido or 0.0
    minimo_por_compra = media_pedido * 0.35 if media_pedido > 0 else 0.0

    candidatos_consumo = [
        consumo["media"],
        consumo["pico"] * 0.65,
        consumo_entre_planilhas,
    ]
    candidatos_consumo = [v for v in candidatos_consumo if math.isfinite(v) and v > 0]
    candidatos = [
        *candidatos_consumo,
        minimo_por_compra,
    ]
    candidatos = [v for v in candidatos if math.isfinite(v) and v > 0]
    if not candidatos:
        return None

    demanda_base = max(candidatos)
    estoque_seguranca = max(consumo["desvio"], demanda_base * 0.35, consumo["pico"] * 0.25, minimo_por_compra)
    minimo_estimado = max(demanda_base + estoque_seguranca, minimo_por_compra) if candidatos_consumo else minimo_por_compra
    minimo = _ceil_positive(minimo_estimado)
    if minimo is None:
        return None
    lote = _ceil_positive(max(media_pedido, demanda_base * 1.5, minimo * 0.8)) or minimo
    maximo = max(minimo + lote, minimo + 1)
    return {
        "minimo": minimo,
        "maximo": maximo,
        "reposicao": maximo - minimo,
        "criterio": {
            "demandaBase": demanda_base,
            "estoqueSeguranca": estoque_seguranca,
            "consumoMedio": consumo["media"],
            "consumoPico": consumo["pico"],
            "eventosConsumo": int(consumo["eventos"]),
            "consumoEntrePlanilhas": consumo_entre_planilhas,
            "mediaPedido": media_pedido,
            "minimoPorCompra": minimo_por_compra,
            "fontePrincipal": "pedido_compra" if media_pedido > 0 and not candidatos_consumo else "consumo",
        },
    }


def _aplicar_sugestoes_estoque(
    itens: list[dict[str, Any]],
    historico: dict[str, Any],
    pedidos_compra: dict[str, Any],
) -> None:
    for item in itens:
        if not isinstance(item, dict):
            continue
        if item.get("limitesOrigem") in {"manual", "cooperat"}:
            item.pop("sugestaoEstoque", None)
            continue
        sugestao = _sugerir_limites_estoque(item, historico, pedidos_compra)
        if not sugestao:
            item.pop("sugestaoEstoque", None)
            continue
        if item.get("minimo") in (None, ""):
            item["minimo"] = sugestao["minimo"]
            item["minimoOrigem"] = "automatico"
        if item.get("maximo") in (None, ""):
            item["maximo"] = sugestao["maximo"]
            item["maximoOrigem"] = "automatico"
        if item.get("minimoOrigem") == "automatico" or item.get("maximoOrigem") == "automatico":
            item["limitesOrigem"] = item.get("limitesOrigem") or "automatico"
            item["reposicao"] = _reposicao_media(item.get("minimo"), item.get("maximo"))
            item["reposicaoOrigem"] = "automatico"
            item["sugestaoEstoque"] = sugestao["criterio"]


def _ajuste_key(item_key: str) -> str:
    raw = item_key.encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _item_key(item: dict[str, Any]) -> str:
    return _safe_text(item.get("protheusKey") or item.get("protheus"))


def _atualizar_historico_saldo(
    novos: list[dict[str, Any]],
    anteriores: list[dict[str, Any]],
    historico_atual: dict[str, Any],
    agora_ms: int,
) -> dict[str, Any]:
    anterior_por_key: dict[str, dict[str, Any]] = {}
    for item in anteriores:
        if not isinstance(item, dict):
            continue
        key = _item_key(item)
        if key and key not in anterior_por_key:
            anterior_por_key[key] = item

    historico = dict(historico_atual or {})
    data_txt = datetime.fromtimestamp(agora_ms / 1000).strftime("%d/%m/%Y")

    for item in novos:
        if not isinstance(item, dict):
            continue
        key = _item_key(item)
        if not key or key not in anterior_por_key:
            continue
        saldo_anterior = _optional_num(anterior_por_key[key].get("saldo"))
        saldo_atual = _optional_num(item.get("saldo"))
        if saldo_anterior is None or saldo_atual is None:
            continue
        delta = saldo_atual - saldo_anterior
        if not delta:
            continue
        hist_key = _ajuste_key(key)
        lista = historico.get(hist_key) if isinstance(historico.get(hist_key), list) else []
        lista = list(lista)
        lista.append(
            {
                "data": data_txt,
                "timestamp": agora_ms,
                "delta": delta,
                "tipo": "entrada" if delta > 0 else "saida",
                "saldoAnterior": saldo_anterior,
                "saldoAtual": saldo_atual,
            }
        )
        historico[hist_key] = lista[-80:]

    return historico


def _sheet_date(value: Any) -> tuple[str, int]:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y"), int(value.timestamp() * 1000)
    txt = _safe_text(value)
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(txt[:10], fmt)
            return dt.strftime("%d/%m/%Y"), int(dt.timestamp() * 1000)
        except Exception:
            pass
    return txt, 0


def _entrada_depois(item: dict[str, Any], historico: dict[str, Any], timestamp: int) -> bool:
    hist = historico.get(_ajuste_key(_item_key(item)))
    if not isinstance(hist, list):
        return False
    for ent in hist:
        if not isinstance(ent, dict):
            continue
        if ent.get("tipo") == "entrada" and _num(ent.get("delta")) > 0 and (not timestamp or int(ent.get("timestamp") or 0) >= timestamp):
            return True
    return False


def _montar_pedidos_compra(
    mata110: list[list[Any]] | None,
    mata111: list[list[Any]] | None,
    mata112: list[list[Any]] | None,
    itens: list[dict[str, Any]],
    historico: dict[str, Any],
) -> dict[str, Any]:
    pedidos_por_codigo: dict[str, list[dict[str, Any]]] = {}
    for idx, row in enumerate((mata111 or [])[1:]):
        codigo = _ascii_lower(row[6] if len(row) > 6 else "")
        if not codigo:
            continue
        data_txt, ts = _sheet_date(row[2] if len(row) > 2 else "")
        pedidos_por_codigo.setdefault(codigo, []).append({
            "codigo": codigo,
            "dataPedido": data_txt,
            "timestamp": ts,
            "quantidadePedida": _num(row[9] if len(row) > 9 else 0),
            "quantidadeRecebida": _num(row[11] if len(row) > 11 else 0),
            "rowIndex": idx,
        })
    for lista in pedidos_por_codigo.values():
        lista.sort(key=lambda p: (p.get("timestamp") or 0, p.get("rowIndex") or 0), reverse=True)

    solicitacoes_por_codigo: dict[str, list[dict[str, Any]]] = {}
    for idx, row in enumerate((mata110 or [])[1:]):
        codigo = _ascii_lower(row[3] if len(row) > 3 else "")
        if not codigo:
            continue
        solicitacoes_por_codigo.setdefault(codigo, []).append({
            "codigo": codigo,
            "quantidadeSolicitada": _num(row[5] if len(row) > 5 else 0),
            "solicitante": _safe_text(row[7] if len(row) > 7 else ""),
            "quantidadeEmPedido": _num(row[8] if len(row) > 8 else 0),
            "aceitoPor": _safe_text(row[17] if len(row) > 17 else ""),
            "rowIndex": idx,
        })

    entradas_por_codigo: dict[str, list[dict[str, Any]]] = {}
    for idx, row in enumerate((mata112 or [])[1:]):
        codigo = _ascii_lower(row[0] if len(row) > 0 else "")
        if not codigo:
            continue
        data_txt, ts = _sheet_date(row[12] if len(row) > 12 else "")
        entradas_por_codigo.setdefault(codigo, []).append({
            "codigo": codigo,
            "quantidadeEntrada": _num(row[3] if len(row) > 3 else 0),
            "saldoAEnderecar": _num(row[4] if len(row) > 4 else 0),
            "dataEntrada": data_txt,
            "timestamp": ts,
            "rowIndex": idx,
        })
    for lista in entradas_por_codigo.values():
        lista.sort(key=lambda e: (e.get("timestamp") or 0, e.get("rowIndex") or 0), reverse=True)

    estado: dict[str, Any] = {}
    for item in itens:
        codigo = _ascii_lower(item.get("protheus") or item.get("protheusKey") or item.get("cooperat"))
        if not codigo:
            continue
        pedidos = pedidos_por_codigo.get(codigo, [])
        solicitacoes = solicitacoes_por_codigo.get(codigo, [])
        entradas = entradas_por_codigo.get(codigo, [])
        entrada_ativa = None

        def localizar_entrada(pedido: dict[str, Any]) -> dict[str, Any] | None:
            pedido_ts = int(pedido.get("timestamp") or 0)
            return next((e for e in entradas if not pedido_ts or not int(e.get("timestamp") or 0) or int(e.get("timestamp") or 0) >= pedido_ts), None)

        pedido = None
        for candidato in pedidos:
            entrada = localizar_entrada(candidato)
            if entrada and _num(entrada.get("saldoAEnderecar")) <= 0:
                continue
            if not entrada and _entrada_depois(item, historico, int(candidato.get("timestamp") or 0)):
                continue
            pedido = candidato
            entrada_ativa = entrada
            break
        solicitacao = next(reversed(solicitacoes), None) if solicitacoes else None
        recebidos = [p for p in pedidos if _num(p.get("quantidadeRecebida")) > 0]
        media = sum(_num(p.get("quantidadeRecebida")) or _num(p.get("quantidadePedida")) for p in recebidos) / len(recebidos) if recebidos else None
        titulo, detalhe, status, recebido_sem_entrada = "Sem solicitação de pedido", "", "sem", 0
        if solicitacao:
            if not solicitacao.get("aceitoPor") and _num(solicitacao.get("quantidadeEmPedido")) <= 0:
                status, titulo, detalhe = "aguardando_liberacao", "Aguardando liberação...", f"Solicitado por: {solicitacao.get('solicitante') or '-'}"
            elif not pedido and solicitacao.get("aceitoPor"):
                status, titulo, detalhe = "aguardando_pedido", "Aguardando pedido de compra...", f"Aceito por: {solicitacao.get('aceitoPor') or '-'}"
            elif pedido and _num(pedido.get("quantidadeRecebida")) <= 0:
                status, titulo, detalhe = "aguardando_recebimento", "Aguardando recebimento...", f"Pedido feito em: {pedido.get('dataPedido') or '-'}"
            elif pedido and entrada_ativa and _num(entrada_ativa.get("saldoAEnderecar")) > 0:
                status = "aguardando_enderecamento"
                titulo = "Aguardando endereçamento..."
                detalhe = f"Entrou dia: {entrada_ativa.get('dataEntrada') or '-'} - {_format_num(entrada_ativa.get('quantidadeEntrada'))} unidades"
            elif pedido:
                status, titulo, detalhe = "aguardando_contagem", "Aguardando contagem de nota...", f"Recebido em: {pedido.get('dataPedido') or '-'}"
                recebido_sem_entrada = _num(pedido.get("quantidadeRecebida"))
        estado[_ajuste_key(codigo)] = {
            "codigo": codigo,
            "status": status,
            "titulo": titulo,
            "detalhe": detalhe,
            "solicitacao": solicitacao,
            "pedido": pedido,
            "entradaEndereco": entrada_ativa,
            "mediaPedido": media,
            "recebidoSemEntrada": recebido_sem_entrada,
        }
    return estado


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _format_num(value: Any) -> str:
    num = _num(value)
    if float(num).is_integer():
        return str(int(num))
    return f"{num:.2f}".replace(".", ",")


def _ascii_lower(value: Any) -> str:
    txt = _safe_text(value).lower()
    if not txt:
        return ""
    normalized = unicodedata.normalize("NFKD", txt)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _detect_incluir_columns(incluir: list[list[Any]]) -> dict[str, int]:
    header = incluir[1] if len(incluir) > 1 else incluir[0] if incluir else []
    cols = {"protheus": 1, "cooperat": 0, "descricao": 2, "inicio": 2}

    for index, value in enumerate(header):
        name = _ascii_lower(value)
        if not name:
            continue
        is_codigo = name in {"codigo", "cod produto", "codigo produto"}
        is_descricao = name in {"descricao", "descrição"}
        is_referencia = "refer" in name or "antigo" in name or name == "cooperat"

        if is_codigo:
            cols["protheus"] = index
        if is_descricao:
            cols["descricao"] = index
        if is_referencia:
            cols["cooperat"] = index

    if len(header) > 1 and _ascii_lower(header[0]) == "codigo" and _ascii_lower(header[1]) == "descricao":
        cols["protheus"] = 0
        cols["descricao"] = 1
        cols["cooperat"] = 2

    return cols


def _is_descricao_dado_morto(value: Any) -> bool:
    desc = _ascii_lower(value)
    return "desativado" in desc or "bloqueado" in desc


def _morto_key(item: dict[str, Any]) -> str:
    return _safe_text(item.get("protheus") or item.get("cooperat") or item.get("protheusKey"))


def _preparar_item_morto(item: dict[str, Any]) -> dict[str, Any]:
    morto = dict(item)
    key = _morto_key(morto)
    morto["morto"] = True
    if key:
        morto["protheusKey"] = "MORTO|" + key
    return morto


def _separar_dados_mortos_por_descricao(
    itens: list[dict[str, Any]],
    dados_mortos_anteriores: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ativos: list[dict[str, Any]] = []
    mortos: list[dict[str, Any]] = []
    codigos_ativos: set[str] = set()
    codigos_mortos: set[str] = set()

    for item in itens:
        key = _morto_key(item)
        if _is_descricao_dado_morto(item.get("descricao")):
            morto = _preparar_item_morto(item)
            if key and key in codigos_mortos:
                continue
            if key:
                codigos_mortos.add(key)
            mortos.append(morto)
            continue
        ativo = dict(item)
        ativo["morto"] = False
        ativo.pop("protheusKey", None)
        if key:
            codigos_ativos.add(key)
        ativos.append(ativo)

    for item in dados_mortos_anteriores:
        if not isinstance(item, dict):
            continue
        key = _morto_key(item)
        if key and (key in codigos_ativos or key in codigos_mortos):
            continue
        morto = dict(item)
        morto["morto"] = True
        mortos.append(morto)
        if key:
            codigos_mortos.add(key)

    return ativos, mortos


def _build_items(
    incluir: list[list[Any]],
    cooperat: list[list[Any]],
    saldo_atual: list[list[Any]],
    saldo_endereco: list[list[Any]],
    estoque_minimo: list[list[Any]] | None,
    dados_anteriores: list[dict[str, Any]],
    ajustes_itens: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    novos: list[dict[str, Any]] = []

    saldo_atual_idx: dict[str, float] = {}
    for row in saldo_atual[1:]:
        if len(row) < 5:
            continue
        cod = _safe_text(row[1])
        if cod:
            saldo_atual_idx[cod] = _num(row[5] if len(row) > 5 else row[4])

    end_antigo_idx: dict[str, str] = {}
    for row in cooperat[2:]:
        if not row:
            continue
        cod = _safe_text(row[0] if len(row) > 0 else "")
        if not cod:
            continue
        end = " ".join(
            [
                _safe_text(row[3] if len(row) > 3 else ""),
                _safe_text(row[4] if len(row) > 4 else ""),
                _safe_text(row[5] if len(row) > 5 else ""),
            ]
        ).strip()
        if _is_endereco_valido(end):
            end_antigo_idx[cod] = end

    enderecos_idx: dict[str, list[dict[str, Any]]] = {}
    for row in saldo_endereco[1:]:
        if len(row) < 9:
            continue
        cod = _safe_text(row[1])
        if not cod:
            continue
        ent = {
            "endereco": _safe_text(row[4]) or "ND",
            "armazem": _safe_text(row[2]) or "ND",
            "saldo": _num(row[8]),
        }
        enderecos_idx.setdefault(cod, []).append(ent)

    estoque_minimo_idx: dict[str, dict[str, float]] = {}
    for row in (estoque_minimo or [])[1:]:
        if len(row) < 2:
            continue
        cooperat_cod = _safe_text(row[1] if len(row) > 1 else "")
        if not cooperat_cod:
            continue
        cod_lower = _ascii_lower(cooperat_cod)
        if "codigo" in cod_lower or "código" in cod_lower or "item" in cod_lower:
            continue
        minimo = _optional_limit_num(row[6] if len(row) > 6 else None)
        maximo = _optional_limit_num(row[7] if len(row) > 7 else None)
        reposicao_planilha = _optional_limit_num(row[8] if len(row) > 8 else None)
        saldo_anterior = _optional_num(row[5] if len(row) > 5 else None)
        reposicao = reposicao_planilha if reposicao_planilha is not None else _reposicao_media(minimo, maximo)
        if minimo is None and maximo is None and reposicao is None and saldo_anterior is None:
            continue
        estoque_minimo_idx[cooperat_cod] = {
            "temLinha": True,
            "minimo": minimo,
            "maximo": maximo,
            "reposicao": reposicao,
            "saldoAnterior": saldo_anterior,
        }

    prev_by_protheus: dict[str, dict[str, Any]] = {}
    prev_by_cooperat: dict[str, dict[str, Any]] = {}
    for d in dados_anteriores:
        if not isinstance(d, dict):
            continue
        p = _safe_text(d.get("protheus"))
        c = _safe_text(d.get("cooperat"))
        if p and p not in prev_by_protheus:
            prev_by_protheus[p] = d
        if c and c not in prev_by_cooperat:
            prev_by_cooperat[c] = d

    incluir_cols = _detect_incluir_columns(incluir)

    for row in incluir[incluir_cols["inicio"]:]:
        if len(row) <= incluir_cols["protheus"]:
            continue

        protheus = _safe_text(row[incluir_cols["protheus"]])
        cooperat_cod = _safe_text(row[incluir_cols["cooperat"]] if len(row) > incluir_cols["cooperat"] else "")
        descricao = _safe_text(row[incluir_cols["descricao"]] if len(row) > incluir_cols["descricao"] else "")
        if not protheus:
            continue

        item = {
            "protheus": protheus,
            "cooperat": cooperat_cod,
            "descricao": descricao,
            "enderecoPrincipal": "Sem Endereco",
            "armazemPrincipal": "ND",
            "saldo": 0.0,
            "enderecos": [],
            "comentarios": [],
            "morto": False,
        }

        if protheus in saldo_atual_idx:
            item["saldo"] = saldo_atual_idx[protheus]

        if cooperat_cod in end_antigo_idx:
            item["enderecoPrincipal"] = end_antigo_idx[cooperat_cod]

        if not _is_endereco_valido(item["enderecoPrincipal"]):
            anterior = prev_by_protheus.get(protheus) or prev_by_cooperat.get(cooperat_cod)
            if anterior and _is_endereco_valido(anterior.get("enderecoPrincipal")):
                item["enderecoPrincipal"] = _safe_text(anterior.get("enderecoPrincipal"))

        enderecos = enderecos_idx.get(protheus, [])
        if enderecos:
            item["enderecos"] = enderecos
            validos = [e for e in enderecos if _is_endereco_valido(e.get("endereco"))]
            if validos:
                item["enderecoPrincipal"] = _safe_text(validos[0].get("endereco"))
                item["armazemPrincipal"] = _safe_text(validos[0].get("armazem")) or "ND"
            item["saldo"] = sum(_num(e.get("saldo")) for e in enderecos)

        estoque_minimo_item = estoque_minimo_idx.get(cooperat_cod)
        if estoque_minimo_item:
            item["limitesCooperat"] = {
                "minimo": estoque_minimo_item.get("minimo"),
                "maximo": estoque_minimo_item.get("maximo"),
                "reposicao": estoque_minimo_item.get("reposicao"),
                "saldoAnterior": estoque_minimo_item.get("saldoAnterior"),
            }
            tem_limite_planilha = (
                estoque_minimo_item.get("minimo") is not None
                or estoque_minimo_item.get("maximo") is not None
                or estoque_minimo_item.get("reposicao") is not None
            )
            if tem_limite_planilha and estoque_minimo_item.get("minimo") is not None:
                item["minimo"] = estoque_minimo_item["minimo"]
                item["minimoOrigem"] = "cooperat"
            if tem_limite_planilha and estoque_minimo_item.get("maximo") is not None:
                item["maximo"] = estoque_minimo_item["maximo"]
                item["maximoOrigem"] = "cooperat"
            if tem_limite_planilha and estoque_minimo_item.get("reposicao") is not None:
                item["reposicao"] = estoque_minimo_item["reposicao"]
                item["reposicaoOrigem"] = "cooperat"
            if tem_limite_planilha:
                item["limitesOrigem"] = "cooperat"

        anterior = prev_by_protheus.get(protheus) or prev_by_cooperat.get(cooperat_cod)
        if anterior:
            if estoque_minimo is None and not item.get("limitesCooperat") and isinstance(anterior.get("limitesCooperat"), dict):
                item["limitesCooperat"] = anterior.get("limitesCooperat")
            if estoque_minimo is None and item.get("minimo") is None and anterior.get("minimo") is not None:
                item["minimo"] = anterior.get("minimo")
                item["minimoOrigem"] = anterior.get("minimoOrigem") or anterior.get("limitesOrigem") or "anterior"
            if estoque_minimo is None and item.get("maximo") is None and anterior.get("maximo") is not None:
                item["maximo"] = anterior.get("maximo")
                item["maximoOrigem"] = anterior.get("maximoOrigem") or anterior.get("limitesOrigem") or "anterior"
            if estoque_minimo is None and not item.get("limitesOrigem"):
                item["limitesOrigem"] = anterior.get("limitesOrigem") or "anterior"
            if estoque_minimo is None and not item.get("reposicaoOrigem"):
                item["reposicaoOrigem"] = anterior.get("reposicaoOrigem") or item.get("limitesOrigem")

        ajuste = (ajustes_itens or {}).get(_ajuste_key(protheus))
        if isinstance(ajuste, dict):
            if "minimo" in ajuste:
                item["minimo"] = _optional_limit_num(ajuste.get("minimo"))
                item["minimoOrigem"] = "manual"
            if "maximo" in ajuste:
                item["maximo"] = _optional_limit_num(ajuste.get("maximo"))
                item["maximoOrigem"] = "manual"
            item["limitesOrigem"] = "manual"

        reposicao_cooperat = None
        if item.get("limitesOrigem") == "cooperat" and isinstance(item.get("limitesCooperat"), dict):
            reposicao_cooperat = _optional_limit_num(item["limitesCooperat"].get("reposicao"))
        reposicao_final = reposicao_cooperat if reposicao_cooperat is not None else _reposicao_media(item.get("minimo"), item.get("maximo"))
        if reposicao_final is None:
            item.pop("reposicao", None)
        else:
            item["reposicao"] = reposicao_final
            item["reposicaoOrigem"] = item.get("limitesOrigem") or item.get("reposicaoOrigem") or "calculada"

        novos.append(item)

    return novos


def _resolve_file(base_dir: Path, filename: str) -> Path:
    candidates = [
        base_dir / "downloads" / filename,
        Path.home() / "Desktop" / "AMBIENTE ROSA" / filename,
        Path.home() / "Desktop" / filename,
        Path.home() / "Downloads" / filename,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    raise FileNotFoundError(f"Arquivo nao encontrado: {filename}")


def _resolve_optional_file(base_dir: Path, filename: str) -> Path | None:
    candidates = [
        base_dir / "downloads" / filename,
        Path.home() / "Desktop" / "AMBIENTE ROSA" / filename,
        Path.home() / "Desktop" / filename,
        Path.home() / "Downloads" / filename,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    return None


def _write_local_backup(project_root: Path, backup_payload: dict[str, Any], agora_ms: int, log: logging.Logger) -> Path:
    backup_dir = project_root / "_backups" / "automus"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"firebase_backup_{agora_ms}.json"
    backup_path.write_text(
        _json_payload(backup_payload, indent=2),
        encoding="utf-8",
    )
    if not backup_path.exists() or backup_path.stat().st_size <= 0:
        raise RuntimeError("NAO CONFORME: backup local nao foi salvo corretamente.")
    log.info(
        "BACKUP_LOCAL_OK | arquivo=%s | bytes=%s",
        backup_path,
        backup_path.stat().st_size,
    )
    return backup_path


def run_automus_update(
    config_path: Path,
    project_root: Path,
    logger: logging.Logger | None = None,
    auth_id_token: str | None = None,
    auth_email: str | None = None,
) -> None:
    log = logger or logging.getLogger("automus_update")

    if not config_path.exists() and not auth_id_token:
        raise FileNotFoundError(
            f"Config do Automus nao encontrada em {config_path}. Crie com email e password."
        )

    cfg = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    email = _safe_text(cfg.get("email"))
    password = _safe_text(cfg.get("password"))
    updated_by = _safe_text(cfg.get("updated_by")) or "atualizado automaticamente via Automus"

    if not auth_id_token and (not email or not password):
        raise RuntimeError("Config invalida: preencha 'email' e 'password' em automus_config.json")
    log.info("TEST_AUTOMUS_CONFIG_OK | config=%s | email=%s", config_path, auth_email or email)

    index_path = project_root / "index.html"
    api_key, db_url = _extract_firebase_config(index_path)

    def autenticar_config() -> tuple[str, str]:
        auth_resp = _http_json(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}",
            method="POST",
            payload={
                "email": email,
                "password": password,
                "returnSecureToken": True,
            },
        )
        if not isinstance(auth_resp, dict) or not auth_resp.get("idToken"):
            raise RuntimeError("AUTOMUS: falha ao autenticar no Firebase.")
        return str(auth_resp["idToken"]), _safe_text(auth_resp.get("email")) or email

    incluir_path = _resolve_file(project_root, FILE_MAP["mata105"])
    saldo_atual_path = _resolve_file(project_root, FILE_MAP["mata225"])
    saldo_endereco_path = _resolve_file(project_root, FILE_MAP["mata226"])
    estoque_minimo_path = _resolve_optional_file(project_root, FILE_MAP["estoque_minimo"])
    mata110_path = _resolve_optional_file(project_root, FILE_MAP["mata110"])
    mata111_path = _resolve_optional_file(project_root, FILE_MAP["mata111"])
    mata112_path = _resolve_optional_file(project_root, FILE_MAP["mata112"])
    log.info(
        "TEST_PLANILHAS_RESOLVIDAS_OK | incluir=%s | saldoAtual=%s | saldoEndereco=%s | estoque_minimo=%s",
        incluir_path,
        saldo_atual_path,
        saldo_endereco_path,
        estoque_minimo_path or "NAO_ENCONTRADA",
    )

    if auth_id_token and _id_token_expired(auth_id_token):
        if not email or not password:
            raise RuntimeError("AUTOMUS: sessao Firebase expirada e automus_config.json nao tem email/password para renovar.")
        log.warning("AUTOMUS: sessao Firebase ADM expirada; renovando autenticacao antes do envio.")
        auth_id_token = None

    if auth_id_token:
        log.info("AUTOMUS: usando sessão Firebase ADM já autenticada.")
        id_token = str(auth_id_token)
        safe_email = _safe_text(auth_email) or "sessao-adm"
    else:
        log.info("AUTOMUS: iniciando autenticacao Firebase para envio sem navegador.")
        id_token, safe_email = autenticar_config()
    token_qs = f"?auth={id_token}"

    usando_token_sessao = bool(auth_id_token)
    while True:
        estoque_url = f"{db_url}/estoqueGlobal.json{token_qs}"
        try:
            snapshot = _http_json(estoque_url, method="GET")
            break
        except RuntimeError as exc:
            if usando_token_sessao and email and password and "HTTP 401" in str(exc):
                log.warning("AUTOMUS: sessao Firebase ADM recusada pelo banco; renovando autenticacao e tentando novamente.")
                id_token, safe_email = autenticar_config()
                token_qs = f"?auth={id_token}"
                usando_token_sessao = False
                continue
            raise
    banco = snapshot if isinstance(snapshot, dict) else {}
    hash_banco_antes = _json_hash(banco)
    log.info("TEST_FIREBASE_LEITURA_OK | hashAntes=%s", hash_banco_antes)

    dados_anteriores = banco.get("dados") if isinstance(banco.get("dados"), list) else []
    dados_mortos = banco.get("dadosMortos") if isinstance(banco.get("dadosMortos"), list) else []
    ajustes_itens = banco.get("ajustesItens") if isinstance(banco.get("ajustesItens"), dict) else {}
    historico_saldo = banco.get("historicoSaldo") if isinstance(banco.get("historicoSaldo"), dict) else {}

    incluir = _read_sheet(incluir_path)
    saldo_atual = _read_sheet(saldo_atual_path)
    saldo_endereco = _read_sheet(saldo_endereco_path)
    estoque_minimo = _read_sheet(estoque_minimo_path) if estoque_minimo_path else None
    mata110 = _read_sheet(mata110_path) if mata110_path else None
    mata111 = _read_sheet(mata111_path) if mata111_path else None
    mata112 = _read_sheet(mata112_path, "Saldos a Endereçar") if mata112_path else None
    log.info(
        "TEST_PLANILHAS_LIDAS_OK | incluir_linhas=%s | saldoAtual_linhas=%s | saldoEndereco_linhas=%s | estoque_minimo_linhas=%s",
        len(incluir),
        len(saldo_atual),
        len(saldo_endereco),
        len(estoque_minimo) if estoque_minimo else 0,
    )
    if len(incluir) < 3 or len(saldo_atual) < 2 or len(saldo_endereco) < 2:
        raise RuntimeError(
            "NAO CONFORME: uma ou mais planilhas estao vazias/incompletas para atualizacao."
        )

    novos_dados = _build_items(
        incluir,
        [],
        saldo_atual,
        saldo_endereco,
        estoque_minimo,
        dados_anteriores,
        ajustes_itens,
    )
    if not novos_dados:
        raise RuntimeError("NAO CONFORME: geracao de itens resultou em 0 registros.")
    novos_dados, dados_mortos = _separar_dados_mortos_por_descricao(novos_dados, dados_mortos)
    log.info(
        "TEST_GERACAO_ITENS_OK | itensAtivos=%s | dadosMortos=%s",
        len(novos_dados),
        len(dados_mortos),
    )

    agora_ms = int(time.time() * 1000)
    historico_saldo = _atualizar_historico_saldo(
        novos_dados,
        dados_anteriores,
        historico_saldo,
        agora_ms,
    )
    pedidos_compra = _montar_pedidos_compra(mata110, mata111, mata112, novos_dados, historico_saldo)
    _aplicar_sugestoes_estoque(novos_dados, historico_saldo, pedidos_compra)

    payload = {
        "dados": novos_dados,
        "dadosMortos": dados_mortos,
        "ajustesItens": ajustes_itens,
        "historicoSaldo": historico_saldo,
        "pedidosCompra": pedidos_compra,
        "ultimaAtualizacao": agora_ms,
        "atualizadoPor": updated_by,
        "atualizacaoAutomatica": True,
        "ultimaAtualizacaoAutomatica": agora_ms,
        "mapeamentoArquivos": {
            "mata105": "incluir.xlsx",
            "mata225": "saldo.atual.xlsx",
            "mata226": "saldo.por.endereco.xlsx",
            **({"estoque_minimo": "estoque_minimo.xlsx"} if estoque_minimo_path else {}),
            **({"mata110": "mata110.xlsx"} if mata110_path else {}),
            **({"mata111": "mata111.xlsx"} if mata111_path else {}),
            **({"mata112": "mata112.xlsx"} if mata112_path else {}),
        },
        "automus": {
            "executadoEm": datetime.now().isoformat(timespec="seconds"),
            "usuario": safe_email,
        },
    }

    backup_url = f"{db_url}/estoqueGlobalBackups/automus_last.json{token_qs}"
    backup_payload = {
        "salvoEm": agora_ms,
        "origem": "automus",
        "hashAntes": hash_banco_antes,
        "dados": banco,
    }
    backup_remote_payload = {
        "salvoEm": agora_ms,
        "origem": "automus",
        "hashAntes": hash_banco_antes,
        "backupLocal": str(backup_local_path) if "backup_local_path" in locals() else "",
        "dadosQuantidade": len(dados_anteriores),
        "dadosMortosQuantidade": len(dados_mortos),
        "tamanhoBackupLocalBytes": 0,
    }

    backup_local_path = _write_local_backup(project_root, backup_payload, agora_ms, log)
    backup_remote_payload["backupLocal"] = str(backup_local_path)
    backup_remote_payload["tamanhoBackupLocalBytes"] = backup_local_path.stat().st_size

    backup_remoto_ok = False
    try:
        log.info("AUTOMUS: gravando indice remoto do backup de seguranca.")
        _http_json(backup_url, method="PUT", payload=backup_remote_payload)
        backup_check = _http_json(backup_url, method="GET")
        if not isinstance(backup_check, dict):
            raise RuntimeError("NAO CONFORME: indice remoto do backup nao pode ser conferido.")
        if backup_check.get("salvoEm") != agora_ms or backup_check.get("hashAntes") != hash_banco_antes:
            raise RuntimeError("NAO CONFORME: indice remoto do backup gravou dados divergentes.")
        log.info(
            "BACKUP_REMOTO_INDICE_OK | salvoEm=%s | hashAntes=%s",
            backup_check.get("salvoEm"),
            backup_check.get("hashAntes"),
        )
        backup_remoto_ok = True
    except Exception as exc:
        log.warning(
            "BACKUP_REMOTO_INDISPONIVEL | mantendo backup local como fonte de rollback | motivo=%s",
            exc,
        )

    log.info(
        "BACKUP_GARANTIA_OK | local=%s | remoto=%s",
        backup_local_path,
        "OK" if backup_remoto_ok else "NAO",
    )

    payload = _sanitize_json_value(payload)
    _json_payload(payload)

    log.info("AUTOMUS: enviando atualizacao final para estoqueGlobal em blocos.")
    blocos = [
        ("dados", novos_dados),
        ("dadosMortos", dados_mortos),
        ("ajustesItens", ajustes_itens),
        ("historicoSaldo", historico_saldo),
        ("pedidosCompra", pedidos_compra),
        ("mapeamentoArquivos", payload["mapeamentoArquivos"]),
        ("automus", payload["automus"]),
    ]
    for nome_bloco, bloco in blocos:
        bloco_url = f"{db_url}/estoqueGlobal/{nome_bloco}.json{token_qs}"
        tamanho = len(_json_payload(bloco).encode("utf-8"))
        log.info("AUTOMUS: enviando bloco %s | bytes=%s", nome_bloco, tamanho)
        _http_json(bloco_url, method="PUT", payload=bloco)

    meta_payload = {
        "ultimaAtualizacao": agora_ms,
        "atualizadoPor": updated_by,
        "atualizacaoAutomatica": True,
        "ultimaAtualizacaoAutomatica": agora_ms,
    }
    _http_json(estoque_url, method="PATCH", payload=meta_payload)
    log.info("TEST_FIREBASE_PATCH_OK")

    check = _http_json(estoque_url, method="GET")
    if not isinstance(check, dict):
        raise RuntimeError("NAO CONFORME: leitura de conferencia pos-escrita retornou formato invalido.")

    ultima = check.get("ultimaAtualizacao")
    dados_pos = check.get("dados") if isinstance(check.get("dados"), list) else []
    auto_flag = bool(check.get("atualizacaoAutomatica"))

    if ultima != agora_ms:
        raise RuntimeError("AUTOMUS: atualizacao enviada, mas conferencia final nao confirmou timestamp.")
    if len(dados_pos) != len(novos_dados):
        raise RuntimeError("NAO CONFORME: quantidade de itens no banco diverge da carga enviada.")
    if not auto_flag:
        raise RuntimeError("NAO CONFORME: flag de atualizacao automatica nao foi persistida.")

    log.info(
        "TEST_FIREBASE_CONSISTENCIA_OK | itensBanco=%s | atualizacaoAutomatica=%s",
        len(dados_pos),
        auto_flag,
    )
    log.info(
        "AUTO_UPDATE_FIREBASE_OK | usuario=%s | itens=%s | ultimaAtualizacao=%s",
        safe_email,
        len(novos_dados),
        agora_ms,
    )


def _setup_cli_logger() -> logging.Logger:
    logger = logging.getLogger("automus_update_cli")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(h)
    return logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Automus: atualiza o estoqueGlobal no Firebase sem usar navegador.")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).resolve().parent / "automus_config.json"),
        help="Caminho do JSON com email/password.",
    )
    parser.add_argument(
        "--project-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Raiz do projeto (onde esta o index.html e pasta downloads).",
    )
    args = parser.parse_args()

    log = _setup_cli_logger()
    run_automus_update(Path(args.config), Path(args.project_root), logger=log)


if __name__ == "__main__":
    main()
