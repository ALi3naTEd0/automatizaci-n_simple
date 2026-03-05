"""Obtener precio de acciones usando yfinance (API) con fallback a Google scraping."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.sanitizar import sanitizar
import re
import os
import time
import random

# Mapeo de nombres comunes en español → ticker Yahoo Finance
TICKER_MAP = {
    "tesla": "TSLA",
    "apple": "AAPL",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "microsoft": "MSFT",
    "meta": "META",
    "facebook": "META",
    "nvidia": "NVDA",
    "netflix": "NFLX",
    "mercado libre": "MELI",
    "mercadolibre": "MELI",
    "coca cola": "KO",
    "coca-cola": "KO",
    "disney": "DIS",
    "walmart": "WMT",
    "amd": "AMD",
    "intel": "INTC",
    "uber": "UBER",
    "spotify": "SPOT",
    "airbnb": "ABNB",
    "paypal": "PYPL",
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "oro": "GC=F",
    "petroleo": "CL=F",
    "petróleo": "CL=F",
    "dolar": "MXN=X",
    "dólar": "MXN=X",
}


def _save_debug_html(driver, prefix, consulta):
    try:
        logs_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        name = f"{prefix}_{int(time.time())}_{consulta}.html"
        path = os.path.join(logs_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        return path
    except Exception:
        return None


def _resolver_ticker(consulta: str) -> str | None:
    """Intenta resolver un nombre de empresa a su ticker de Yahoo Finance."""
    c = consulta.lower().strip()
    # Buscar en el mapeo
    if c in TICKER_MAP:
        return TICKER_MAP[c]
    # Si parece un ticker directo (todo mayúsculas, corto)
    if re.match(r"^[A-Z]{1,5}$", consulta.strip()):
        return consulta.strip().upper()
    # Buscar parcial en el mapeo
    for nombre, ticker in TICKER_MAP.items():
        if nombre in c or c in nombre:
            return ticker
    return None


# ── Fuente principal: yfinance ─────────────────────────────────────────────────
def _precio_yfinance(consulta: str) -> str | None:
    """Intenta obtener el precio usando yfinance. Retorna cadena o None."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    ticker_str = _resolver_ticker(consulta)
    if not ticker_str:
        # Intentar con el texto tal cual como ticker
        ticker_str = consulta.strip().upper()

    try:
        ticker = yf.Ticker(ticker_str)
        info = ticker.info

        nombre = info.get("shortName") or info.get("longName") or ticker_str
        precio = info.get("currentPrice") or info.get("regularMarketPrice")
        moneda = info.get("currency", "USD")
        cambio = info.get("regularMarketChangePercent")

        if precio is None:
            # Intentar desde fast_info
            fi = ticker.fast_info
            precio = getattr(fi, "last_price", None)
            moneda = getattr(fi, "currency", "USD") or "USD"

        if precio is None:
            return None

        resultado = f"{nombre} [{ticker_str}]: ${precio:,.2f} {moneda}"
        if cambio is not None:
            signo = "+" if cambio >= 0 else ""
            resultado += f" ({signo}{cambio:.2f}%)"
        return resultado
    except Exception:
        return None


# ── Fuente secundaria: Google scraping ─────────────────────────────────────────
def _precio_google(driver, consulta: str) -> str | None:
    """Intenta obtener el precio scrapeando Google. Retorna cadena o None."""
    q = sanitizar(consulta)
    time.sleep(random.uniform(0.5, 1.5))
    driver.get(f"https://www.google.com/search?q=precio+accion+{q}&hl=es")

    wait = WebDriverWait(driver, 8)

    page = driver.page_source
    if "captcha" in page.lower() or "recaptcha" in page.lower():
        return None

    try:
        price_text = None
        for sel in ["span[jsname='vWLAgc']", "div[data-attrid='Price'] span", "span.IsqQVc"]:
            try:
                elem = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                price_text = elem.text
                if price_text:
                    break
            except Exception:
                pass

        empresa = None
        for sel in ["div.PZPZlf", "div[class='PZPZlf ssJ7i B5dxMb']", "div.LrzXr"]:
            try:
                empresa = driver.find_element(By.CSS_SELECTOR, sel).text
                if empresa:
                    break
            except Exception:
                pass

        # Fallback: buscar precio en HTML con regex
        if not price_text:
            page = driver.page_source
            pm = re.search(r'([\d,]+\.\d{2})\s*(?:USD|EUR|MXN|GBP)', page)
            if pm:
                price_text = pm.group(1)
            else:
                pm2 = re.search(r'>\$?\s*([\d,]+\.\d{2})<', page)
                if pm2:
                    price_text = pm2.group(1)

        if not empresa and not price_text:
            return None

        # Extraer ticker si está entre paréntesis
        ticker = ""
        if empresa:
            m = re.search(r"\(([A-Z0-9\.\-]{1,10})\)", empresa)
            if m:
                ticker = m.group(1)
                empresa = re.sub(r"\s*\([A-Z0-9\.\-]{1,10}\)", "", empresa).strip()

        # Heurística para divisa
        page = driver.page_source
        div_match = re.search(r"\b(USD|EUR|GBP|MXN|ARS|CLP|JPY|COP|BRL|CAD)\b", page)
        divisa = div_match.group(1) if div_match else ""

        precio_text = price_text or "N/A"
        ticker_text = f" [{ticker}]" if ticker else ""
        emp_text = empresa or consulta
        div_text = f" {divisa}" if divisa else ""

        return f"{emp_text}{ticker_text}: ${precio_text}{div_text}"
    except Exception:
        return None


# ── Función pública ────────────────────────────────────────────────────────────
def obtener_precio_accion(driver, consulta: str) -> str:
    """Obtiene precio de acción: primero yfinance, luego Google scraping."""

    # 1) Intentar yfinance
    resultado = _precio_yfinance(consulta)
    if resultado:
        return resultado

    # 2) Fallback: Google scraping
    try:
        resultado = _precio_google(driver, consulta)
        if resultado:
            return resultado
    except Exception:
        pass

    # 3) Guardar HTML para debug
    dbg = _save_debug_html(driver, "precio", sanitizar(consulta))
    if dbg:
        return f"No se pudo obtener el precio de la acción en este momento. HTML guardado en: {dbg}"
    return "No se pudo obtener el precio de la acción en este momento."
