import argparse
import importlib.util
import logging
import os
import re
import shutil
import time
from pathlib import Path

from atualizacao.automus_update import run_automus_update
from azul_encerradas import registrar_requisicoes_encerradas
from controladordeatualização import ExecutionController, StopRequested, push_status, validate_macro_comment_sequence


def carregar_macro(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Falha ao carregar {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def executar_macro(path: Path, func_name: str = "play"):
    mod = carregar_macro(path)
    if hasattr(mod, func_name):
        getattr(mod, func_name)()
    else:
        raise RuntimeError(f"{path.name} nao possui funcao {func_name}()")


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


def preparar_planilhas_para_importacao(
    logger: logging.Logger,
    base: Path,
    started_at_epoch: float,
    project_root: Path | None = None,
) -> dict[str, bool]:
    project_root = project_root or base.parent
    mapeamento = [
        ("mata105", "incluir.xlsx"),
        ("mata225", "Saldo Atual.xlsx"),
        ("mata226", "Saldo por Endereco.xlsx"),
        ("mata185", "mata185.xlsx"),
        ("estoque_minimo", "estoque_minimo.xlsx"),
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
            if codigo == "estoque_minimo":
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
            shutil.copy2(origem, destino)
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


def executar_macro_extra(
    logger: logging.Logger,
    macro: Path,
    func_name: str = "play",
    etapa_nome: str | None = None,
) -> None:
    if not macro.exists():
        raise FileNotFoundError(f"Nao encontrei {macro}")
    try:
        validate_macro_comment_sequence(macro)
    except RuntimeError as exc:
        logger.warning("Validacao de comentarios ignorada em %s: %s", macro.name, exc)
    nome = etapa_nome or macro.name
    logger.info("Iniciando etapa extra: %s", nome)
    executar_macro(macro, func_name=func_name)
    logger.info("Etapa extra concluida com sucesso: %s", nome)


def preparar_mata185_e_registrar_encerradas(
    logger: logging.Logger,
    base: Path,
    started_at_epoch: float | None,
    project_root: Path,
) -> None:
    mapa = preparar_planilhas_para_importacao(logger, base, started_at_epoch, project_root=project_root)
    if not mapa.get("mata185", False):
        raise RuntimeError("Validacao forte falhou: mata185.xlsx nova nao encontrada para verificar requisicoes encerradas.")
    registrar_requisicoes_encerradas(logger, base, project_root)


def executar_macro_012_com_verificador(
    logger: logging.Logger,
    base: Path,
    project_root: Path,
    started_at_epoch: float | None = None,
) -> None:
    macro = base / "macro_012.py"
    executar_macro_extra(
        logger,
        macro,
        func_name="play_pre",
        etapa_nome="macro_012.py antes do identificador",
    )
    preparar_mata185_e_registrar_encerradas(logger, base, started_at_epoch, project_root)
    executar_macro_extra(
        logger,
        macro,
        func_name="play_post",
        etapa_nome="macro_012.py depois do identificador",
    )


def main(macro_ref: str | None = None, automus_auth: dict | None = None, modo_atualizacao: str | None = None):
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
        "Somente planilhas mata105/mata225/mata226 com data/hora >= esse marco serao aceitas.",
        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at_epoch)),
    )
    logger.info(
        "Fluxo esperado: macros 003/004/005 salvam mata105/mata225/mata226; "
        "apos a macro 005, Automus envia direto ao Firebase (sem mexer na sessao aberta do Dark Jutsu)."
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
        if macro_ref and macro.name.lower() == "macro_012.py":
            try:
                logger.info(
                    "Iniciando macro_012 isolada com verificador de azuis e mata185.xlsx mais recente."
                )
                executar_macro_012_com_verificador(logger, base, project_root, started_at_epoch=None)
            except StopRequested as exc:
                logger.warning("Parada solicitada durante macro_012 isolada: %s", exc)
                break
            except Exception as exc:
                logger.exception("Falha na macro_012 isolada com verificador: %s", exc)
                logger.error("Automacao encerrada com erro.")
                failed = True
                break
            else:
                logger.info("Macro_012 isolada com verificador concluida com sucesso.")
                continue

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
                    mapa = preparar_planilhas_para_importacao(logger, base, started_at_epoch, project_root=project_root)
                    logger.info(
                        "CONFIRMACAO: preparo planilhas apos macro final | mata105=%s | mata225=%s | mata226=%s",
                        "OK" if mapa.get("mata105") else "FALHOU",
                        "OK" if mapa.get("mata225") else "FALHOU",
                        "OK" if mapa.get("mata226") else "FALHOU",
                    )
                    if not all(mapa.get(cod, False) for cod in ("mata105", "mata225", "mata226")):
                        raise RuntimeError(
                            "Validacao forte falhou: nem todas as planilhas novas da execucao atual foram encontradas."
                        )
                    logger.info(
                        "CONFIRMACAO: macro final de extracao concluida. Iniciando verificacao de requisicoes encerradas."
                    )
                    executar_macro_012_com_verificador(logger, base, project_root, started_at_epoch)
                    enviar_atualizacao_automus(logger, base, automus_auth=automus_auth, project_root=project_root)
                    logger.info(
                        "CONFIRMACAO: envio Firebase via Automus executado com requisicoes encerradas da MATA185."
                    )
                except Exception as exc:
                    logger.exception("Falha no pos-processamento apos macro_005: %s", exc)
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
