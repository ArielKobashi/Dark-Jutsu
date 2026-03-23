import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# endereço do protheus
url = "https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/index.html"

# links das planilhas
planilhas = [
"https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/cc71b606-b13f-46f9-bbcc-eb7ae5d5e155/user/26bcc80fb99446889669d7ef7869b65b/mata105.xlsx?download=1",
"https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/mata225.xlsx?download=1",
"https://fiasulindustria182431.protheus.cloudtotvs.com.br:1703/webapp/mata226.xlsx?download=1"
]

# abre navegador
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

driver.get(url)

print("Faça login no Protheus...")
time.sleep(30)  # tempo para logar

for planilha in planilhas:
    driver.get(planilha)
    print("Baixando:", planilha)
    time.sleep(5)

print("Download finalizado")

driver.quit()