"""Obtener información del clima usando Open-Meteo API con fallback a Google scraping."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from utils.sanitizar import sanitizar
import os
import time
import re
import random
import json
import urllib.request
import urllib.parse


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


# Mapeo de Weather Code (WMO) → Descripción en español
_WMO_DESC = {
    0: "Cielo despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado",
    3: "Nublado", 45: "Niebla", 48: "Niebla con escarcha",
    51: "Llovizna ligera", 53: "Llovizna moderada", 55: "Llovizna intensa",
    61: "Lluvia ligera", 63: "Lluvia moderada", 65: "Lluvia intensa",
    71: "Nevada ligera", 73: "Nevada moderada", 75: "Nevada intensa",
    80: "Chubascos ligeros", 81: "Chubascos moderados", 82: "Chubascos fuertes",
    95: "Tormenta eléctrica", 96: "Tormenta con granizo ligero", 99: "Tormenta con granizo fuerte",
}


# ── Fuente principal: Open-Meteo API ──────────────────────────────────────────
def _clima_open_meteo(consulta: str) -> str | None:
    """Obtiene clima usando Open-Meteo (geocoding + forecast). Retorna cadena o None."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}

        # 1) Geocodificar la ciudad
        nombre = consulta.strip()
        geo_url = (
            f"https://geocoding-api.open-meteo.com/v1/search"
            f"?name={urllib.parse.quote_plus(nombre)}&count=1&language=es"
        )
        req = urllib.request.Request(geo_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            geo = json.loads(resp.read().decode("utf-8"))

        if not geo.get("results"):
            return None
        r = geo["results"][0]
        lat, lon = r["latitude"], r["longitude"]
        loc_name = r.get("name", nombre)
        admin = r.get("admin1", "")
        country = r.get("country", "")
        ubicacion = f"{loc_name}, {admin}" if admin else loc_name
        if country:
            ubicacion += f" ({country})"

        # 2) Obtener clima actual
        wx_url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,relative_humidity_2m,weather_code,"
            f"wind_speed_10m,apparent_temperature"
            f"&timezone=auto"
        )
        req2 = urllib.request.Request(wx_url, headers=headers)
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            wx = json.loads(resp2.read().decode("utf-8"))

        c = wx["current"]
        temp = c["temperature_2m"]
        humedad = c["relative_humidity_2m"]
        viento = c["wind_speed_10m"]
        sensacion = c.get("apparent_temperature")
        wmo_code = c.get("weather_code", -1)
        condicion = _WMO_DESC.get(wmo_code, f"Código {wmo_code}")

        partes = [f"{ubicacion}: {temp}°C, {condicion}"]
        if sensacion is not None:
            partes.append(f"Sensación: {sensacion}°C")
        partes.append(f"Humedad: {humedad}%")
        partes.append(f"Viento: {viento} km/h")
        return ". ".join(partes) + "."
    except Exception:
        return None


# ── Fuente secundaria: Google scraping ─────────────────────────────────────────
def _clima_google(driver, consulta: str) -> str | None:
    """Intenta obtener el clima scrapeando Google. Retorna cadena o None."""
    q = sanitizar(consulta)
    time.sleep(random.uniform(0.5, 1.5))
    driver.get(f"https://www.google.com/search?q=clima+{q}&hl=es")

    wait = WebDriverWait(driver, 8)
    try:
        wait.until(lambda d: d.find_elements(By.ID, "wob_tm")
                             or d.find_elements(By.CSS_SELECTOR, ".nB7Pqb")
                             or d.find_elements(By.CSS_SELECTOR, ".ilUpNd"))
    except Exception:
        pass

    page = driver.page_source

    if "captcha" in page.lower() or "recaptcha" in page.lower():
        return None

    def safe_find(id_):
        try:
            return driver.find_element(By.ID, id_).text
        except Exception:
            return None

    loc = safe_find("wob_loc")
    temp = safe_find("wob_tm")
    cond = safe_find("wob_dc")
    precip = safe_find("wob_pp")
    hum = safe_find("wob_hm")
    wind = safe_find("wob_ws")
    unit = "C"

    # Fallback temperatura
    if not temp:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, ".nB7Pqb"):
                txt = (el.text or "").strip()
                m = re.search(r"(\d{1,3})\s?°\s?([CF])?", txt)
                if m:
                    temp = m.group(1)
                    if m.group(2):
                        unit = m.group(2)
                    break
        except Exception:
            pass

    if not temp:
        m = re.search(r">(\d{1,3})°([CF])<", page)
        if m:
            temp, unit = m.group(1), m.group(2)

    # Fallback ubicación
    if not loc:
        try:
            for e in driver.find_elements(By.CSS_SELECTOR, ".ilUpNd"):
                txt = (e.text or "").strip()
                if "," in txt and 2 < len(txt) < 60:
                    loc = txt
                    break
        except Exception:
            pass
        if not loc:
            loc = consulta

    # Fallback condición
    if not cond:
        m2 = re.search(
            r"\b(Despejado|Nublado|Nubes|Lluvia|Tormenta|Chubascos|Soleado"
            r"|Parcialmente nublado|Cielo despejado)\b",
            page, re.I,
        )
        cond = m2.group(1) if m2 else "N/A"

    if not temp:
        return None

    parts = [f"{loc}: {temp}°{unit}, {cond}"]
    if precip:
        parts.append(f"Precip: {precip}")
    if hum:
        parts.append(f"Humedad: {hum}")
    if wind:
        parts.append(f"Viento: {wind}")
    return ". ".join(parts) + "."


# ── Función pública ────────────────────────────────────────────────────────────
def obtener_clima(driver, consulta: str) -> str:
    """Obtiene el clima: primero wttr.in, luego Google scraping."""

    # 1) Intentar Open-Meteo API
    resultado = _clima_open_meteo(consulta)
    if resultado:
        return resultado

    # 2) Fallback: Google scraping
    try:
        resultado = _clima_google(driver, consulta)
        if resultado:
            return resultado
    except Exception:
        pass

    # 3) Guardar HTML para debug
    dbg = _save_debug_html(driver, "clima", sanitizar(consulta))
    if dbg:
        return f"No se pudo obtener el clima en este momento. HTML guardado en: {dbg}"
    return "No se pudo obtener el clima en este momento."
