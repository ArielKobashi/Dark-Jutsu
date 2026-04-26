import importlib.util
import logging
from pathlib import Path

from controladordeatualização import (
    ExecutionController,
    StopRequested,
    push_status,
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


def main():
    base = Path(__file__).resolve().parent
    macros = [
        base / "macro_002.py",
        base / "macro_004.py",
        base / "macro_001.py",
        base / "macro_003.py",
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

        validate_macro_comment_sequence(macro)
        logger.info("Iniciando etapa: %s", macro.name)

        try:
            executar_macro(macro)
        except StopRequested as exc:
            break
        except Exception as exc:
            logger.error("Falha na etapa %s: %s", macro.name, exc)
            logger.error("Automacao encerrada com erro.")
            break
        else:
            logger.info("Etapa concluida com sucesso: %s", macro.name)

    if not controller.stop_requested:
        logger.info("Automacao finalizada com sucesso.")


if __name__ == "__main__":
    main()
