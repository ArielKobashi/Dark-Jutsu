import argparse
import argparse
import importlib.util
import logging
import os
import re
import shutil
import time
from pathlib import Path

from atualizacao.automus_update import run_automus_update
from controladordeatualização import (
    ExecutionController,
    StopRequested,
    handle_custom_event,
    push_status,
    sleep_with_controls,
    validate_macro_comment_sequence,
)


def carregar_macro(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Falha ao carregar {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def executar_macro(path: Path):
    mod = carregar_macro(path)
    if hasattr(mod, "play"):
        mod.play()
    else:
        raise RuntimeError(f"{path.name} nao possui funcao play()")


def preparar_transicao_macro(logger: logging.Logger, controller: ExecutionController, macro: Path):
    nome = macro.name.lower()
    if nome not in {"macro_007.py", "macro_008.py", "macro_009.py"}:
        return

    espera = 8.0 if nome == "macro_007.py" else 2.5
    logger.info("Preparando transicao para %s: aguardando %.1fs e refocando TOTVS.", macro.name, espera)
    if not sleep_with_controls(espera, controller):
        raise StopRequested(controller.get_stop_message())
    handle_custom_event(
        "focus_totvs_window",
        {
            "titles": ["TOTVS SmartClient HTML", "TOTVS Manufatura"],
            "timeout": 15,
            "interval": 0.2,
            "post_wait": 1.0,
            "error_on_timeout": False,
            "label": f"transicao {macro.name} foco TOTVS",
        },
        controller,
    )


class MacroPanelLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            push_status(self.format(record))
        except Exception:
            pass


def configurar_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("executar_tudo")
    if getattr(logger, "_macro_logger_configured", False):
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    panel_handler = MacroPanelLogHandler()
    panel_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.addHandler(panel_handler)
    logger._macro_logger_configured = True
    return logger


def _resolver_macro(base: Path, macro_ref: str) -> Path:
    macro_path = Path(macro_ref)
    if macro_path.suffix.lower() != ".py":
        macro_path = macro_path.with_suffix(".py")
    if not macro_path.is_absolute():
        macro_path = base / macro_path
    return macro_path


def _localizar_arquivo_mais_recente(
    pasta: Path,
    padrao: re.Pattern[str],
    started_at_epoch: float | None = None,
) -> Path | None:
    if not pasta.exists():
        return None
    candidatos = [p for p in pasta.iterdir() if p.is_file() and padrao.match(p.name)]
    if started_at_epoch is not None:
        candidatos = [p for p in candidatos if p.stat().st_mtime >= started_at_epoch]
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def _mesmo_arquivo(origem: Path, destino: Path) -> bool:
    try:
        return destino.exists() and os.path.samefile(origem, destino)
    except OSError:
        return False


def _copiar_planilha_com_retentativas(
    logger: logging.Logger,
    origem: Path,
    destino: Path,
    tentativas: int = 30,
    espera: float = 1.5,
) -> bool:
    if _mesmo_arquivo(origem, destino):
        return True

    destino.parent.mkdir(parents=True, exist_ok=True)
    ultimo_erro: Exception | None = None

    for tentativa in range(1, tentativas + 1):
        try:
            shutil.copy2(origem, destino)
            return True
        except PermissionError as exc:
            ultimo_erro = exc
        except OSError as exc:
            ultimo_erro = exc
            if getattr(exc, "winerror", None) not in {5, 32, 33}:
                raise

        if tentativa < tentativas:
            logger.info(
                "Planilha em uso, aguardando liberar: %s -> %s | tentativa %s/%s",
                origem,
                destino,
                tentativa,
                tentativas,
            )
            time.sleep(espera)

    logger.error("Falha ao copiar planilha apos tentativas: %s -> %s | erro=%s", origem, destino, ultimo_erro)
    return False


def preparar_planilhas_para_importacao(
    logger: logging.Logger,
    base: Path,
    started_at_epoch: float,
    project_root: Path | None = None,
    required_codes: tuple[str, ...] = ("mata105", "mata225", "mata226", "mata110", "mata111", "mata112"),
) -> dict[str, bool]:
    project_root = project_root or base.parent
    required = set(required_codes)
    mapeamento = [
        ("mata105", "incluir.xlsx"),
        ("mata225", "Saldo Atual.xlsx"),
        ("mata226", "Saldo por Endereco.xlsx"),
        ("estoque_minimo", "estoque_minimo.xlsx"),
        ("mata110", "mata110.xlsx"),
        ("mata111", "mata111.xlsx"),
        ("mata112", "mata112.xlsx"),
    ]

    pastas_origem = [
        project_root / "downloads",
        Path.home() / "Desktop" / "AMBIENTE ROSA",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
    ]
    pastas_destino = [
        p for p in [
            project_root / "downloads",
            Path.home() / "Desktop",
            Path.home() / "Downloads",
        ]
        if p.exists()
    ]
    resultado: dict[str, bool] = {}
    if not pastas_destino:
        logger.warning("Nenhuma pasta de destino encontrada para preparar as planilhas.")
        for codigo, _ in mapeamento:
            resultado[codigo] = False
        return resultado

    for codigo, nome_destino in mapeamento:
        padrao = re.compile(rf"^{re.escape(codigo)}(?:\s*\(\d+\))?\.xlsx$", re.IGNORECASE)
        origem = None
        for pasta in pastas_origem:
            origem = _localizar_arquivo_mais_recente(pasta, padrao, started_at_epoch=started_at_epoch)
            if origem is not None:
                break

        if origem is None:
            if codigo == "estoque_minimo" or codigo not in required:
                logger.info(
                    "Planilha opcional nao localizada para %s em %s.",
                    codigo,
                    ", ".join(str(p) for p in pastas_origem),
                )
            else:
                logger.error(
                    "NAO CONFORME: nao encontrei arquivo novo para %s (gerado apos inicio da execucao) em %s.",
                    codigo,
                    ", ".join(str(p) for p in pastas_origem),
                )
            resultado[codigo] = False
            continue

        for destino_base in pastas_destino:
            destino = destino_base / nome_destino
            copiado = _copiar_planilha_com_retentativas(logger, origem, destino)
            if not copiado:
                if destino_base == pastas_destino[0]:
                    raise PermissionError(f"Arquivo em uso: {origem} -> {destino}")
                logger.warning("Copia secundaria ignorada porque o arquivo esta em uso: %s", destino)
                continue
            logger.info(
                "Planilha preparada (nova): %s | mtime=%s -> %s",
                origem.name,
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(origem.stat().st_mtime)),
                destino,
            )
        resultado[codigo] = True

    return resultado

def enviar_atualizacao_automus(logger: logging.Logger, base: Path, automus_auth: dict | None = None, project_root: Path | None = None):
    config_path = base / "atualizacao" / "automus_config.json"
    project_root = project_root or Path(os.environ.get("AUTOMUS_PROJECT_ROOT") or base.parent)
    logger.info(
        "AUTOMUS: iniciando envio automatico ao Firebase sem interagir com navegador/sessao aberta."
    )
    run_automus_update(
        config_path=config_path,
        project_root=project_root,
        logger=logger,
        auth_id_token=(automus_auth or {}).get("idToken"),
        auth_email=(automus_auth or {}).get("email") or (automus_auth or {}).get("nickname"),
    )
    logger.info("AUTOMUS: envio concluido com sucesso.")


def preparar_e_enviar_etapa(
    logger: logging.Logger,
    base: Path,
    started_at_epoch: float,
    project_root: Path,
    automus_auth: dict | None,
    etapa: str,
    required_codes: tuple[str, ...],
) -> None:
    mapa = preparar_planilhas_para_importacao(
        logger,
        base,
        started_at_epoch,
        project_root=project_root,
        required_codes=required_codes,
    )
    logger.info(
        "CONFIRMACAO: preparo planilhas %s | mata105=%s | mata225=%s | mata226=%s | mata110=%s | mata111=%s | mata112=%s",
        etapa,
        "OK" if mapa.get("mata105") else "FALHOU",
        "OK" if mapa.get("mata225") else "FALHOU",
        "OK" if mapa.get("mata226") else "FALHOU",
        "OK" if mapa.get("mata110") else "FALHOU",
        "OK" if mapa.get("mata111") else "FALHOU",
        "OK" if mapa.get("mata112") else "FALHOU",
    )
    if not all(mapa.get(cod, False) for cod in required_codes):
        faltando = ", ".join(cod for cod in required_codes if not mapa.get(cod, False))
        raise RuntimeError(f"Validacao forte falhou na {etapa}: planilhas obrigatorias ausentes: {faltando}.")
    enviar_atualizacao_automus(logger, base, automus_auth=automus_auth, project_root=project_root)
    logger.info("CONFIRMACAO: envio Firebase via Automus concluido na %s.", etapa)

def main(macro_ref: str | None = None, automus_auth: dict | None = None):
    base = Path(os.environ.get("AUTOMUS_BUNDLED_SCRIPT_DIR") or Path(__file__).resolve().parent)
    project_root = Path(os.environ.get("AUTOMUS_PROJECT_ROOT") or base.parent)
    started_at_epoch = time.time()
    failed = False
    if macro_ref:
        macros = [_resolver_macro(base, macro_ref)]
    else:
        macros = [
            base / "macro_001.py",
            base / "macro_002.py",
            base / "macro_003.py",
            base / "macro_004.py",
            base / "macro_005.py",
            base / "macro_007.py",
            base / "macro_008.py",
            base / "macro_009.py",
        ]

    logger = configurar_logger(base / "executar_tudo.log")
    controller = ExecutionController()

    logger.info(
        "Automacao iniciada. Controles: F8 pausa, F9 retoma, F10 para "
        "(tambem P/R/S e botoes na janela). "
        "Identificador de pixel: ative no botao e use Espaco para capturar."
    )
    logger.info(
        "Marco temporal de validacao criado em: %s. "
        "Somente planilhas mata105/mata225/mata226/mata110/mata111/mata112 "
        "com data/hora >= esse marco serao aceitas.",
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at_epoch)),
    )
    logger.info(
        "Fluxo esperado: macros 003/004/005/007/008/009 salvam as planilhas; "
        "apos a macro 009, Automus envia direto ao Firebase (sem mexer na sessao aberta do sistema)."
    )

    for macro in macros:
        controller.poll_keypress()
        if controller.stop_requested:
            logger.warning(controller.get_stop_message())
            break

        controller.wait_if_paused()
        if controller.stop_requested:
            logger.warning(controller.get_stop_message())
            break

        if not macro.exists():
            raise FileNotFoundError(f"Nao encontrei {macro}")

        try:
            validate_macro_comment_sequence(macro)
        except RuntimeError as exc:
            logger.warning("Validacao de comentarios ignorada em %s: %s", macro.name, exc)
        preparar_transicao_macro(logger, controller, macro)
        logger.info("Iniciando etapa: %s", macro.name)

        try:
            executar_macro(macro)
        except StopRequested as exc:
            logger.warning("Parada solicitada durante %s: %s", macro.name, exc)
            break
        except Exception as exc:
            logger.exception("Falha na etapa %s: %s", macro.name, exc)
            logger.error("Automacao encerrada com erro.")
            failed = True
            break
        else:
            logger.info("Etapa concluida com sucesso: %s", macro.name)
            if macro.name.lower() == "macro_005.py":
                try:
                    logger.info(
                        "CONFIRMACAO: primeira parte concluida. Enviando mata105/mata225/mata226 ao Firebase antes de continuar."
                    )
                    preparar_e_enviar_etapa(
                        logger,
                        base,
                        started_at_epoch,
                        project_root,
                        automus_auth,
                        "primeira parte apos macro_005",
                        ("mata105", "mata225", "mata226"),
                    )
                    logger.info(
                        "CONFIRMACAO: primeira parte enviada. Continuando para macro_007/macro_008/macro_009."
                    )
                except Exception as exc:
                    logger.exception("Falha no envio da primeira parte apos macro_005: %s", exc)
                    logger.error("Automacao encerrada com erro.")
                    failed = True
                    break

            if macro.name.lower() == "macro_009.py":
                try:
                    logger.info(
                        "CONFIRMACAO: segunda parte concluida. Enviando pedido/compra/enderecamento ao Firebase."
                    )
                    preparar_e_enviar_etapa(
                        logger,
                        base,
                        started_at_epoch,
                        project_root,
                        automus_auth,
                        "segunda parte apos macro_009",
                        ("mata105", "mata225", "mata226", "mata110", "mata111", "mata112"),
                    )
                except Exception as exc:
                    logger.exception("Falha no envio da segunda parte apos macro_009: %s", exc)
                    logger.error("Automacao encerrada com erro.")
                    failed = True
                    break

    if not controller.stop_requested and not failed:
        logger.info("Automacao finalizada com sucesso.")
        return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executa a sequencia de macros ou uma macro isolada.")
    parser.add_argument("macro", nargs="?", help="Nome da macro para executar isoladamente, como macro_001.py.")
    args = parser.parse_args()
    main(args.macro)

