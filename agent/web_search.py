"""Scraping de specs técnicas desde sitios oficiales de marcas."""

import re
import httpx
import logging
from urllib.parse import urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger("agentkit")

DOMINIOS_PERMITIDOS = {
    "therabody.com",
    "www.therabody.com",
    "whoop.com",
    "www.whoop.com",
    "foreo.com",
    "www.foreo.com",
    "us.foreo.com",
}

_ETIQUETAS_ELIMINAR = [
    "script", "style", "nav", "footer", "header", "aside",
    "form", "button", "iframe", "noscript",
]

_PATRON_COMERCIAL = re.compile(
    r"(\$|USD|€|£|PYG|Gs\.)\s*[\d,]+|"
    r"\b(free shipping|add to cart|buy now|shop now|"
    r"warranty|return policy|refund|subscribe|sign up|"
    r"newsletter|cookie|privacy policy|terms of use|"
    r"checkout|cart|basket|order now|qty|quantity|"
    r"in stock|out of stock|available|ships)\b",
    re.IGNORECASE,
)


def _url_permitida(url: str) -> bool:
    try:
        return urlparse(url).netloc.lower() in DOMINIOS_PERMITIDOS
    except Exception:
        return False


async def scrape_specs(url: str) -> str:
    """
    Scrapes product technical specs from an official brand URL.
    Filters out all commercial info (prices, warranties, CTAs).
    Returns plain text with product description and specs only.
    """
    if not _url_permitida(url):
        dominios = ", ".join(sorted(DOMINIOS_PERMITIDOS))
        return f"URL no permitida. Solo se pueden consultar: {dominios}"

    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            })
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in _ETIQUETAS_ELIMINAR:
            for el in soup.find_all(tag):
                el.decompose()

        texto = soup.get_text(separator="\n")

        lineas_limpias = []
        for linea in texto.splitlines():
            linea = linea.strip()
            if len(linea) < 8:
                continue
            if _PATRON_COMERCIAL.search(linea):
                continue
            lineas_limpias.append(linea)

        # Limitar a 200 líneas para no saturar el contexto
        resultado = "\n".join(lineas_limpias[:200])
        logger.info(f"✓ Scrape OK: {url[:70]} — {len(resultado)} chars")
        return resultado or "No se pudo extraer información técnica de la página."

    except httpx.TimeoutException:
        logger.warning(f"⚠️ Timeout scraping {url}")
        return "Tiempo de espera agotado al consultar la página oficial."
    except httpx.HTTPStatusError as e:
        logger.warning(f"⚠️ HTTP {e.response.status_code} en {url}")
        return f"La página oficial respondió con error {e.response.status_code}."
    except Exception as e:
        logger.warning(f"⚠️ Error scraping {url}: {e}")
        return "No se pudo acceder a la página oficial en este momento."
