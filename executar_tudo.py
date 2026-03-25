import importlib.util
import logging
import time
from pathlib import Path

import msvcrt
from macro_controls import StopRequested


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


class ExecutionController:
    def __init__(self):
        self.paused = False
        self.stop_requested = False

    def poll_keypress(self, logger: logging.Logger):
        if not msvcrt.kbhit():
            return
        key = msvcrt.getch()
        if not key:
            return
        try:
            char = key.decode("utf-8").lower()
        except UnicodeDecodeError:
            return
        if char == "p":
            if not self.paused:
                self.paused = True
                logger.info("Pausado. Pressione R para retomar ou S para parar.")
        elif char == "r":
            if self.paused:
                self.paused = False
                logger.info("Retomado.")
        elif char == "s":
            if not self.stop_requested:
                self.stop_requested = True
                logger.warning("Parada solicitada. Encerrando apos a etapa atual.")

    def wait_if_paused(self, logger: logging.Logger):
        while self.paused and not self.stop_requested:
            self.poll_keypress(logger)
            time.sleep(0.1)


def configurar_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("executar_tudo")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def main():
    base = Path(__file__).resolve().parent
    macros = [ base / "macro_004.py",base /"macro_001.py", base / base / "macro_002.py", base / "macro_003.py"]
    logger = configurar_logger(base / "executar_tudo.log")
    controller = ExecutionController()
    logger.info("Automacao iniciada. Controles: F8 pausa, F9 retoma, F10 para (P/R/S no console).")
    for macro in macros:
        controller.poll_keypress(logger)
        if controller.stop_requested:
            logger.warning("Execucao interrompida antes da proxima etapa.")
            break
        controller.wait_if_paused(logger)
        if controller.stop_requested:
            logger.warning("Execucao interrompida antes da proxima etapa.")
            break
        if not macro.exists():
            raise FileNotFoundError(f"Nao encontrei {macro}")
        logger.info("Iniciando etapa: %s", macro.name)
        try:
            executar_macro(macro)
        except StopRequested as exc:
            controller.stop_requested = True
            logger.warning("Parada solicitada durante %s: %s", macro.name, exc)
            break
        except Exception as exc:
            controller.stop_requested = True
            logger.error("Falha na etapa %s: %s", macro.name, exc)
            logger.error("Automacao encerrada com erro.")
            break
        else:
            logger.info("Etapa concluida com sucesso: %s", macro.name)

    if not controller.stop_requested:
        logger.info("Automacao finalizada com sucesso.")


if __name__ == "__main__":
    main()
