import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


DEFAULT_URL = "https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/index.html"
LOGIN_SELECTORS = "input[name='login'], input[id^='po-login']"
PASS_SELECTORS = "input[name='password'], input[id^='po-password']"


def find_login_frame(page):
    for frame in page.frames:
        try:
            if frame.query_selector(LOGIN_SELECTORS):
                return frame
        except Exception:
            pass
    return None


def has_login_fields(page) -> bool:
    return find_login_frame(page) is not None


def attempt_login(page, user: str, senha: str, timeout: int = 60) -> bool:
    end = time.time() + timeout
    submitted = False
    while time.time() < end:
        frame = find_login_frame(page)
        if frame:
            try:
                frame.fill(LOGIN_SELECTORS, user)
                frame.fill(PASS_SELECTORS, senha)
                frame.press(PASS_SELECTORS, "Enter")
                submitted = True
            except Exception:
                pass
        if submitted and not has_login_fields(page):
            return True
        time.sleep(0.5)
    return False


def click_entrar_button(page, timeout: int = 10) -> bool:
    try:
        page.locator("button.po-button:has-text('Entrar')").first.click(timeout=timeout * 1000)
        return True
    except Exception:
        pass
    try:
        page.locator("po-button.session-settings-button-enter button.po-button").click(timeout=timeout * 1000)
        return True
    except Exception:
        pass
    try:
        page.locator("po-button.session-settings-button-enter").click(timeout=timeout * 1000)
        return True
    except Exception:
        pass
    try:
        page.locator("span.po-button-label:has-text('Entrar')").click(timeout=timeout * 1000)
        return True
    except Exception:
        pass

    # tenta em todos os iframes
    for frame in page.frames:
        try:
            frame.locator("button.po-button:has-text('Entrar')").first.click(timeout=timeout * 1000)
            return True
        except Exception:
            pass
        try:
            frame.locator("po-button.session-settings-button-enter button.po-button").click(timeout=timeout * 1000)
            return True
        except Exception:
            pass
        try:
            frame.locator("po-button.session-settings-button-enter").click(timeout=timeout * 1000)
            return True
        except Exception:
            pass
        try:
            frame.locator("span.po-button-label:has-text('Entrar')").click(timeout=timeout * 1000)
            return True
        except Exception:
            pass

    # fallback: varre shadow DOM procurando botão "Entrar"
    try:
        clicked = page.evaluate(
            """
            () => {
              function clickEntrar(root){
                const buttons = Array.from(root.querySelectorAll("button, po-button, span.po-button-label"));
                for(const el of buttons){
                  const text = (el.textContent || '').trim().toLowerCase();
                  if(text === 'entrar'){
                    if(el.tagName === 'SPAN' && el.closest('button')){ el.closest('button').click(); return true; }
                    if(el.tagName === 'PO-BUTTON' && el.shadowRoot){
                      const inner = el.shadowRoot.querySelector('button');
                      if(inner){ inner.click(); return true; }
                    }
                    el.click();
                    return true;
                  }
                }
                const all = Array.from(root.querySelectorAll("*"));
                for(const el of all){
                  if(el.shadowRoot){
                    const ok = clickEntrar(el.shadowRoot);
                    if(ok) return true;
                  }
                }
                return false;
              }
              if(clickEntrar(document)) return true;
              const frames = Array.from(document.querySelectorAll('iframe'));
              for(const f of frames){
                try{
                  if(f.contentDocument && clickEntrar(f.contentDocument)) return true;
                }catch(e){}
              }
              return false;
            }
            """
        )
        return bool(clicked)
    except Exception:
        return False


def selecionar_env_rapido(page, env_value: str = "fiasul_prod", timeout: int = 30) -> bool:
    end = time.time() + timeout
    try:
        # Garante foco no mesmo "body" usando o slot com tabindex=-1 (quando existir)
        clicked = page.evaluate(
            """
            () => {
              const slot = document.querySelector("slot[tabindex='-1']");
              if(slot){ slot.click(); return true; }
              return false;
            }
            """
        )
        if not clicked:
            page.click("body", timeout=5000)
    except Exception:
        pass
    while time.time() < end:
        try:
            # Tenta selecionar no DOM profundo (inclui shadow DOM)
            selected = page.evaluate(
                """
                (val) => {
                  function matchesOption(opt, v){
                    const txt = (opt.textContent || '').trim().toLowerCase();
                    const value = (opt.value || '').trim().toLowerCase();
                    return txt === v || value === v;
                  }
                  function findSelect(root, v){
                    const sels = Array.from(root.querySelectorAll("select"));
                    for(const sel of sels){
                      const opts = Array.from(sel.options || []);
                      if(opts.some(o => matchesOption(o, v))) return sel;
                    }
                    const all = Array.from(root.querySelectorAll("*"));
                    for(const el of all){
                      if(el.shadowRoot){
                        const found = findSelect(el.shadowRoot, v);
                        if(found) return found;
                      }
                    }
                    return null;
                  }
                  const v = (val || '').toLowerCase();
                  const sel = findSelect(document, v);
                  if(!sel) return false;
                  const opts = Array.from(sel.options || []);
                  const target = opts.find(o => matchesOption(o, v));
                  if(!target) return false;
                  sel.value = target.value;
                  target.selected = true;
                  sel.dispatchEvent(new Event('input', { bubbles:true }));
                  sel.dispatchEvent(new Event('change', { bubbles:true }));
                  return true;
                }
                """,
                env_value.lower()
            )
            if selected:
                page.keyboard.press("Tab")
                page.keyboard.press("Tab")
                page.keyboard.press("Enter")
                return True

            # Fallback: TAB + digitar + ENTER
            page.keyboard.press("Tab")
            page.keyboard.press("Tab")
            page.keyboard.type(env_value, delay=25)
            page.keyboard.press("Enter")
            return True
        except Exception:
            time.sleep(0.5)
    return False


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Login Protheus com Playwright")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL do Protheus")
    parser.add_argument("--headless", action="store_true", help="Rodar em modo headless")
    parser.add_argument("--manual", action="store_true", help="Login manual")
    parser.add_argument("--user", default="davi.souza", help="UsuÃ¡rio do Protheus (override)")
    parser.add_argument("--password", default="pudimA1?", help="Senha do Protheus (override)")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout do login (s)")
    parser.add_argument("--env", default="fiasul_prod", help="Ambiente (primeira tela)")
    return parser.parse_args(argv)

def run_login(args):
    user = (args.user or os.getenv("PROTHEUS_USER", "")).strip()
    senha = (args.password or os.getenv("PROTHEUS_PASS", "")).strip()
    if args.manual:
        user = ""
        senha = ""

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=args.headless)
    context = browser.new_context()
    page = context.new_page()

    print("Abrindo Protheus...")
    page.goto(args.url, wait_until="domcontentloaded")

    time.sleep(5)
    print("Primeira tela: selecionando ambiente via TAB + texto + ENTER...")
    selecionar_env_rapido(page, args.env, timeout=30)
    time.sleep(2)

    if args.manual:
        print("Login manual: faÃ§a o login e aguarde 30s.")
        time.sleep(30)
        return p, browser, context, page, True, 0

    if not user or not senha:
        print("UsuÃ¡rio/senha nÃ£o definidos. Use PROTHEUS_USER/PROTHEUS_PASS ou --manual.")
        return p, browser, context, page, False, 1

    print("Tentando login automÃ¡tico...")
    ok = attempt_login(page, user, senha, timeout=args.timeout)
    if ok:
        print("Login concluÃ­do. Aguardando 10s para carregar a prÃ³xima tela...")
        time.sleep(10)
        try:
            page.click("body", timeout=5000)
        except Exception:
            pass
        print("Enviando 12x TAB e ENTER...")
        for _ in range(6):
            page.keyboard.press("Tab")
            time.sleep(0.25)
        page.keyboard.press("Enter")
    else:
        print("NÃ£o consegui confirmar o login dentro do tempo.")

    time.sleep(3)
    return p, browser, context, page, ok, 0


def main():
    args = parse_args()

    p = browser = None
    try:
        p, browser, _context, _page, _ok, code = run_login(args)
        if code != 0:
            return code
        return 0
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if p:
                p.stop()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
