import argparse
import importlib.util
import sys
import time
from pathlib import Path


def build_parser():
    parser = argparse.ArgumentParser(
        description="Executa entrar.protheus1.py e, em seguida, pesquisa 'baixar' no menu."
    )
    return parser


def load_entrar_module(entrar_path: Path):
    spec = importlib.util.spec_from_file_location("entrar_protheus1", entrar_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Falha ao carregar modulo: {entrar_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_entrar(entrar_module, extra_args: list[str]):
    entrar_args = entrar_module.parse_args(extra_args)
    return entrar_module.run_login(entrar_args)


def pesquisar_menu(page, termo: str = "baixar", timeout: int = 20) -> bool:
    end = time.time() + timeout
    selectors = [
        "wa-text-input[placeholder*='Pesquisar' i]",
        "wa-text-input[placeholder*='buscar' i]",
        "wa-text-input",
        "input[placeholder*='Pesquisar' i]",
        "input[placeholder*='buscar' i]",
        "input[type='search']",
        "input[type='text'][placeholder]",
    ]

    def _set_value_and_click(frame, sel: str, value: str) -> bool:
        # 1) tenta focar e digitar via teclado (melhor para webcomponents)
        try:
            loc = frame.locator(sel).first
            if loc.count() > 0:
                loc.click(timeout=1000)
                frame.keyboard.press("Control+A")
                frame.keyboard.type(value, delay=30)

                # tenta clicar no botao dentro do componente
                try:
                    btn = frame.locator(f"{sel} button.button-image").first
                    if btn.count() > 0:
                        btn.dispatch_event("mousedown")
                        btn.dispatch_event("mouseup")
                        btn.click()
                        return True
                except Exception:
                    pass
        except Exception:
            pass

        # 2) tenta via shadow DOM + botao
        try:
            clicked = frame.evaluate(
                """
                ({ selector, value }) => {
                  const host = document.querySelector(selector);
                  if (!host) return false;

                  if (host.tagName && host.tagName.toLowerCase() === 'wa-text-input') {
                    host.value = value;
                    host.setAttribute('value', value);
                    host.dispatchEvent(new Event('input', { bubbles: true }));
                    host.dispatchEvent(new Event('change', { bubbles: true }));
                    const input = host.shadowRoot && host.shadowRoot.querySelector('input');
                    if (input) {
                      input.focus();
                      input.value = value;
                      input.dispatchEvent(new Event('input', { bubbles: true }));
                      input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    const btn = host.querySelector('button.button-image') || host.querySelector('button');
                    if (btn) {
                      btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                      btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                      btn.click();
                      return true;
                    }
                  }

                  if (host.tagName && host.tagName.toLowerCase() === 'input') {
                    host.focus();
                    host.value = value;
                    host.dispatchEvent(new Event('input', { bubbles: true }));
                    host.dispatchEvent(new Event('change', { bubbles: true }));
                    const parent = host.parentElement;
                    if (parent) {
                      const btn = parent.querySelector("button.button-image, button, .po-icon-search, .po-input-icon, .po-icon");
                      if (btn) { btn.click(); return true; }
                    }
                  }

                  const direct = document.querySelector("button.button-image");
                  if (direct) {
                    direct.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    direct.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    direct.click();
                    return true;
                  }
                  return false;
                }
                """,
                {"selector": sel, "value": value},
            )
            if clicked:
                clique_via_macro()
                return True
            return False
        except Exception:
            return False

    while time.time() < end:
        for frame in page.frames:
            for sel in selectors:
                if _set_value_and_click(frame, sel, termo):
                    return True
        time.sleep(0.5)
    return False


def clique_via_macro():
    try:
        from pynput import mouse, keyboard  # type: ignore
    except Exception:
        print("pynput nao instalado. Instale com: pip install pynput")
        return

    events = [
        (1.799566000001505, "click", {"x": 174, "y": 444, "button": "left", "pressed": True}),
        (1.9356370999012142, "click", {"x": 174, "y": 444, "button": "left", "pressed": False}),
    ]

    def _parse_button(name):
        return getattr(mouse.Button, name, mouse.Button.left)

    m = mouse.Controller()
    k = keyboard.Controller()
    last = 0.0
    for t, kind, data in events:
        wait = t - last
        if wait > 0:
            time.sleep(wait)
        last = t
        if kind == "move":
            m.position = (data["x"], data["y"])
        elif kind == "click":
            m.position = (data["x"], data["y"])
            btn = _parse_button(data["button"])
            if data["pressed"]:
                m.press(btn)
            else:
                m.release(btn)
        elif kind == "scroll":
            m.position = (data["x"], data["y"])
            m.scroll(data["dx"], data["dy"])
        elif kind == "key_down":
            key = data.get("key")
            if key is not None:
                k.press(key)
        elif kind == "key_up":
            key = data.get("key")
            if key is not None:
                k.release(key)

def teclas_via_macro(setas_baixo: int, delay: float = 0.12):
    try:
        from pynput import keyboard  # type: ignore
    except Exception:
        print("pynput nao instalado. Instale com: pip install pynput")
        return

    k = keyboard.Controller()
    for _ in range(setas_baixo):
        k.press(keyboard.Key.down)
        k.release(keyboard.Key.down)
        time.sleep(delay)
    k.press(keyboard.Key.enter)
    k.release(keyboard.Key.enter)

def enter_via_playwright(page, delay: float = 0.1):
    page.keyboard.press("Enter")
    if delay > 0:
        time.sleep(delay)


def enter_via_playwright_com_foco(page, timeout: float = 5.0, delay: float = 0.1) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        for frame in page.frames:
            try:
                frame.evaluate(
                    """
                    () => {
                      const el = document.activeElement || document.body;
                      if (el && el.focus) el.focus();
                    }
                    """
                )
                frame.keyboard.press("Enter")
                if delay > 0:
                    time.sleep(delay)
                return True
            except Exception:
                continue
        time.sleep(0.2)
    return False


def enter_via_js(page, timeout: float = 5.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        for frame in page.frames:
            try:
                sent = frame.evaluate(
                    """
                    () => {
                      const el = document.activeElement || document.body;
                      if (el && el.focus) el.focus();
                      const down = new KeyboardEvent('keydown', {
                        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                      });
                      const up = new KeyboardEvent('keyup', {
                        key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                      });
                      const target = el || document;
                      target.dispatchEvent(down);
                      target.dispatchEvent(up);
                      return true;
                    }
                    """
                )
                if sent:
                    return True
            except Exception:
                continue
        time.sleep(0.2)
    return False


def setas_baixo_via_macro(setas_baixo: int, delay: float = 0.12):
    try:
        from pynput import keyboard  # type: ignore
    except Exception:
        print("pynput nao instalado. Instale com: pip install pynput")
        return

    k = keyboard.Controller()
    for _ in range(setas_baixo):
        k.press(keyboard.Key.down)
        k.release(keyboard.Key.down)
        time.sleep(delay)


def enter_via_macro():
    try:
        from pynput import keyboard  # type: ignore
    except Exception:
        print("pynput nao instalado. Instale com: pip install pynput")
        return

    k = keyboard.Controller()
    k.press(keyboard.Key.enter)
    k.release(keyboard.Key.enter)




def clicar_outras_acoes(page, timeout: int = 20) -> bool:



    end = time.time() + timeout
    selectors = [
        "wa-button#COMP4573",
        "wa-button[caption*='Outras' i]",
        "wa-button:has-text('Outras')",
        "button:has-text('Outras')",
    ]

    def _try_click(frame) -> bool:
        for sel in selectors:
            try:
                loc = frame.locator(sel).first
                if loc.count() > 0:
                    loc.scroll_into_view_if_needed(timeout=1000)
                    loc.click(timeout=1000)
                    return True
            except Exception:
                continue

        try:
            clicked = frame.evaluate(
                """
                () => {
                  const normalize = (s) => (s || "")
                    .toLowerCase()
                    .normalize("NFD")
                    .replace(/\\p{Diacritic}/gu, "");

                  const target = "outras acoes";
                  const candidates = Array.from(document.querySelectorAll("wa-button, button"));
                  for (const el of candidates) {
                    const id = (el.getAttribute && el.getAttribute("id")) || "";
                    const caption = (el.getAttribute && el.getAttribute("caption")) || "";
                    const text = el.textContent || "";
                    const hay = normalize(`${id} ${caption} ${text}`);
                    if (id === "COMP4573" || hay.includes(target)) {
                      const btn = el.tagName.toLowerCase() === "button"
                        ? el
                        : (el.shadowRoot && el.shadowRoot.querySelector("button")) || el.querySelector("button");
                      if (btn) {
                        btn.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
                        btn.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
                        btn.click();
                        return true;
                      }
                    }
                  }
                  return false;
                }
                """
            )
            return bool(clicked)
        except Exception:
            return False

    while time.time() < end:
        for frame in page.frames:
            if _try_click(frame):
                return True
        time.sleep(0.5)
    return False


def clicar_botao_pesquisa_produto(page, timeout: int = 20) -> bool:
    end = time.time() + timeout
    selectors = [
        "wa-text-input#COMP6006 button.button-image",
        "wa-text-input#COMP6006 >> button.button-image",
    ]

    while time.time() < end:
        for frame in page.frames:
            for sel in selectors:
                try:
                    loc = frame.locator(sel).first
                    if loc.count() > 0:
                        loc.scroll_into_view_if_needed(timeout=1000)
                        loc.click(timeout=1000)
                        return True
                except Exception:
                    pass
            try:
                clicked = frame.evaluate(
                    """
                    () => {
                      const host = document.querySelector('wa-text-input#COMP6006');
                      if (!host) return false;
                      const btn =
                        host.querySelector('button.button-image') ||
                        (host.shadowRoot && host.shadowRoot.querySelector('button.button-image'));
                      if (btn) {
                        btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        btn.click();
                        return true;
                      }
                      return false;
                    }
                    """
                )
                if clicked:
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def manter_navegador_aberto():
    print("Navegador aberto. Para encerrar o script, use Ctrl+C.")
    while True:
        time.sleep(1)


def main() -> int:
    parser = build_parser()
    _, remaining = parser.parse_known_args()

    if remaining[:1] == ["--"]:
        remaining = remaining[1:]

    script_dir = Path(__file__).resolve().parent
    entrar_path = script_dir / "entrar.protheus1.py"
    if not entrar_path.exists():
        print(f"Nao encontrei {entrar_path}")
        return 1

    entrar_module = load_entrar_module(entrar_path)

    p = browser = None
    try:
        p, browser, context, page, ok, code = run_entrar(entrar_module, remaining)
        print(f"Login finalizado (ok={ok}).")
        if code != 0:
            return code

        time.sleep(2)
        print("Pesquisando 'baixar' no menu...")
        if not pesquisar_menu(page, "baixar", timeout=20):
            print("Nao consegui acionar a pesquisa.")
            return 2
        print("Pesquisa acionada.")

        print("Aguardando 8s para carregar...")
        time.sleep(8)
        if not enter_via_playwright_com_foco(page, timeout=5, delay=0.1):
            if not enter_via_js(page, timeout=5):
                print("Nao consegui enviar Enter via Playwright/JS.")
                return 5
        print("Enter enviado. Aguardando 8s...")
        time.sleep(8)

        manter_navegador_aberto()
        return 0
    finally:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
