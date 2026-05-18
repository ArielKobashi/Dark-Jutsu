import argparse
import importlib.util
import logging
import re
import shutil
from pathlib import Path

from controladordeatualização import ExecutionController, StopRequested, push_status, validate_macro_comment_sequence


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


def _localizar_arquivo_mais_recente(pasta: Path, padrao: re.Pattern[str]) -> Path | None:
    if not pasta.exists():
        return None
    candidatos = [p for p in pasta.iterdir() if p.is_file() and padrao.match(p.name)]
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def preparar_planilhas_para_importacao(logger: logging.Logger, base: Path):
    mapeamento = [
        ("mata105", "incluir.xlsx"),
        ("mata225", "Saldo Atual.xlsx"),
        ("mata226", "Saldo por Endereco.xlsx"),
    ]

    pastas_origem = [
        base.parent / "downloads",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
    ]
    pastas_destino = [p for p in pastas_origem if p.exists()]
    if not pastas_destino:
        logger.warning("Nenhuma pasta de destino encontrada para preparar as planilhas.")
        return

    for codigo, nome_destino in mapeamento:
        padrao = re.compile(rf"^{re.escape(codigo)}(?:\s*\(\d+\))?\.xlsx$", re.IGNORECASE)
        origem = None
        for pasta in pastas_origem:
            origem = _localizar_arquivo_mais_recente(pasta, padrao)
            if origem is not None:
                break

        if origem is None:
            logger.warning("Nao encontrei arquivo para %s em %s.", codigo, ", ".join(str(p) for p in pastas_origem))
            continue

        for destino_base in pastas_destino:
            destino = destino_base / nome_destino
            shutil.copy2(origem, destino)
            logger.info("Planilha preparada: %s -> %s", origem.name, destino)


def main(macro_ref: str | None = None):
    base = Path(__file__).resolve().parent
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
        logger.info("Iniciando etapa: %s", macro.name)

        try:
            executar_macro(macro)
        except StopRequested as exc:
            logger.warning("Parada solicitada durante %s: %s", macro.name, exc)
            break
        except Exception as exc:
            logger.error("Falha na etapa %s: %s", macro.name, exc)
            logger.error("Automacao encerrada com erro.")
            break
        else:
            logger.info("Etapa concluida com sucesso: %s", macro.name)
            if macro.name.lower() == "macro_003.py":
                preparar_planilhas_para_importacao(logger, base)

    if not controller.stop_requested:
        logger.info("Automacao finalizada com sucesso.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executa a sequencia de macros ou uma macro isolada.")
    parser.add_argument("macro", nargs="?", help="Nome da macro para executar isoladamente, como macro_001.py.")
    args = parser.parse_args()
    main(args.macro)
