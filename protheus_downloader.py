import argparse
import os
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchWindowException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager


DEFAULT_BASE_URL = "https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/index.html"
DEFAULT_LINKS = [
    "https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/mata105.xlsx?download=1",
    "https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/mata225.xlsx?download=1",
    "https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/mata226.xlsx?download=1",
]


def build_driver(download_dir: Path, headless: bool) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument("--start-maximized")

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options,
    )


def wait_clickable(wait: WebDriverWait, xpath: str, timeout: int = 20):
    return wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))


def try_click(wait: WebDriverWait, xpath: str, label: str) -> bool:
    try:
        wait_clickable(wait, xpath).click()
        print(label)
        return True
    except Exception:
        return False


def try_click_shadow_button(driver: webdriver.Chrome, selector: str, label: str) -> bool:
    try:
        clicked = driver.execute_script(
            """
            const host = document.querySelector(arguments[0]);
            if(!host || !host.shadowRoot) return false;
            const btn = host.shadowRoot.querySelector('button');
            if(!btn) return false;
            btn.click();
            return true;
            """,
            selector,
        )
        if clicked:
            print(label)
        return bool(clicked)
    except Exception:
        return False


def click_ok_anywhere(driver: webdriver.Chrome, timeout: int = 25) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        # 1) tentativa simples via Selenium
        try:
            btn = driver.find_element(
                By.XPATH,
                "//button[normalize-space()='OK' or normalize-space()='Ok']"
                " | //input[@type='button' and (translate(@value,'ok','OK')='OK')]"
                " | //input[@type='submit' and (translate(@value,'ok','OK')='OK')]",
            )
            if btn.is_enabled():
                btn.click()
                print("SmartClient confirmado")
                return True
        except Exception:
            pass

        # 2) tentativa via JS (DOM + iframes + shadow)
        try:
            clicked = driver.execute_script(
                """
                function clickWaButtonOk(root){
                    const host = root.querySelector("wa-dialog.startParameters wa-button[part='btn-ok']") ||
                                 root.querySelector("wa-button[part='btn-ok']");
                    if(host){
                        const inner = host.shadowRoot ? host.shadowRoot.querySelector("button") : null;
                        if(inner){ inner.click(); return true; }
                        host.click(); return true;
                    }
                    const all = Array.from(root.querySelectorAll("wa-button"));
                    for(const el of all){
                        const caption = (el.getAttribute('caption') || '').trim().toLowerCase();
                        if(caption === 'ok'){
                            const inner2 = el.shadowRoot ? el.shadowRoot.querySelector("button") : null;
                            if(inner2){ inner2.click(); return true; }
                            el.click(); return true;
                        }
                    }
                    return false;
                }
                function clickOkInDoc(doc){
                    if(clickWaButtonOk(doc)) return true;
                    const nodes = Array.from(doc.querySelectorAll("button, input[type='button'], input[type='submit']"));
                    for(const el of nodes){
                        const text = (el.textContent || el.value || el.getAttribute('caption') || '').trim().toLowerCase();
                        if(text === 'ok'){
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }
                const docs = [document];
                const frames = Array.from(document.querySelectorAll('iframe'));
                for(const f of frames){
                    try{
                        if(f.contentDocument) docs.push(f.contentDocument);
                    }catch(e){}
                }
                for(const d of docs){
                    try{
                        if(clickOkInDoc(d)) return true;
                    }catch(e){}
                }
                return false;
                """
            )
            if clicked:
                print("SmartClient confirmado")
                return True
        except Exception:
            pass

        time.sleep(0.5)
    return False


def click_ok_by_mouse(driver: webdriver.Chrome) -> bool:
    try:
        host = driver.find_element(By.CSS_SELECTOR, "wa-dialog.startParameters wa-button[part='btn-ok']")
        size = host.size or {"width": 1, "height": 1}
        actions = ActionChains(driver)
        actions.move_to_element_with_offset(host, size["width"] / 2, size["height"] / 2).click().perform()
        print("SmartClient confirmado")
        return True
    except Exception:
        return False


def click_ok_dispatch(driver: webdriver.Chrome) -> bool:
    try:
        clicked = driver.execute_script(
            """
            const host = document.querySelector("wa-dialog.startParameters wa-button[part='btn-ok']")
                || document.querySelector("wa-button[part='btn-ok']");
            if(!host) return false;
            const btn = host.shadowRoot ? host.shadowRoot.querySelector("button") : host;
            const r = btn.getBoundingClientRect();
            const x = r.left + r.width/2;
            const y = r.top + r.height/2;
            const target = document.elementFromPoint(x, y) || btn;
            ['pointerdown','mousedown','pointerup','mouseup','click'].forEach(type=>{
                target.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}));
            });
            return true;
            """
        )
        if clicked:
            print("SmartClient confirmado")
        return bool(clicked)
    except Exception:
        return False


def is_ok_disabled(driver: webdriver.Chrome) -> bool:
    try:
        return bool(driver.execute_script(
            """
            const host = document.querySelector("wa-dialog.startParameters wa-button[part='btn-ok']")
                || document.querySelector("wa-button[part='btn-ok']");
            if(!host) return true;
            const btn = host.shadowRoot ? host.shadowRoot.querySelector("button") : host;
            const disabledAttr = host.hasAttribute('disabled') || (btn && btn.hasAttribute('disabled'));
            return (!!btn && !!btn.disabled) || disabledAttr;
            """
        ))
    except Exception:
        return True


def debug_ok_state(driver: webdriver.Chrome):
    try:
        info = driver.execute_script(
            """
            const host = document.querySelector("wa-dialog.startParameters wa-button[part='btn-ok']")
                || document.querySelector("wa-button[part='btn-ok']");
            const btn = host && host.shadowRoot ? host.shadowRoot.querySelector("button") : host;
            return {
                hasHost: !!host,
                hostDisabled: host ? host.hasAttribute('disabled') : null,
                btnDisabled: btn ? btn.disabled : null,
                btnText: btn ? (btn.textContent || '').trim() : null
            };
            """
        )
        print("DEBUG ok:", info)
    except Exception as e:
        print("DEBUG ok: erro ao inspecionar", e)


def debug_env_state(driver: webdriver.Chrome):
    try:
        info = driver.execute_script(
            """
            const env = document.querySelector("wa-combobox#selectEnv");
            const start = document.querySelector("wa-combobox#selectStartProg");
            function getInfo(combo){
                if(!combo || !combo.shadowRoot) return null;
                const select = combo.shadowRoot.querySelector("select");
                const input = combo.shadowRoot.querySelector("input[type='text']");
                return {
                    inputValue: input ? (input.value || '') : '',
                    selectValue: select ? (select.value || '') : '',
                    options: select ? (select.options || []).length : 0
                };
            }
            return { env: getInfo(env), start: getInfo(start) };
            """
        )
        print("DEBUG env/start:", info)
    except Exception as e:
        print("DEBUG env/start: erro", e)


def wait_ok_enabled(driver: webdriver.Chrome, timeout: int = 10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if not is_ok_disabled(driver):
            return True
        time.sleep(0.2)
    return False


def wait_dialog_closed(driver: webdriver.Chrome, timeout: int = 15) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            open_dialog = driver.execute_script(
                "return !!document.querySelector('wa-dialog.startParameters');"
            )
            if not open_dialog:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def click_ok_strict(driver: webdriver.Chrome) -> bool:
    # tenta vários métodos até clicar de fato
    try:
        host = driver.find_element(By.CSS_SELECTOR, "wa-dialog.startParameters wa-button[part='btn-ok']")
        driver.execute_script("arguments[0].click();", host)
        return True
    except Exception:
        pass

    if wait_for_shadow_host(driver, "wa-button[part='btn-ok']", timeout=5):
        if try_click_shadow_button(driver, "wa-button[part='btn-ok']", "SmartClient confirmado"):
            return True

    if click_ok_by_mouse(driver):
        return True

    if click_ok_dispatch(driver):
        return True

    return False


def select_environment_first(driver: webdriver.Chrome):
    # Tenta selecionar o ambiente "fiasul_prod" no combo (wa-combobox)
    try:
        return bool(driver.execute_script(
            """
            const combo = document.querySelector("wa-combobox#selectEnv");
            if(!combo || !combo.shadowRoot) return false;
            const select = combo.shadowRoot.querySelector("select");
            const input = combo.shadowRoot.querySelector("input[type='text']");
            if(!select) return false;
            const opts = Array.from(select.options || []);
            let idx = opts.findIndex(o => (o.value || o.textContent || '').trim().toLowerCase() === 'fiasul_prod');
            if(idx < 0) idx = 1;
            const target = opts[idx] || opts[0];
            if(target){
                select.value = target.value;
                target.selected = true;
                select.selectedIndex = idx;
                combo.setAttribute('selectedindex', String(idx));
                combo.selectedIndex = idx;
                const desired = (target.value && target.value !== '-1')
                    ? target.value
                    : (target.textContent || '').trim() || 'fiasul_prod';
                combo.value = desired;
                combo.setAttribute('value', desired);
                select.dispatchEvent(new Event('change', { bubbles:true }));
                if(input){
                    input.value = desired;
                    input.dispatchEvent(new Event('input', { bubbles:true }));
                    input.dispatchEvent(new Event('change', { bubbles:true }));
                    input.dispatchEvent(new Event('blur', { bubbles:true }));
                }
                combo.dispatchEvent(new Event('change', { bubbles:true }));
                combo.dispatchEvent(new CustomEvent('wa-change', { bubbles:true, detail:{ value: desired }}));
                return true;
            }
            return false;
            """
        ))
    except Exception:
        return False


def wait_for_env_options(driver: webdriver.Chrome, timeout: int = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            ready = driver.execute_script(
                """
                const combo = document.querySelector("wa-combobox#selectEnv");
                if(!combo || !combo.shadowRoot) return false;
                const select = combo.shadowRoot.querySelector("select");
                return !!select && (select.options || []).length > 1;
                """
            )
            if ready:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def get_env_value(driver: webdriver.Chrome) -> str:
    try:
        return driver.execute_script(
            """
            const combo = document.querySelector("wa-combobox#selectEnv");
            if(!combo || !combo.shadowRoot) return '';
            const input = combo.shadowRoot.querySelector("input[type='text']");
            const select = combo.shadowRoot.querySelector("select");
            const v1 = input ? (input.value || '') : '';
            const v2 = select ? (select.value || '') : '';
            return (v1 || '').toString();
            """
        ) or ""
    except Exception:
        return ""


def get_startprog_value(driver: webdriver.Chrome) -> str:
    try:
        return driver.execute_script(
            """
            const combo = document.querySelector("wa-combobox#selectStartProg");
            if(!combo || !combo.shadowRoot) return '';
            const input = combo.shadowRoot.querySelector("input[type='text']");
            const v1 = input ? (input.value || '') : '';
            return (v1 || '').toString();
            """
        ) or ""
    except Exception:
        return ""


def select_startprog_exact(driver: webdriver.Chrome) -> bool:
    try:
        return bool(driver.execute_script(
            """
            const combo = document.querySelector("wa-combobox#selectStartProg");
            if(!combo || !combo.shadowRoot) return false;
            const select = combo.shadowRoot.querySelector("select");
            const input = combo.shadowRoot.querySelector("input[type='text']");
            if(!select) return false;
            const opts = Array.from(select.options || []);
            let target = opts.find(o => (o.value || o.textContent || '').trim().toLowerCase() === 'sigamdi');
            if(!target){
                // ignora a opção "-1" escondida se existir
                target = opts.find(o => (o.value || '').trim() !== '-1') || opts[0];
            }
            if(!target) return false;
            const desired = (target.value && target.value !== '-1')
                ? target.value
                : (target.textContent || '').trim() || 'SIGAMDI';
            select.value = target.value;
            target.selected = true;
            select.selectedIndex = opts.indexOf(target);
            combo.setAttribute('selectedindex', String(select.selectedIndex));
            combo.selectedIndex = select.selectedIndex;
            combo.value = desired;
            combo.setAttribute('value', desired);
            select.dispatchEvent(new Event('input', { bubbles:true }));
            select.dispatchEvent(new Event('change', { bubbles:true }));
            if(input){
                input.value = desired;
                input.dispatchEvent(new Event('input', { bubbles:true }));
                input.dispatchEvent(new Event('change', { bubbles:true }));
                input.dispatchEvent(new Event('blur', { bubbles:true }));
            }
            combo.dispatchEvent(new Event('input', { bubbles:true }));
            combo.dispatchEvent(new Event('change', { bubbles:true }));
            combo.dispatchEvent(new CustomEvent('wa-change', { bubbles:true, detail:{ value: desired }}));
            return true;
            """
        ))
    except Exception:
        return False


def ensure_startprog_selected(driver: webdriver.Chrome, timeout: int = 10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        select_startprog_exact(driver)
        val = (get_startprog_value(driver) or "").strip().lower()
        if "sigamdi" in val:
            return True
        time.sleep(0.3)
    return False


def press_tabs_enter(driver: webdriver.Chrome, tabs: int = 3) -> bool:
    try:
        # garante foco na página
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            ActionChains(driver).move_to_element(body).click().perform()
        except Exception:
            pass
        time.sleep(0.2)
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.2)
        for _ in range(max(1, tabs)):
            try:
                body = driver.find_element(By.TAG_NAME, "body")
                body.send_keys(Keys.TAB)
            except Exception:
                ActionChains(driver).send_keys(Keys.TAB).perform()
            time.sleep(0.2)
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.ENTER)
        except Exception:
            ActionChains(driver).send_keys(Keys.ENTER).perform()
        return True
    except Exception:
        return False


def wait_for_user_zero(prompt: str) -> bool:
    try:
        while True:
            val = input(prompt + " ").strip()
            if val == "0":
                return True
    except KeyboardInterrupt:
        return False


def select_environment_exact(driver: webdriver.Chrome) -> bool:
    try:
        return bool(driver.execute_script(
            """
            const combo = document.querySelector("wa-combobox#selectEnv");
            if(!combo || !combo.shadowRoot) return false;
            const select = combo.shadowRoot.querySelector("select");
            const input = combo.shadowRoot.querySelector("input[type='text']");
            if(!select) return false;
            const opts = Array.from(select.options || []);
            const target = opts.find(o => (o.value || o.textContent || '').trim().toLowerCase() === 'fiasul_prod');
            if(!target) return false;
            const desired = (target.value && target.value !== '-1')
                ? target.value
                : (target.textContent || '').trim() || 'fiasul_prod';
            select.value = target.value;
            target.selected = true;
            select.selectedIndex = opts.indexOf(target);
            combo.setAttribute('selectedindex', String(select.selectedIndex));
            combo.selectedIndex = select.selectedIndex;
            combo.value = desired;
            combo.setAttribute('value', desired);
            select.dispatchEvent(new Event('input', { bubbles:true }));
            select.dispatchEvent(new Event('change', { bubbles:true }));
            if(input){
                input.value = desired;
                input.dispatchEvent(new Event('input', { bubbles:true }));
                input.dispatchEvent(new Event('change', { bubbles:true }));
                input.dispatchEvent(new Event('blur', { bubbles:true }));
            }
            combo.dispatchEvent(new Event('input', { bubbles:true }));
            combo.dispatchEvent(new Event('change', { bubbles:true }));
            combo.dispatchEvent(new CustomEvent('wa-change', { bubbles:true, detail:{ value: desired }}));
            return true;
            """
        ))
    except Exception:
        return False


def ensure_environment_selected(driver: webdriver.Chrome, timeout: int = 20) -> bool:
    end = time.time() + timeout
    attempt = 0
    while time.time() < end:
        attempt += 1
        select_environment_exact(driver)
        env_val = (get_env_value(driver) or "").strip().lower()
        if "fiasul_prod" in env_val:
            return True
        time.sleep(0.3)
    return False


def wait_for_shadow_host(driver: webdriver.Chrome, selector: str, timeout: int = 20) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            exists = driver.execute_script(
                "return !!document.querySelector(arguments[0]);", selector
            )
            if exists:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def ensure_active_window(driver: webdriver.Chrome):
    handles = driver.window_handles
    if not handles:
        raise RuntimeError("Janela do Chrome foi fechada inesperadamente.")
    driver.switch_to.window(handles[-1])


def wait_for_window_ready(driver: webdriver.Chrome, timeout: int = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if driver.window_handles:
                driver.switch_to.window(driver.window_handles[-1])
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def wait_for_selector(driver: webdriver.Chrome, selector: str, timeout: int = 30) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            exists = driver.execute_script(
                "return !!document.querySelector(arguments[0]);", selector
            )
            if exists:
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def dialog_is_open(driver: webdriver.Chrome) -> bool:
    try:
        return bool(driver.execute_script(
            "return !!document.querySelector('wa-dialog.startParameters');"
        ))
    except Exception:
        return False


def switch_to_login_frame(driver: webdriver.Chrome) -> bool:
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    # tenta encontrar o iframe que contém input[name='login']
    for frame in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(frame)
            found = driver.execute_script(
                "return !!document.querySelector(\"input[name='login']\");"
            )
            if found:
                return True
            driver.switch_to.default_content()
        except Exception:
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
    return False


def fill_login_fields_js(driver: webdriver.Chrome, user: str, senha: str) -> bool:
    try:
        return bool(driver.execute_script(
            """
            function setVal(input, value){
                if(!input) return false;
                input.focus();
                input.value = value;
                input.dispatchEvent(new Event('input', { bubbles:true }));
                input.dispatchEvent(new Event('change', { bubbles:true }));
                return true;
            }
            function fillInDoc(doc){
                const login = doc.querySelector("input[name='login'], input[id^='po-login']");
                const pass = doc.querySelector("input[name='password'], input[id^='po-password']");
                let ok1 = setVal(login, arguments[0]);
                let ok2 = setVal(pass, arguments[1]);
                return ok1 || ok2;
            }
            // documento atual
            if(fillInDoc(document)) return true;
            // iframes (mesma origem)
            const frames = Array.from(document.querySelectorAll('iframe'));
            for(const f of frames){
                try{
                    if(f.contentDocument && fillInDoc(f.contentDocument)) return true;
                }catch(e){}
            }
            return false;
            """,
            user,
            senha
        ))
    except Exception:
        return False


def click_entrar(driver: webdriver.Chrome) -> bool:
    try:
        return bool(driver.execute_script(
            """
            function clickInDoc(doc){
                const btn = Array.from(doc.querySelectorAll('button, po-button, [role=\"button\"]'))
                  .find(b => (b.textContent || '').trim().toLowerCase() === 'entrar');
                if(btn){ btn.click(); return true; }
                return false;
            }
            if(clickInDoc(document)) return true;
            const frames = Array.from(document.querySelectorAll('iframe'));
            for(const f of frames){
                try{
                    if(f.contentDocument && clickInDoc(f.contentDocument)) return true;
                }catch(e){}
            }
            return false;
            """
        ))
    except Exception:
        return False


def debug_login_state(driver: webdriver.Chrome):
    try:
        info = driver.execute_script(
            """
            const login = document.querySelector("input[name='login']");
            const pass = document.querySelector("input[name='password']");
            const entrar = Array.from(document.querySelectorAll('button, po-button, [role=\"button\"]'))
              .find(b => (b.textContent || '').trim().toLowerCase() === 'entrar');
            return {
                hasLogin: !!login,
                hasPass: !!pass,
                loginValue: login ? (login.value || '') : '',
                passValue: pass ? (pass.value || '') : '',
                entrarFound: !!entrar
            };
            """
        )
        print("DEBUG login:", info)
    except Exception as e:
        print("DEBUG login: erro ao inspecionar DOM", e)


def type_login_keyboard(driver: webdriver.Chrome, user: str, senha: str) -> bool:
    try:
        actions = ActionChains(driver)
        # foca no primeiro input visível e digita
        actions.send_keys(user)
        actions.send_keys(Keys.TAB)
        actions.send_keys(senha)
        actions.send_keys(Keys.ENTER)
        actions.perform()
        return True
    except Exception:
        return False


def type_login_keyboard_flow(driver: webdriver.Chrome, user: str, senha: str) -> bool:
    try:
        actions = ActionChains(driver)
        actions.send_keys(user)
        actions.send_keys(Keys.TAB)
        actions.send_keys(senha)
        actions.send_keys(Keys.TAB)
        actions.send_keys(Keys.ENTER)
        actions.perform()
        return True
    except Exception:
        return False


def wait_for_login_fields(driver: webdriver.Chrome, timeout: int = 20) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            found = driver.execute_script(
                """
                return !!document.querySelector("input[name='login'], input[id^='po-login']")
                    || !!document.querySelector("input[name='password'], input[id^='po-password']");
                """
            )
            if found:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def login_protheus(driver: webdriver.Chrome, wait: WebDriverWait, user: str, senha: str) -> bool:
    # Tela SmartClient
    print("Etapa: SmartClient - aguardando tela inicial")
    time.sleep(5)
    wait_for_window_ready(driver, timeout=30)
    wait_for_selector(driver, "wa-dialog.startParameters", timeout=40)
    wait_for_selector(driver, "wa-combobox#selectStartProg", timeout=40)
    wait_for_selector(driver, "wa-combobox#selectEnv", timeout=40)
    wait_for_env_options(driver, timeout=30)
    print("Etapa: SmartClient - combinacoes carregadas")
    ensure_startprog_selected(driver, timeout=10)
    if not ensure_environment_selected(driver, timeout=20):
        print("Etapa: SmartClient - falha ao selecionar ambiente")
        return False
    print("Etapa: SmartClient - ambiente selecionado")

    # Reaplica Programa Inicial + Ambiente
    print("Etapa: SmartClient - reaplicando programa/ambiente")
    select_startprog_exact(driver)
    select_environment_exact(driver)
    time.sleep(0.4)
    # Fluxo solicitado
    print("Etapa: SmartClient - enviando 2 TABs + ENTER")
    press_tabs_enter(driver, tabs=1)
# esta acontecendo algo nessa parte que da só um tab e depois some o selector de elemento e não completa os dois tabs
    print("Etapa: Login - aguardando 10s")
    time.sleep(10)
    print("Etapa: Login - digitando credenciais (teclado) + TAB + ENTER")
    type_login_keyboard_flow(driver, user, senha)

    print("Etapa: Pos-login - aguardando 10s")
    time.sleep(10)
    print("Etapa: Pos-login - enviando 14 TABs + ENTER")
    press_tabs_enter(driver, tabs=14)

    print("Etapa: Final - aguardando 15s antes de fechar")
    time.sleep(15)

    print("Etapa: Fluxo concluido")
    return True


def snapshot_dir(path: Path):
    return {p.name for p in path.glob("*") if p.is_file()}


def wait_for_download(download_dir: Path, before: set, timeout: int = 120):
    start = time.time()
    while time.time() - start < timeout:
        current = snapshot_dir(download_dir)
        new_files = current - before
        in_progress = [p for p in download_dir.glob("*.crdownload")]
        if new_files and not in_progress:
            return list(new_files)
        time.sleep(0.5)
    return []


def download_links(driver: webdriver.Chrome, download_dir: Path, links: list[str]):
    for link in links:
        print("Baixando:", link)
        before = snapshot_dir(download_dir)
        try:
            ensure_active_window(driver)
            driver.get(link)
        except Exception as e:
            print("Aviso: sessao do navegador indisponivel durante o download.", e)
            return
        files = wait_for_download(download_dir, before, timeout=180)
        if files:
            print("Concluído:", ", ".join(files))
        else:
            print("Aviso: não detectei o arquivo baixado (verifique a pasta).")


def parse_args():
    parser = argparse.ArgumentParser(description="Downloader Protheus")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="URL base do Protheus")
    parser.add_argument("--download-dir", default=str(Path.cwd()), help="Pasta de downloads")
    parser.add_argument("--headless", action="store_true", help="Rodar em modo headless")
    parser.add_argument("--manual", action="store_true", help="Login manual (sem usuário/senha)")
    parser.add_argument("--user", default="", help="Usuário do Protheus (override)")
    parser.add_argument("--password", default="", help="Senha do Protheus (override)")
    parser.add_argument("--stop-after-login", action="store_true", help="Parar após o segundo Entrar")
    parser.add_argument("--link", action="append", dest="links", help="Adicionar link de planilha")
    return parser.parse_args()


def main():
    args = parse_args()
    download_dir = Path(args.download_dir).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    links = args.links if args.links else list(DEFAULT_LINKS)

    user = (args.user or os.getenv("PROTHEUS_USER", "")).strip()
    senha = (args.password or os.getenv("PROTHEUS_PASS", "")).strip()
    if args.manual:
        user = ""
        senha = ""

    driver = build_driver(download_dir, args.headless)
    wait = WebDriverWait(driver, 60)

    print("Abrindo Protheus...")
    driver.get(args.base_url)

    if not args.manual:
        if not user or not senha:
            print("Usuário/senha não definidos. Use PROTHEUS_USER e PROTHEUS_PASS ou --manual.")
            driver.quit()
            sys.exit(1)
        if not login_protheus(driver, wait, user, senha):
            driver.quit()
            return
    else:
        print("Faça o login manual no Protheus. Aguarde 30s.")
        time.sleep(30)

    if args.stop_after_login:
        print("Parado após login conforme solicitado.")
        time.sleep(5)
        driver.quit()
        return

    time.sleep(5)
    download_links(driver, download_dir, links)

    print("Downloads finalizados")
    time.sleep(3)
    driver.quit()


if __name__ == "__main__":
    main()
