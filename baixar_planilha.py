import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

download_dir = r"C:\Users\davi.souza\Desktop\KKKKKKKK"

options = webdriver.ChromeOptions()

prefs = {
"download.default_directory": download_dir,
"download.prompt_for_download": False
}

options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(
service=Service(ChromeDriverManager().install()),
options=options
)

wait = WebDriverWait(driver, 60)

print("Abrindo Protheus...")

driver.get("https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/index.html")

# ===== TELA SMARTCLIENT =====
try:
    ok = wait.until(EC.element_to_be_clickable((By.XPATH,"//button[contains(.,'OK')]")))
    ok.click()
    print("SmartClient confirmado")
except:
    print("Tela SmartClient não apareceu")

# ===== LOGIN =====
usuario = "davi.souza"
senha = "pudimA1?"

campo_user = wait.until(EC.presence_of_element_located((By.XPATH,"//input[@type='text']")))
campo_user.send_keys(usuario)

campo_pass = driver.find_element(By.XPATH,"//input[@type='password']")
campo_pass.send_keys(senha)

driver.find_element(By.XPATH,"//button[contains(.,'Entrar')]").click()

print("Login realizado")

# ===== TELA AMBIENTE =====
try:
    entrar2 = wait.until(EC.element_to_be_clickable((By.XPATH,"//button[contains(.,'Entrar')]")))
    entrar2.click()
    print("Ambiente confirmado")
except:
    print("Tela ambiente não apareceu")

time.sleep(10)

# ===== DOWNLOADS =====
links = [

"https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/mata105.xlsx?download=1",

"https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/mata225.xlsx?download=1",

"https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/mata226.xlsx?download=1"

]

for link in links:

    print("Baixando:",link)

    driver.execute_script(f"window.open('{link}')")

    time.sleep(6)

print("Downloads finalizados")

time.sleep(15)

driver.quit()