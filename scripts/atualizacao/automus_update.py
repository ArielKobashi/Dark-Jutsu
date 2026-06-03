import argparse
import base64
import hashlib
import json
import logging
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

try:
    from atualizacao.automus_crypto import decrypt_config, read_json
except ModuleNotFoundError:
    from automus_crypto import decrypt_config, read_json

FILE_MAP = {
    "mata105": "incluir.xlsx",
    "mata225": "Saldo Atual.xlsx",
    "mata226": "Saldo por Endereco.xlsx",
    "estoque_minimo": "estoque_minimo.xlsx",
}


def _json_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _http_json(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any] | list[Any] | None:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
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


def _load_automus_config(config_path: Path, api_key: str, db_url: str) -> tuple[dict[str, Any], Path | None]:
    if config_path.exists():
        cfg = read_json(config_path)
        if cfg.get("format") == "automus-config-v1":
            return decrypt_config(cfg, api_key, db_url), config_path
        return cfg, config_path

    encrypted_path = config_path.with_name("automus_config.enc.json")
    if encrypted_path.exists():
        return decrypt_config(read_json(encrypted_path), api_key, db_url), encrypted_path

    return {}, None


def _read_sheet(path: Path) -> list[list[Any]]:
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb[wb.sheetnames[0]]
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
    invalid = {"sem endereco", "sem endereço", "nd", "n/d", "na", "n/a", "-", "--", "/", "/ /"}
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
    return {"media": media, "pico": max(saidas), "desvio": math.sqrt(variancia), "eventos": float(len(saidas))}


def _sugerir_limites_estoque(item: dict[str, Any], historico: dict[str, Any]) -> dict[str, Any] | None:
    consumo = _historico_consumo_stats(item, historico)
    saldo_atual = _optional_num(item.get("saldo")) or 0.0
    limites_cooperat = item.get("limitesCooperat") if isinstance(item.get("limitesCooperat"), dict) else {}
    saldo_anterior = _optional_num(limites_cooperat.get("saldoAnterior") if isinstance(limites_cooperat, dict) else None)
    consumo_entre_planilhas = max(0.0, (saldo_anterior or 0.0) - saldo_atual) if saldo_anterior is not None else 0.0
    media_pedido = 0.0
    minimo_por_compra = 0.0
    candidatos_consumo = [consumo["media"], consumo["pico"] * 0.65, consumo_entre_planilhas]
    candidatos_consumo = [v for v in candidatos_consumo if math.isfinite(v) and v > 0]
    candidatos = [*candidatos_consumo, minimo_por_compra]
    candidatos = [v for v in candidatos if math.isfinite(v) and v > 0]
    if not candidatos:
        return None
    demanda_base = max(candidatos)
    estoque_seguranca = max(consumo["desvio"], demanda_base * 0.35, consumo["pico"] * 0.25, minimo_por_compra)
    minimo_estimado = max(demanda_base + estoque_seguranca, minimo_por_compra) if candidatos_consumo else minimo_por_compra
    minimo = _ceil_positive(minimo_estimado)
    if minimo is None:
        return None
    lote = _ceil_positive(max(demanda_base * 1.5, minimo * 0.8)) or minimo
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
            "fontePrincipal": "consumo",
        },
    }


def _aplicar_sugestoes_estoque(itens: list[dict[str, Any]], historico: dict[str, Any]) -> None:
    for item in itens:
        if not isinstance(item, dict):
            continue
        if item.get("limitesOrigem") in {"manual", "cooperat"}:
            item.pop("sugestaoEstoque", None)
            continue
        sugestao = _sugerir_limites_estoque(item, historico)
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


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _ascii_lower(value: Any) -> str:
    txt = _safe_text(value).lower()
    if not txt:
        return ""
    normalized = unicodedata.normalize("NFKD", txt)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _code_key(value: Any) -> str:
    txt = _safe_text(value).replace(" ", "").lower()
    if not txt:
        return ""
    normalized_num = txt.replace(",", ".")
    if re.fullmatch(r"\d+(?:\.0+)?", normalized_num):
        return str(int(float(normalized_num)))
    return txt


def _looks_unit(value: Any) -> bool:
    return _ascii_lower(value).upper() in {"PC", "UN", "MT", "M", "KG", "CJ", "JG", "PAR", "RL", "CX"}


def _old_address_from_row(row: list[Any]) -> str:
    endereco_coluna_padrao = _safe_text(row[4] if len(row) > 4 else "")
    coluna_anterior = row[3] if len(row) > 3 else ""
    proxima_coluna = row[5] if len(row) > 5 else None
    if (
        _is_endereco_valido(endereco_coluna_padrao)
        and (_looks_unit(coluna_anterior) or _optional_num(proxima_coluna) is not None or "/" in endereco_coluna_padrao)
    ):
        return endereco_coluna_padrao

    endereco_separado = " ".join(
        _safe_text(row[index] if len(row) > index else "")
        for index in (3, 4, 5)
        if _safe_text(row[index] if len(row) > index else "")
    ).strip()
    if _is_endereco_valido(endereco_separado):
        return endereco_separado

    return endereco_coluna_padrao if _is_endereco_valido(endereco_coluna_padrao) else ""


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
        cod = _code_key(row[1])
        if cod:
            saldo_atual_idx[cod] = _num(row[5] if len(row) > 5 else row[4])

    end_antigo_idx: dict[str, str] = {}
    for row in list(cooperat[1:]) + list((estoque_minimo or [])[1:]):
        if not row:
            continue
        end = _old_address_from_row(row)
        if not _is_endereco_valido(end):
            continue
        for col in (0, 1):
            cod = _code_key(row[col] if len(row) > col else "")
            if cod and cod not in end_antigo_idx:
                end_antigo_idx[cod] = end

    enderecos_idx: dict[str, list[dict[str, Any]]] = {}
    for row in saldo_endereco[1:]:
        if len(row) < 9:
            continue
        cod = _code_key(row[1])
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
    prev_by_descricao: dict[str, dict[str, Any]] = {}
    for d in dados_anteriores:
        if not isinstance(d, dict):
            continue
        p = _code_key(d.get("protheus"))
        c = _code_key(d.get("cooperat"))
        desc = _ascii_lower(d.get("descricao"))
        if p and p not in prev_by_protheus:
            prev_by_protheus[p] = d
        if c and c not in prev_by_cooperat:
            prev_by_cooperat[c] = d
        if desc and desc not in prev_by_descricao:
            prev_by_descricao[desc] = d

    for row in incluir[2:]:
        if len(row) < 3:
            continue

        protheus = _safe_text(row[1])
        cooperat_cod = _safe_text(row[0])
        descricao = _safe_text(row[2])
        if not protheus:
            continue
        protheus_key = _code_key(protheus)
        cooperat_key = _code_key(cooperat_cod)

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

        if protheus_key in saldo_atual_idx:
            item["saldo"] = saldo_atual_idx[protheus_key]

        endereco_antigo = end_antigo_idx.get(cooperat_key) or end_antigo_idx.get(protheus_key)
        if endereco_antigo:
            item["enderecoPrincipal"] = endereco_antigo

        if not _is_endereco_valido(item["enderecoPrincipal"]):
            anterior = prev_by_protheus.get(protheus_key) or prev_by_cooperat.get(cooperat_key) or prev_by_descricao.get(_ascii_lower(descricao))
            if anterior and _is_endereco_valido(anterior.get("enderecoPrincipal")):
                item["enderecoPrincipal"] = _safe_text(anterior.get("enderecoPrincipal"))

        enderecos = enderecos_idx.get(protheus_key, [])
        if enderecos:
            item["enderecos"] = enderecos
            validos = [e for e in enderecos if _is_endereco_valido(e.get("endereco"))]
            if validos:
                item["enderecoPrincipal"] = _safe_text(validos[-1].get("endereco"))
                item["armazemPrincipal"] = _safe_text(validos[-1].get("armazem")) or "ND"
            item["saldo"] = sum(_num(e.get("saldo")) for e in enderecos)

        anterior = prev_by_protheus.get(protheus_key) or prev_by_cooperat.get(cooperat_key) or prev_by_descricao.get(_ascii_lower(descricao))
        if anterior and isinstance(anterior.get("enderecos"), list):
            chaves_atuais = {
                (_ascii_lower(e.get("endereco")), _ascii_lower(e.get("armazem")))
                for e in item["enderecos"]
                if isinstance(e, dict)
            }
            for end_antigo in anterior["enderecos"]:
                if not isinstance(end_antigo, dict) or not _is_endereco_valido(end_antigo.get("endereco")):
                    continue
                chave = (_ascii_lower(end_antigo.get("endereco")), _ascii_lower(end_antigo.get("armazem")))
                if chave in chaves_atuais:
                    continue
                item["enderecos"].append({
                    "endereco": _safe_text(end_antigo.get("endereco")),
                    "armazem": _safe_text(end_antigo.get("armazem")) or "ND",
                    "saldo": 0.0,
                    "origem": "Historico",
                })
                chaves_atuais.add(chave)

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
            if estoque_minimo_item.get("reposicao") is not None:
                item["reposicao"] = estoque_minimo_item["reposicao"]
                item["reposicaoOrigem"] = "cooperat"
            if tem_limite_planilha:
                item["limitesOrigem"] = "cooperat"

        anterior = prev_by_protheus.get(protheus_key) or prev_by_cooperat.get(cooperat_key) or prev_by_descricao.get(_ascii_lower(descricao))
        if anterior:
            if item.get("minimo") is None and anterior.get("minimo") is not None:
                item["minimo"] = anterior.get("minimo")
            if item.get("maximo") is None and anterior.get("maximo") is not None:
                item["maximo"] = anterior.get("maximo")

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
        base_dir / "data" / filename,
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
        base_dir / "data" / filename,
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
        json.dumps(backup_payload, ensure_ascii=False, indent=2),
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

    index_path = project_root / "index.html"
    api_key, db_url = _extract_firebase_config(index_path)
    cfg, resolved_config_path = _load_automus_config(config_path, api_key, db_url)
    if not resolved_config_path and not auth_id_token:
        raise FileNotFoundError(
            f"Config do Automus nao encontrada em {config_path}. Crie automus_config.json ou automus_config.enc.json."
        )

    email = _safe_text(cfg.get("email"))
    password = _safe_text(cfg.get("password"))
    updated_by = _safe_text(cfg.get("updated_by")) or "atualizado automaticamente via Automus"

    if not auth_id_token and (not email or not password):
        raise RuntimeError("Config invalida: preencha 'email' e 'password' em automus_config.json")
    log.info("TEST_AUTOMUS_CONFIG_OK | config=%s | email=%s", resolved_config_path or config_path, auth_email or email)

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
        dados_anteriores + dados_mortos,
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
    _aplicar_sugestoes_estoque(novos_dados, historico_saldo)

    payload = {
        "dados": novos_dados,
        "dadosMortos": dados_mortos,
        "ajustesItens": ajustes_itens,
        "historicoSaldo": historico_saldo,
        "ultimaAtualizacao": agora_ms,
        "atualizadoPor": updated_by,
        "atualizacaoAutomatica": True,
        "ultimaAtualizacaoAutomatica": agora_ms,
        "mapeamentoArquivos": {
            "mata105": "incluir.xlsx",
            "mata225": "saldo.atual.xlsx",
            "mata226": "saldo.por.endereco.xlsx",
            **({"estoque_minimo": "estoque_minimo.xlsx"} if estoque_minimo_path else {}),
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

    backup_local_path = _write_local_backup(project_root, backup_payload, agora_ms, log)

    backup_remoto_ok = False
    try:
        log.info("AUTOMUS: gravando backup remoto de seguranca antes da atualizacao.")
        _http_json(backup_url, method="PUT", payload=backup_payload)
        backup_check = _http_json(backup_url, method="GET")
        if not isinstance(backup_check, dict):
            raise RuntimeError("NAO CONFORME: backup remoto nao pode ser conferido.")
        if backup_check.get("salvoEm") != agora_ms or backup_check.get("hashAntes") != hash_banco_antes:
            raise RuntimeError("NAO CONFORME: backup remoto gravou dados divergentes.")
        log.info(
            "BACKUP_REMOTO_OK | salvoEm=%s | hashAntes=%s",
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

    log.info("AUTOMUS: enviando atualizacao final para estoqueGlobal.")
    _http_json(estoque_url, method="PATCH", payload=payload)
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
