from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
import shutil
import os
import stat
import glob

from funciones_agentes.obtener_clima import obtener_clima
from funciones_agentes.obtener_precio_accion import obtener_precio_accion

import re

# Configuración de Selenium
options = Options()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--window-size=1920,1080")
options.add_argument("--lang=es-MX")
options.add_argument(
    "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option("useAutomationExtension", False)

def find_chrome_executable():
    candidates = [
        'google-chrome',
        'google-chrome-stable',
        'google-chrome-beta',
        'google-chrome-dev',
        'chromium',
        'chromium-browser'
    ]
    for name in candidates:
        path = shutil.which(name)
        if path:
            return path
    return None


def resolve_driver_executable(path):
    # if path is a directory, search for 'chromedriver'
    if os.path.isdir(path):
        candidates = glob.glob(os.path.join(path, '**', 'chromedriver'), recursive=True)
        if not candidates:
            raise RuntimeError(f"No se encontró 'chromedriver' dentro de {path}")
        driver_exec = candidates[0]
    else:
        driver_exec = path

    # read header to check ELF
    try:
        with open(driver_exec, 'rb') as f:
            header = f.read(4)
    except Exception:
        header = b''

    if header.startswith(b"\x7fELF"):
        if not os.access(driver_exec, os.X_OK):
            st = os.stat(driver_exec)
            os.chmod(driver_exec, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return driver_exec

    # otherwise search folder for a binary named chromedriver
    folder = os.path.dirname(driver_exec)
    for p in os.listdir(folder):
        if 'chromedriver' in p.lower():
            full = os.path.join(folder, p)
            if os.path.isfile(full):
                try:
                    with open(full, 'rb') as f:
                        h = f.read(4)
                except Exception:
                    h = b''
                if h.startswith(b"\x7fELF"):
                    if not os.access(full, os.X_OK):
                        st = os.stat(full)
                        os.chmod(full, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                    return full

    raise RuntimeError(f"El archivo {driver_exec} no parece un ejecutable ELF válido ni se encontró otro binario cromedriver en {folder}")


# Inicialización del driver: localizar Chrome y chromedriver correctos
chrome_path = find_chrome_executable()
if chrome_path:
    options.binary_location = chrome_path

raw_driver_path = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install()
driver_exec = resolve_driver_executable(raw_driver_path)
driver = webdriver.Chrome(service=Service(driver_exec), options=options)

# Eliminar la marca navigator.webdriver que delata la automatización
try:
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
except Exception:
    pass


def procesar_input(user_input):
    """Devuelve (funcion_agente, consulta_limpia) o (None, None)."""
    u = user_input.strip()
    ul = u.lower()
    if "clima" in ul or "temperatura" in ul:
        consulta = re.sub(r'\b(clima|temperatura|el|de|en)\b', '', ul).strip()
        return obtener_clima, consulta or u
    elif "precio" in ul or "accion" in ul or "acción" in ul or "valor" in ul:
        consulta = re.sub(r'\b(precio|accion|acción|valor|de|la|el)\b', '', ul).strip()
        return obtener_precio_accion, consulta or u
    return None, None


print("Hola, soy tu asistente virtual. ¿En qué puedo ayudarte hoy?")
while True:
    raw_input_text = input("---> ")
    funcion_agente, consulta = procesar_input(raw_input_text)
    if funcion_agente is None:
        print("No entendí tu solicitud. Intenta nuevamente.")
    else:
        respuesta = funcion_agente(driver, consulta)
        print(f">>> {respuesta}")