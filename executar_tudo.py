import importlib.util
from pathlib import Path


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


def main():
    base = Path(__file__).resolve().parent
    macros = [base / "macro_004.py", base / "macro_001.py", base / "macro_002.py", base / "macro_003.py"]
    for macro in macros:
        if not macro.exists():
            raise FileNotFoundError(f"Nao encontrei {macro}")
        executar_macro(macro)


if __name__ == "__main__":
    main()
