import argparse
import hashlib
import json
import logging
import re
import time
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


def _extract_firebase_config(index_html_path: Path) -> tuple[str, str]:
    html = index_html_path.read_text(encoding="utf-8", errors="replace")
    api_match = re.search(r'apiKey:\s*"([^"]+)"', html)
    db_match = re.search(r'databaseURL:\s*"([^"]+)"', html)
    if not api_match or not db_match:
        raise RuntimeError("Nao foi possivel extrair apiKey/databaseURL do index.html")
    return api_match.group(1), db_match.group(1).rstrip("/")


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


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _build_items(
    incluir: list[list[Any]],
    cooperat: list[list[Any]],
    saldo_atual: list[list[Any]],
    saldo_endereco: list[list[Any]],
    dados_anteriores: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    novos: list[dict[str, Any]] = []

    saldo_atual_idx: dict[str, float] = {}
    for row in saldo_atual[1:]:
        if len(row) < 5:
            continue
        cod = _safe_text(row[1])
        if cod:
            saldo_atual_idx[cod] = _num(row[4])

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

    for row in incluir[2:]:
        if len(row) < 3:
            continue

        protheus = _safe_text(row[1])
        cooperat_cod = _safe_text(row[0])
        descricao = _safe_text(row[2])
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

        novos.append(item)

    return novos


def _resolve_file(base_dir: Path, filename: str) -> Path:
    candidates = [
        base_dir / "downloads" / filename,
        Path.home() / "Desktop" / filename,
        Path.home() / "Downloads" / filename,
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c
    raise FileNotFoundError(f"Arquivo nao encontrado: {filename}")


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


def run_automus_update(config_path: Path, project_root: Path, logger: logging.Logger | None = None) -> None:
    log = logger or logging.getLogger("automus_update")

    if not config_path.exists():
        raise FileNotFoundError(
            f"Config do Automus nao encontrada em {config_path}. Crie com email e password."
        )

    cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    email = _safe_text(cfg.get("email"))
    password = _safe_text(cfg.get("password"))
    updated_by = _safe_text(cfg.get("updated_by")) or "atualizado automaticamente via Automus"

    if not email or not password:
        raise RuntimeError("Config invalida: preencha 'email' e 'password' em automus_config.json")
    log.info("TEST_AUTOMUS_CONFIG_OK | config=%s | email=%s", config_path, email)

    index_path = project_root / "index.html"
    api_key, db_url = _extract_firebase_config(index_path)

    incluir_path = _resolve_file(project_root, FILE_MAP["mata105"])
    saldo_atual_path = _resolve_file(project_root, FILE_MAP["mata225"])
    saldo_endereco_path = _resolve_file(project_root, FILE_MAP["mata226"])
    log.info(
        "TEST_PLANILHAS_RESOLVIDAS_OK | incluir=%s | saldoAtual=%s | saldoEndereco=%s",
        incluir_path,
        saldo_atual_path,
        saldo_endereco_path,
    )

    log.info("AUTOMUS: iniciando autenticacao Firebase para envio sem navegador.")
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

    id_token = str(auth_resp["idToken"])
    safe_email = _safe_text(auth_resp.get("email")) or email
    token_qs = f"?auth={id_token}"

    estoque_url = f"{db_url}/estoqueGlobal.json{token_qs}"
    snapshot = _http_json(estoque_url, method="GET")
    banco = snapshot if isinstance(snapshot, dict) else {}
    hash_banco_antes = _json_hash(banco)
    log.info("TEST_FIREBASE_LEITURA_OK | hashAntes=%s", hash_banco_antes)

    dados_anteriores = banco.get("dados") if isinstance(banco.get("dados"), list) else []
    dados_mortos = banco.get("dadosMortos") if isinstance(banco.get("dadosMortos"), list) else []

    incluir = _read_sheet(incluir_path)
    saldo_atual = _read_sheet(saldo_atual_path)
    saldo_endereco = _read_sheet(saldo_endereco_path)
    log.info(
        "TEST_PLANILHAS_LIDAS_OK | incluir_linhas=%s | saldoAtual_linhas=%s | saldoEndereco_linhas=%s",
        len(incluir),
        len(saldo_atual),
        len(saldo_endereco),
    )
    if len(incluir) < 3 or len(saldo_atual) < 2 or len(saldo_endereco) < 2:
        raise RuntimeError(
            "NAO CONFORME: uma ou mais planilhas estao vazias/incompletas para atualizacao."
        )

    novos_dados = _build_items(incluir, [], saldo_atual, saldo_endereco, dados_anteriores)
    if not novos_dados:
        raise RuntimeError("NAO CONFORME: geracao de itens resultou em 0 registros.")
    log.info("TEST_GERACAO_ITENS_OK | itensGerados=%s", len(novos_dados))

    agora_ms = int(time.time() * 1000)

    payload = {
        "dados": novos_dados,
        "dadosMortos": dados_mortos,
        "ultimaAtualizacao": agora_ms,
        "atualizadoPor": updated_by,
        "atualizacaoAutomatica": True,
        "ultimaAtualizacaoAutomatica": agora_ms,
        "mapeamentoArquivos": {
            "mata105": "incluir.xlsx",
            "mata225": "saldo.atual.xlsx",
            "mata226": "saldo.por.endereco.xlsx",
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
