import unicodedata
import re
from urllib.parse import quote_plus


def sanitizar(text: str) -> str:
    """Normaliza y codifica una consulta para usar en una URL de búsqueda.

    - elimina tildes/acentos
    - elimina caracteres especiales
    - colapsa espacios
    - aplica `quote_plus` para seguridad en URLs
    """
    if not text:
        return ""
    s = text.strip()
    # Normalizar y quitar marcas diacríticas
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    # Eliminar caracteres que no sean letras, números, guiones o espacios
    s = re.sub(r"[^\w\s-]", "", s)
    # Colapsar espacios y guiones multiple
    s = re.sub(r"[-\s]+", " ", s).strip()
    return quote_plus(s)