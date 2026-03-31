"""
Price Alert Tracker v3.0
Price comparison across multiple shops via Geizhals URL or search term.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import json, smtplib, threading, time, re, os, sys
from datetime import datetime
from pathlib import Path

def _resource_path(rel):
    """Resolve path to a bundled resource — works both in dev and PyInstaller."""
    base = getattr(sys, '_MEIPASS', Path(__file__).parent)
    return Path(base) / rel
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "requests", "beautifulsoup4", "win10toast",
                           "plyer", "selenium", "webdriver-manager"])
    import requests
    from bs4 import BeautifulSoup

# System Tray
TRAY_OK = False
try:
    import pystray
    from pystray import MenuItem as TrayItem
    from PIL import Image, ImageDraw
    TRAY_OK = True
except ImportError:
    pass

SELENIUM_OK = False
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_OK = True
except ImportError:
    pass

# ── Translations ─────────────────────────────────────────────────────────────
LANGUAGES = {
    "en": "🇬🇧 English",
    "de": "🇩🇪 Deutsch",
    "fr": "🇫🇷 Français",
    "es": "🇪🇸 Español",
    "it": "🇮🇹 Italiano",
    "nl": "🇳🇱 Nederlands",
    "pl": "🇵🇱 Polski",
    "pt": "🇵🇹 Português",
    "tr": "🇹🇷 Türkçe",
    "ru": "🇷🇺 Русский",
    "zh": "🇨🇳 中文",
    "ja": "🇯🇵 日本語",
    "ar": "🇸🇦 العربية",
}

REGIONS = {
    "de": {"flag": "🇩🇪", "label": "Deutschland / AT / CH", "engine": "geizhals",  "currency": "€",  "ps_domain": None,           "amz": "amazon.de"},
    "uk": {"flag": "🇬🇧", "label": "United Kingdom",         "engine": "pricespy",  "currency": "£",  "ps_domain": "pricespy.co.uk","amz": "amazon.co.uk"},
    "nl": {"flag": "🇳🇱", "label": "Netherlands",            "engine": "pricespy",  "currency": "€",  "ps_domain": "pricespy.nl",   "amz": "amazon.nl"},
    "fi": {"flag": "🇫🇮", "label": "Suomi",                  "engine": "pricespy",  "currency": "€",  "ps_domain": "pricespy.fi",   "amz": None},
    "se": {"flag": "🇸🇪", "label": "Sverige",                "engine": "pricespy",  "currency": "kr", "ps_domain": "pricespy.se",   "amz": None},
    "no": {"flag": "🇳🇴", "label": "Norge",                  "engine": "pricespy",  "currency": "kr", "ps_domain": "pricespy.no",   "amz": None},
    "dk": {"flag": "🇩🇰", "label": "Danmark",                "engine": "pricespy",  "currency": "kr", "ps_domain": "pricespy.dk",   "amz": None},
    "fr": {"flag": "🇫🇷", "label": "France",                 "engine": "amazon",    "currency": "€",  "ps_domain": None,            "amz": "amazon.fr"},
    "it": {"flag": "🇮🇹", "label": "Italia",                 "engine": "amazon",    "currency": "€",  "ps_domain": None,            "amz": "amazon.it"},
    "es": {"flag": "🇪🇸", "label": "España",                 "engine": "amazon",    "currency": "€",  "ps_domain": None,            "amz": "amazon.es"},
    "pl": {"flag": "🇵🇱", "label": "Polska",                 "engine": "amazon",    "currency": "zł", "ps_domain": None,            "amz": "amazon.pl"},
}

def _region_display(key):
    r = REGIONS.get(key, REGIONS["de"])
    return f"{r['flag']} {r['label']}"

def _region_currency(key):
    return REGIONS.get(key, REGIONS["de"])["currency"]

def _load_translations(lang_code):
    """Load translations from locales/lang_code.json file."""
    import json as _json
    # Look next to script / inside PyInstaller bundle
    locales_dir = _resource_path("locales")
    lang_file   = locales_dir / f"{lang_code}.json"
    fallback    = locales_dir / "en.json"
    try:
        if lang_file.exists():
            return _json.loads(lang_file.read_text(encoding="utf-8"))
    except: pass
    try:
        if fallback.exists():
            return _json.loads(fallback.read_text(encoding="utf-8"))
    except: pass
    return {}

# Load translations lazily
_TRANS_CACHE = {}

def _get_trans(lang_code):
    if lang_code not in _TRANS_CACHE:
        _TRANS_CACHE[lang_code] = _load_translations(lang_code)
    return _TRANS_CACHE[lang_code]
def T(key):
    """Get translation for current language from locale file."""
    lang = _current_lang()
    result = _get_trans(lang).get(key)
    if result is None:
        result = _get_trans("en").get(key, key)
    return result

def _current_lang():
    try:
        import json as _json, os as _os
        from pathlib import Path as _P
        cfg = _P(_os.getenv("APPDATA", ".")) / "PreisAlarm" / "config.json"
        if cfg.exists():
            data = _json.loads(cfg.read_text(encoding="utf-8"))
            return data.get("language", "en")
    except:
        pass
    return "en"


def toast(titel, text):
    """Show Windows toast notification — strips emojis, uses WinForms balloon."""
    import re as _re
    # Remove emojis to avoid encoding issues
    def _clean(s):
        return _re.sub(r"[^\x00-\x7F\u00C0-\u024F\u0400-\u04FF\s]", "", s).strip()
    t = _clean(titel)
    m = _clean(text)
    if not t: t = "Price Alert Tracker"
    if not m: m = titel  # fallback to original if all removed

    try:
        import subprocess as _sp, tempfile
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms\n"
            "$n = New-Object System.Windows.Forms.NotifyIcon\n"
            "$n.Icon = [System.Drawing.SystemIcons]::Application\n"
            "$n.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info\n"
            f"$n.BalloonTipTitle = '{t}'\n"
            f"$n.BalloonTipText = '{m}'\n"
            "$n.Visible = $true\n"
            "$n.ShowBalloonTip(5000)\n"
            "Start-Sleep -Milliseconds 6000\n"
            "$n.Dispose()\n"
        )
        tmp = tempfile.mktemp(suffix=".ps1")
        with open(tmp, "w", encoding="ascii", errors="ignore") as f:
            f.write(ps)
        _sp.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", tmp],
            creationflags=0x08000000,
            stdout=_sp.DEVNULL, stderr=_sp.DEVNULL
        )
    except Exception:
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(t, m, duration=8, threaded=True)
        except Exception:
            pass

# ── Pfade ─────────────────────────────────────────────────────────────────────
BASE_DIR        = Path(os.getenv("APPDATA", ".")) / "PreisAlarm"
BASE_DIR.mkdir(exist_ok=True)
VERGLEICH_DATEI = BASE_DIR / "vergleich.json"
CONFIG_DATEI    = BASE_DIR / "config.json"
LOG_DATEI       = BASE_DIR / "log.txt"

# ── Design ────────────────────────────────────────────────────────────────────
# ── Themes ────────────────────────────────────────────────────────────────────
THEMES = {
    "dark_mint": {
        "name": "🌑 Dark Mint",
        "BG":     "#0d0d12", "BG2":    "#13131a", "BG3":    "#1c1c27",
        "AKZENT": "#6ee7b7", "ROT":    "#f87171", "GELB":   "#fbbf24",
        "GRAU":   "#64748b", "TEXT":   "#f0f4ff", "TEXT2":  "#8b9cc8",
        "BORDER": "#252535", "PURPLE": "#a78bfa", "BLUE":   "#60a5fa",
    },
    "dark_blue": {
        "name": "🔵 Dark Blue",
        "BG":     "#0a0f1e", "BG2":    "#111827", "BG3":    "#1e2a3a",
        "AKZENT": "#60a5fa", "ROT":    "#f87171", "GELB":   "#fbbf24",
        "GRAU":   "#64748b", "TEXT":   "#f0f8ff", "TEXT2":  "#93c5fd",
        "BORDER": "#1e3a5f", "PURPLE": "#818cf8", "BLUE":   "#38bdf8",
    },
    "dark_purple": {
        "name": "🟣 Dark Purple",
        "BG":     "#0f0a1e", "BG2":    "#1a1030", "BG3":    "#251840",
        "AKZENT": "#c084fc", "ROT":    "#f87171", "GELB":   "#fbbf24",
        "GRAU":   "#6b7280", "TEXT":   "#faf5ff", "TEXT2":  "#d8b4fe",
        "BORDER": "#3b1f6e", "PURPLE": "#a855f7", "BLUE":   "#818cf8",
    },
    "dark_orange": {
        "name": "🟠 Dark Orange",
        "BG":     "#1a0f00", "BG2":    "#241500", "BG3":    "#321d00",
        "AKZENT": "#fb923c", "ROT":    "#f87171", "GELB":   "#fbbf24",
        "GRAU":   "#a8906a", "TEXT":   "#fff7ed", "TEXT2":  "#fed7aa",
        "BORDER": "#5c3d10", "PURPLE": "#c084fc", "BLUE":   "#60a5fa",
    },
    "light": {
        "name": "☀ Light",
        "BG":     "#f0f4f8", "BG2":    "#ffffff", "BG3":    "#e8edf2",
        "AKZENT": "#059669", "ROT":    "#dc2626", "GELB":   "#b45309",
        "GRAU":   "#64748b", "TEXT":   "#1a2332", "TEXT2":  "#334155",
        "BORDER": "#cbd5e1", "PURPLE": "#7c3aed", "BLUE":   "#1d4ed8",
    },
    "light_blue": {
        "name": "🔵 Light Blue",
        "BG":     "#eef4ff", "BG2":    "#ffffff", "BG3":    "#dce8ff",
        "AKZENT": "#1d4ed8", "ROT":    "#dc2626", "GELB":   "#b45309",
        "GRAU":   "#64748b", "TEXT":   "#0f2040", "TEXT2":  "#1e40af",
        "BORDER": "#93c5fd", "PURPLE": "#6d28d9", "BLUE":   "#1d4ed8",
    },
}

# ── Fonts ─────────────────────────────────────────────────────────────────────
FONTS = {
    "segoe":    {"name": "Segoe UI",    "label": "Segoe UI (Standard)"},
    "bahnschrift": {"name": "Bahnschrift", "label": "Bahnschrift (Modern)"},
    "calibri":  {"name": "Calibri",        "label": "Calibri (Office)"},
    "verdana":  {"name": "Verdana",        "label": "Verdana (Readable)"},
    "trebuchet":{"name": "Trebuchet MS",   "label": "Trebuchet MS (Clean)"},
    "tahoma":   {"name": "Tahoma",         "label": "Tahoma (Classic)"},
    "arial":    {"name": "Arial",          "label": "Arial (Universal)"},
    "gothic":   {"name": "Century Gothic", "label": "Century Gothic (Round)"},
}

def _load_font():
    try:
        import json as _j, os as _o
        from pathlib import Path as _P
        cfg = _P(_o.getenv("APPDATA", ".")) / "PreisAlarm" / "config.json"
        if cfg.exists():
            data = _j.loads(cfg.read_text(encoding="utf-8"))
            font_id = data.get("font", "segoe")
            return FONTS.get(font_id, FONTS["segoe"])["name"], font_id
    except: pass
    return UI_FONT, "segoe"

UI_FONT, _font_id = _load_font()


def _load_theme():
    """Load theme from config."""
    try:
        import json as _j, os as _o
        from pathlib import Path as _P
        cfg = _P(_o.getenv("APPDATA", ".")) / "PreisAlarm" / "config.json"
        if cfg.exists():
            data = _j.loads(cfg.read_text(encoding="utf-8"))
            theme_id = data.get("theme", "dark_mint")
            return THEMES.get(theme_id, THEMES["dark_mint"]), theme_id
    except: pass
    return THEMES["dark_mint"], "dark_mint"

_theme, _theme_id = _load_theme()
BG     = _theme["BG"]
BG2    = _theme["BG2"]
BG3    = _theme["BG3"]
AKZENT = _theme["AKZENT"]
ROT    = _theme["ROT"]
GELB   = _theme["GELB"]
GRAU   = _theme["GRAU"]
TEXT   = _theme["TEXT"]
TEXT2  = _theme["TEXT2"]
BORDER = _theme["BORDER"]
PURPLE = _theme["PURPLE"]
BLUE   = _theme["BLUE"]

SHOPS = {
    "amazon": "Amazon.de", "mediamarkt": "MediaMarkt", "saturn": "Saturn",
    "otto": "OTTO", "ebay": "eBay", "alza": "Alza.de", "alternate": "Alternate",
    "mindfactory": "Mindfactory", "notebooksbilliger": "notebooksbilliger",
    "cyberport": "Cyberport", "kaufland": "Kaufland", "caseking": "Caseking",
    "idealo": "Idealo", "geizhals": "Geizhals", "custom": "Sonstiger Shop",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

JS_SHOPS = {"alza", "alternate", "mindfactory", "notebooksbilliger", "cyberport", "caseking"}

# ── Datenverwaltung ───────────────────────────────────────────────────────────
def lade_vergleiche():
    if VERGLEICH_DATEI.exists():
        with open(VERGLEICH_DATEI, "r", encoding="utf-8") as f:
            daten = json.load(f)
        # Migration: Currency-Encoding-Fehler beheben (â‚¬ → €, Â£ → £)
        CURRENCY_FIX = {"â‚¬": "€", "â¬": "€", "Â£": "£"}
        geaendert = False
        for g in daten:
            cur = g.get("currency", "")
            fixed = cur
            for bad, good in CURRENCY_FIX.items():
                fixed = fixed.replace(bad, good)
            if fixed != cur:
                g["currency"] = fixed
                geaendert = True

        # Migration: alte Einträge mit shop="custom" reparieren
        for g in daten:
            for s in g.get("shops", []):
                if s.get("shop") == "custom":
                    # Shop-Name aus URL ableiten
                    url = s.get("url", "")
                    try:
                        from urllib.parse import urlparse
                        domain = urlparse(url).netloc.replace("www.", "")
                        if domain:
                            s["shop"] = domain
                            geaendert = True
                    except:
                        pass
        if geaendert:
            with open(VERGLEICH_DATEI, "w", encoding="utf-8") as f:
                json.dump(daten, f, ensure_ascii=False, indent=2)
        return daten
    return []

def speichere_vergleiche(liste):
    with open(VERGLEICH_DATEI, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False, indent=2)

def lade_config():
    defaults = {"email_absender": "", "email_passwort": "", "email_empfaenger": "",
                "smtp_server": "mail.gmx.net", "smtp_port": 587, "intervall": 6, "language": "en"}
    if CONFIG_DATEI.exists():
        with open(CONFIG_DATEI, "r", encoding="utf-8") as f:
            return {**defaults, **json.load(f)}
    return defaults

def speichere_config(cfg):
    with open(CONFIG_DATEI, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def log(msg):
    ts = datetime.now().strftime("%d.%m.%Y %H:%M")
    zeile = f"[{ts}] {msg}\n"
    with open(LOG_DATEI, "a", encoding="utf-8") as f:
        f.write(zeile)
    return zeile.strip()

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def _parse(text):
    clean = re.sub(r"[^\d,.]", "", str(text))
    if not clean:
        return None
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        clean = clean.replace(",", ".")
    try:
        v = float(clean)
        return v if 0.01 < v < 100000 else None
    except:
        return None

def _shop_key_aus_name(name):
    """Returns the internal shop key. Unknown shops keep their name."""
    name_l = name.lower()
    for keyword, key in [
        ("amazon","amazon"),("mediamarkt","mediamarkt"),("media markt","mediamarkt"),
        ("saturn","saturn"),("otto","otto"),("ebay","ebay"),("alza","alza"),
        ("alternate","alternate"),("mindfactory","mindfactory"),
        ("notebooksbilliger","notebooksbilliger"),("cyberport","cyberport"),
        ("kaufland","kaufland"),("caseking","caseking"),
        ("idealo","idealo"),("geizhals","geizhals"),
    ]:
        if keyword in name_l:
            return key
    # Unbekannte Shops: Name direkt als Key speichern
    return name

def _shop_aus_url(url):
    url_l = url.lower()
    for domain, key in [
        ("amazon.","amazon"),("mediamarkt.","mediamarkt"),("saturn.","saturn"),
        ("otto.","otto"),("ebay.","ebay"),("alza.","alza"),("alternate.","alternate"),
        ("mindfactory.","mindfactory"),("notebooksbilliger.","notebooksbilliger"),
        ("cyberport.","cyberport"),("kaufland.","kaufland"),("caseking.","caseking"),
        ("idealo.","idealo"),("geizhals.","geizhals"),
    ]:
        if domain in url_l:
            return key
    return "custom"



# ── Preisabruf ────────────────────────────────────────────────────────────────
def _redirect_aufloesen(url):
    """No longer used — redirects are resolved via product page."""
    return url


def redirects_aufloesen_via_produktseite(source_url, shops):
    """
    Loads the Geizhals product page ONCE with Selenium,
    clicks each shop link and captures the final URL in a new tab.
    Returns a dict {shop_name -> real_url}.
    """
    if not SELENIUM_OK or not source_url:
        return {}
    driver = None
    ergebnis = {}
    try:
        opts = Options()
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("--window-position=-32000,0")
        opts.add_argument("--lang=de-DE")
        opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        driver.set_page_load_timeout(30)

        # Produktseite laden (mit Cookie)
        log(f"  URL resolution: Loading {source_url[:60]}")
        driver.get(source_url)
        time.sleep(3)

        # Cookie-Banner wegklicken
        for sel in ["#onetrust-accept-btn-handler", "button[id*=accept]"]:
            try:
                driver.find_element(By.CSS_SELECTOR, sel).click()
                time.sleep(1)
                break
            except: pass

        time.sleep(2)

        # "Mehr Angebote" laden
        for _ in range(15):
            geklickt = driver.execute_script("""
                var selectors = [
                    '.button--load-more-offers',
                    '[class*="load-more-offer"]',
                    '[class*="load-more"]',
                    '.listview__load-more'
                ];
                var btn = null;
                for (var s of selectors) { btn = document.querySelector(s); if (btn) break; }
                if (!btn) return false;
                var t = btn.textContent.trim().toLowerCase();
                if (t === 'no more offers' || t === 'keine weiteren angebote') return false;
                btn.click(); return true;
            """)
            if not geklickt: break
            time.sleep(2)

        # Für jeden Shop: Link in neuem Tab öffnen und URL abfangen
        haupt_tab = driver.current_window_handle

        for shop in shops:
            shop_name = shop.get("shop_name") or shop["shop"]
            redir_url = shop.get("url","")
            if not ("geizhals.de/redir/" in redir_url or "geizhals.at/redir/" in redir_url or "geizhals.eu/redir/" in redir_url):
                continue

            try:
                # Link per JavaScript in neuem Tab öffnen
                driver.execute_script(f"window.open('{redir_url}', '_blank');")
                time.sleep(3)

                # Zum neuen Tab wechseln
                tabs = driver.window_handles
                if len(tabs) > 1:
                    driver.switch_to.window(tabs[-1])
                    time.sleep(2)
                    final_url = driver.current_url
                    if "geizhals.de" not in final_url and "geizhals.at" not in final_url and "geizhals.eu" not in final_url:
                        ergebnis[shop_name] = final_url
                        log(f"  ✓ {shop_name}: {final_url[:50]}")
                    else:
                        log(f"  ✗ {shop_name}: redirect blocked")
                    driver.close()
                    driver.switch_to.window(haupt_tab)
                    time.sleep(0.5)
            except Exception as e:
                log(f"  ✗ {shop_name}: {e}")
                try:
                    tabs = driver.window_handles
                    if len(tabs) > 1:
                        driver.switch_to.window(tabs[-1])
                        driver.close()
                    driver.switch_to.window(haupt_tab)
                except: pass

        return ergebnis
    except Exception as e:
        log(f"  URL resolution error: {e}")
        return {}
    finally:
        if driver:
            try: driver.quit()
            except: pass


def preis_holen(url, shop):
    try:
        html = _selenium_get(url, wait=4) if shop in JS_SHOPS and SELENIUM_OK else ""
        if not html:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json as _j
                data = _j.loads(script.string or "")
                for item in (data if isinstance(data, list) else [data]):
                    offers = item.get("offers", {})
                    if isinstance(offers, list): offers = offers[0] if offers else {}
                    p = _parse(str(offers.get("price", "")))
                    if p: return p
            except:
                pass

        # itemprop
        el = soup.find(attrs={"itemprop": "price"})
        if el:
            p = _parse(el.get("content", "") or el.get_text())
            if p: return p

        # Shop-Selektoren
        sels = {
            "amazon":     [".a-offscreen", ".a-price-whole"],
            "mediamarkt": ['[data-testid="product-price"]', '[class*="Price_value"]'],
            "saturn":     ['[data-testid="product-price"]', '[class*="Price_value"]'],
            "otto":       [".prd-price__amount"],
            "ebay":       [".x-price-primary"],
            "alza":       [".price-box__price", '[class*="price-final"]'],
            "caseking":   [".js-unit-price", '[data-qa="product-unit-price-value"]'],
        }.get(shop, []) + ['[class*="current-price"]', '[class*="sell-price"]', '.price']

        for sel in sels:
            try:
                el = soup.select_one(sel)
                if el:
                    p = _parse(el.get_text(separator=" ", strip=True))
                    if p and 1 < p < 50000: return p
            except:
                pass

        # Regex-Fallback
        matches = re.findall(r'(?<!\d)(\d{1,4}[.,]\d{2})\s*(?:€|EUR)', html)
        candidates = [c for c in [_parse(m) for m in matches] if c and 1 < c < 50000]
        if candidates:
            from collections import Counter
            return Counter(candidates).most_common(1)[0][0]
        return None
    except:
        return None

# ── Shop-Suche via URL oder Suchbegriff ──────────────────────────────────────
def _selenium_get(url, wait=4):
    """Loads a URL with real Chrome."""
    if not SELENIUM_OK:
        return ""
    driver = None
    try:
        opts = Options()
        ist_geizhals = "geizhals.de" in url or "geizhals.eu" in url or "geizhals.at" in url or "geizhals.eu" in url
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("--lang=de-DE")
        opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])
        opts.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
        driver.set_page_load_timeout(30)

        driver.get(url)
        time.sleep(2)

        # Cookie-Banner wegklicken
        for sel in ["#onetrust-accept-btn-handler", "button[id*=accept]",
                    "button[class*=accept]", "[class*=consent] button",
                    "button[id*=cookie]", "[data-testid*=accept]"]:
            try:
                driver.find_element(By.CSS_SELECTOR, sel).click()
                time.sleep(0.8)
                break
            except: pass

        time.sleep(wait)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
        time.sleep(1.5)

        # Geizhals: "Mehr Angebote" Button klicken bis alle geladen
        if ist_geizhals:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)
            for i in range(15):
                geklickt = driver.execute_script("""
                    var selectors = [
                        '.listview__bottom__more-link',
                        '.button--load-more-offers',
                        '[class*="load-more-offer"]',
                        '[class*="load-more"]',
                        '[class*="more-link"]'
                    ];
                    var btn = null;
                    for (var s of selectors) {
                        btn = document.querySelector(s);
                        if (btn) break;
                    }
                    if (!btn) return false;
                    var t = btn.textContent.trim().toLowerCase();
                    if (t === 'no more offers' || t === 'keine weiteren angebote') return false;
                    btn.scrollIntoView({block: 'center'});
                    btn.click();
                    return true;
                """)
                if geklickt:
                    time.sleep(2.5)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)
                    log(f"  More offers loaded (Klick {i+1})...")
                else:
                    break

        # PriceSpy: "Show more prices" button klicken
        ist_pricespy = "pricespy.co.uk" in url or "pricespy.com" in url
        if ist_pricespy:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            for i in range(10):
                try:
                    btn_el = driver.find_element(
                        By.XPATH,
                        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'more price')]"
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_el)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", btn_el)
                    log(f"  PriceSpy: more prices loaded (click {i+1})")
                    time.sleep(3)
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(1)
                except:
                    break  # Button gone = all loaded

        return driver.page_source
    except Exception as e:
        log(f"Selenium error: {e}")
        return ""
    finally:
        if driver:
            try: driver.quit()
            except: pass


def shops_aus_url_laden(url, max_shops=999):
    """
    Loads all shops directly from a Geizhals or Idealo product page.
    Uses Selenium (real Chrome) so JavaScript content is loaded.
    """
    shops = []
    produkt_name = ""
    try:
        log(f"Loading URL: {url[:80]}")
        html = _selenium_get(url, wait=5)
        if not html:
            r = requests.get(url, headers=HEADERS, timeout=20)
            html = r.text
            log("Fallback: regular HTTP request")

        soup = BeautifulSoup(html, "html.parser")

        # Produktname
        for sel in ["h1.variant__header__headline","h1[class*=headline]",
                    "h1[class*=product]","h1[class*=title]","h1"]:
            el = soup.select_one(sel)
            if el:
                produkt_name = el.get_text(strip=True)[:80]
                break

        anbieter = set()
        ist_geizhals = "geizhals.de" in url or "geizhals.eu" in url or "geizhals.at" in url or "geizhals.eu" in url
        ist_idealo   = "idealo.de"   in url

        # ── JSON-LD (zuverlässigste Methode) ──────────────────────────────────
        import json as _j
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = _j.loads(script.string or "")
                for item in (data if isinstance(data, list) else [data]):
                    offers = item.get("offers", [])
                    if isinstance(offers, dict): offers = [offers]
                    for offer in offers[:max_shops]:
                        seller = offer.get("seller", {})
                        name  = seller.get("name","") if isinstance(seller,dict) else str(seller)
                        preis = _parse(str(offer.get("price","")))
                        ourl  = offer.get("url","") or url
                        if name and preis and name not in anbieter:
                            anbieter.add(name)
                            shops.append({"name":name,"url":ourl,"preis":preis,
                                          "shop_key":_shop_key_aus_name(name),
                                          "shop_name":name})
            except: pass

        log(f"JSON-LD: {len(shops)} Shops gefunden")

        # ── Geizhals HTML-Parsing (alte Struktur: class="offer") ─────────────────
        if not shops and ist_geizhals:
            for offer in soup.find_all(class_="offer")[:max_shops]:
                try:
                    preis_el = offer.find(class_="gh_price")
                    if not preis_el: continue
                    preis = _parse(preis_el.get_text(strip=True))
                    if not preis: continue
                    shop_name = ""
                    shop_url  = ""
                    skip = {"zum angebot","agb","infos","bewertung","store"}
                    for a in offer.find_all("a", href=True):
                        href = a["href"]
                        text = a.get_text(strip=True)
                        if "redir" in href and text and text.lower() not in skip and len(text) > 1:
                            if not href.startswith("http"):
                                href = "https://geizhals.de" + href
                            shop_name = text
                            shop_url  = href
                            break
                    if not shop_name or not shop_url: continue
                    if shop_name not in anbieter:
                        anbieter.add(shop_name)
                        shops.append({"name": shop_name, "url": shop_url,
                                      "preis": preis,
                                      "shop_key": _shop_key_aus_name(shop_name),
                                      "shop_name": shop_name})
                except Exception as e:
                    log(f"Offer parse error (old): {e}")
                    continue
            log(f"Geizhals HTML (alt): {len(shops)} Shops gefunden")

        # ── Geizhals HTML-Parsing (neue Struktur: listview__item) ────────────────
        if not shops and ist_geizhals:
            for item in soup.find_all(
                lambda t: t.name and any("listview__item" in c for c in t.get("class", []))
            )[:max_shops]:
                try:
                    # Preis: gh_price ist weiterhin vorhanden (innerhalb eines redir-Links)
                    preis_el = item.find(class_="gh_price")
                    if not preis_el: continue
                    preis = _parse(preis_el.get_text(strip=True))
                    if not preis: continue

                    # Shop-Name: data-merchant-name Attribut ist zuverlässigste Quelle
                    shop_name = ""
                    shop_url  = ""
                    merchant_el = item.find(class_="merchant")
                    if merchant_el:
                        shop_name = merchant_el.get("data-merchant-name", "").strip()
                        if not shop_name:
                            shop_name = merchant_el.get_text(strip=True)
                        href = merchant_el.get("href", "")
                        if href:
                            if not href.startswith("http"):
                                href = "https://geizhals.de" + href
                            shop_url = href

                    # Fallback: redir-Link des Preisbuttons
                    if not shop_url:
                        price_link = preis_el.find_parent("a", href=True)
                        if price_link and "redir" in price_link.get("href", ""):
                            href = price_link["href"]
                            if not href.startswith("http"):
                                href = "https://geizhals.de" + href
                            shop_url = href

                    if not shop_name or not shop_url: continue
                    if shop_name not in anbieter:
                        anbieter.add(shop_name)
                        shops.append({"name": shop_name, "url": shop_url,
                                      "preis": preis,
                                      "shop_key": _shop_key_aus_name(shop_name),
                                      "shop_name": shop_name})
                except Exception as e:
                    log(f"Offer parse error (new): {e}")
                    continue
            log(f"Geizhals HTML (neu): {len(shops)} Shops gefunden")

        # ── Idealo HTML-Parsing ────────────────────────────────────────────────
        if not shops and ist_idealo:
            for el in soup.find_all(["article","div","li","tr"], limit=300):
                cls = " ".join(el.get("class",[]))
                if not any(k in cls.lower() for k in ["offer","price","shop","dealer","merchant"]):
                    continue
                text = el.get_text(" ", strip=True)
                m = re.search(r"(\d{1,4}[.,]\d{2})\s*€", text)
                if not m: continue
                preis = _parse(m.group(1))
                if not preis or preis < 10: continue
                # Shop-Name
                shop_name = ""
                for cls_key in ["shop","merchant","dealer","vendor","seller"]:
                    ne = el.find(class_=lambda c: c and cls_key in c.lower() if c else False)
                    if ne:
                        shop_name = ne.get_text(strip=True)[:50]
                        break
                # URL
                shop_url = url
                for a in el.find_all("a", href=True):
                    href = a["href"]
                    if any(k in href for k in ["redir","goto","out","affiliate","click"]):
                        if not href.startswith("http"):
                            href = "https://www.idealo.de" + href
                        shop_url = href
                        if not shop_name:
                            shop_name = a.get_text(strip=True)[:50]
                        break
                if shop_name and shop_name not in anbieter:
                    anbieter.add(shop_name)
                    shops.append({"name":shop_name,"url":shop_url,"preis":preis,
                                  "shop_key":_shop_key_aus_name(shop_name)})
                if len(shops) >= max_shops: break

            log(f"Idealo HTML: {len(shops)} Shops gefunden")

        # Deduplizieren und nach Preis sortieren
        shops = sorted(shops, key=lambda s: s["preis"])
        log(f"Total: {len(shops)} Shops von {url[:60]}")
        return shops, produkt_name
    except Exception as e:
        log(f"Error loading: {e}")
        return [], ""


def geizhals_suchen(suchbegriff, max_shops=999):
    """Sucht auf Geizhals (DE + EU), Fallback auf Idealo."""
    log(f"Search: '{suchbegriff}'")
    try:
        # Geizhals: DE first, then EU (both .de and .eu domains)
        for base, hloc in [
            ("https://geizhals.de", "de"),
            ("https://geizhals.de", "de,at,ch,eu,uk"),
            ("https://geizhals.eu", "de,at,ch,eu,uk,pl"),
        ]:
            # Suche nach Relevanz (kein sort=p damit nicht Zubehör zuerst kommt)
            such_url = "{}/?fs={}&bl=&hloc={}&in=&v=e&sort=n".format(
                base, requests.utils.quote(suchbegriff), hloc)
            log(f"Geizhals search ({hloc}): {such_url[:80]}")
            html = _selenium_get(such_url, wait=4)
            if not html:
                r = requests.get(such_url, headers=HEADERS, timeout=20)
                html = r.text
            soup = BeautifulSoup(html, "html.parser")

            # Produktlink finden — URL-Slug basiertes Scoring
            produkt_link = None
            suchwoerter = suchbegriff.lower().split()

            gesehen = set()
            kandidaten = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not re.search(r"-a\d{4,}\.htm", href): continue
                basis = re.sub(r"[#?].*", "", href)
                if basis in gesehen: continue
                gesehen.add(basis)

                # URL-Slug als Produktname (Geizhals rendert Namen per JS)
                slug = basis.split("/")[-1].lower()
                slug_clean = re.sub(r"-a\d+.*", "", slug).replace("-", " ")
                # Normalisiert (ohne Leerzeichen/Bindestriche) für Begriffe wie "5070ti" → "5070 ti"
                slug_norm = slug_clean.replace(" ", "")

                # Relevanz: Suchwörter im URL-Slug (mit normalisiertem Fallback)
                def _match(w):
                    return w in slug_clean or w.replace(" ", "") in slug_norm or w in slug_norm
                wort_treffer = sum(1 for w in suchwoerter if _match(w))
                # Bonus: alle Wörter vorhanden
                alle_bonus = 3 if wort_treffer == len(suchwoerter) else 0
                # Malus: Zubehör-Keywords in URL
                zubehoer = ["screen-protector","schutzglas","huelle","case","cover",
                            "kameraschutz","lens","wallet","folie","panzerglass",
                            "protector","displayschutz","hard-case","tpu","glass",
                            "schutzfolie","hulle","bumper","strap"]
                malus = sum(3 for z in zubehoer if z in slug)

                score = wort_treffer + alle_bonus - malus
                kandidaten.append((score, basis, slug_clean[:60]))

            if kandidaten:
                kandidaten.sort(key=lambda x: x[0], reverse=True)
                bester_score, produkt_link, slug_text = kandidaten[0]
                log(f"Best match (score {bester_score}): '{slug_text}'")
                for s, h, t in kandidaten[:3]:
                    log(f"  [{s:+d}] {t[:55]}")

                # Listing mode: multiple positive-score candidates → return all as variants
                positive = [(s, h, t) for s, h, t in kandidaten if s > 0]
                if len(positive) >= 2:
                    variants = []
                    for _, href, name_text in positive[:30]:
                        full_url = href if href.startswith("http") else "https://geizhals.de" + href
                        name_clean = name_text.strip().title()
                        variants.append({
                            "name":      name_clean,
                            "url":       full_url,
                            "preis":     0,
                            "shop_key":  "geizhals",
                            "shop_name": name_clean,
                        })
                    log(f"Geizhals: {len(variants)} Varianten → Listing-Modus")
                    return variants, suchbegriff, such_url

            if not produkt_link and kandidaten:
                produkt_link = kandidaten[0][1]

            if produkt_link:
                if not produkt_link.startswith("http"):
                    produkt_link = "https://geizhals.de" + produkt_link
                log(f"Product page: {produkt_link}")
                shops, name = shops_aus_url_laden(produkt_link, max_shops=999)
                if shops:
                    return shops, name or suchbegriff, produkt_link

        log("No shops found on Geizhals")
        return [], suchbegriff
    except Exception as e:
        log(f"Search error: {e}")
        return [], suchbegriff, ""


def _pricespy_gbp(text):
    """Extract a GBP price from text."""
    m = re.search(r"£\s*(\d{1,4}[.,]\d{2})", text)
    if m:
        try: return float(m.group(1).replace(",", "."))
        except: pass
    return None


def _pricespy_listing_laden(url, max_shops=999, prefetched_html=""):
    """Fetch a PriceSpy listing/search page (/s/slug/) and return all product variants."""
    import json as _json
    shops = []
    page_name = ""
    try:
        # Use pre-fetched HTML if provided (e.g. from Selenium search)
        html = prefetched_html
        if not html:
            # Try fast requests first — JSON-LD is in the initial HTML, no JS needed
            try:
                r = requests.get(url, headers=HEADERS, timeout=10)
                if r.status_code == 200:
                    html = r.text
                    log(f"PriceSpy listing via requests (fast): {url[:60]}")
            except Exception:
                pass
        # Fall back to Selenium only if requests failed or returned no useful data
        if not html:
            html = _selenium_get(url, wait=4)
        if not html:
            return [], page_name
        soup = BeautifulSoup(html, "html.parser")

        h1 = soup.find("h1")
        if h1:
            page_name = h1.get_text(strip=True)[:80]

        # Parse JSON-LD structured data (most reliable on PriceSpy listing pages)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = _json.loads(script.string or "")
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    t = data.get("@type", "")
                    if t == "ItemList":
                        items = [el.get("item", el) for el in data.get("itemListElement", [])]
                    else:
                        items = [data]
                for item in items:
                    if item.get("@type") != "Product":
                        continue
                    name = item.get("name", "").strip()[:80]
                    offers = item.get("offers", {})
                    if isinstance(offers, list):
                        def _op(o):
                            try: return float(str(o.get("price", 9999)).replace(",", "."))
                            except: return 9999
                        offers = min(offers, key=_op) if offers else {}
                    price_str = str(offers.get("price", "")).replace(",", ".")
                    try:
                        price = float(price_str)
                        if price <= 0: continue
                    except:
                        continue
                    link = item.get("url", "") or offers.get("url", "")
                    if link and not link.startswith("http"):
                        link = "https://pricespy.co.uk" + link
                    if name and price:
                        shops.append({
                            "name":     name,
                            "url":      link or url,
                            "preis":    price,
                            "shop_key": _shop_key_aus_name(name),
                        })
            except:
                pass

        # Fallback: extract product links + visible prices from HTML
        if not shops:
            seen = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "product.php?p=" not in href or href in seen:
                    continue
                seen.add(href)
                if not href.startswith("http"):
                    href = "https://pricespy.co.uk" + href
                node = a.parent
                for _ in range(5):
                    if node is None:
                        break
                    price = _pricespy_gbp(node.get_text(" ", strip=True))
                    if price:
                        name_el = node.find(["h2", "h3", "span"])
                        name = name_el.get_text(strip=True)[:80] if name_el else ""
                        shops.append({
                            "name":     name or href,
                            "url":      href,
                            "preis":    price,
                            "shop_key": _shop_key_aus_name(name or href),
                        })
                        break
                    node = node.parent
                if len(shops) >= max_shops:
                    break

        log(f"PriceSpy listing: {len(shops)} variants found")
        return shops[:max_shops], page_name
    except Exception as e:
        log(f"PriceSpy listing error: {e}")
        return [], page_name


def pricespy_laden(url, max_shops=999):
    """Loads all shops from a PriceSpy product page."""
    shops = []
    produkt_name = ""
    try:
        log(f"Loading PriceSpy: {url[:60]}")
        html = _selenium_get(url, wait=5)
        if not html:
            r = requests.get(url, headers=HEADERS, timeout=20)
            html = r.text
        soup = BeautifulSoup(html, "html.parser")

        # Product name
        h1 = soup.find("h1")
        if h1:
            produkt_name = h1.get_text(strip=True)[:80]

        # If no price rows found, treat as listing page — return all variants
        if not soup.find_all(class_="pj-ui-price-row"):
            if soup.find_all("a", href=lambda h: h and "product.php?p=" in h):
                log(f"PriceSpy listing page detected, loading all variants: {url[:60]}")
                return _pricespy_listing_laden(url, max_shops)

        # Parse shops from pj-ui-price-row (single product page)
        for row in soup.find_all(class_="pj-ui-price-row")[:max_shops]:
            try:
                text  = row.get_text(" ", strip=True)
                price = _pricespy_gbp(text)
                if not price: continue

                store_el = row.find(class_=re.compile("StoreInfoTitle"))
                shop_name = store_el.get_text(strip=True) if store_el else ""

                shop_url = url
                for a in row.find_all("a", href=True):
                    if "go-to-shop" in a["href"]:
                        href = a["href"]
                        if not href.startswith("http"):
                            href = "https://pricespy.co.uk" + href
                        shop_url = href
                        break

                if shop_name and price:
                    shops.append({
                        "name":     shop_name,
                        "url":      shop_url,
                        "preis":    price,
                        "shop_key": _shop_key_aus_name(shop_name),
                    })
            except: pass

        log(f"PriceSpy: {len(shops)} shops found")
        return shops, produkt_name
    except Exception as e:
        log(f"PriceSpy error: {e}")
        return [], ""


def pricespy_suchen(suchbegriff, max_shops=999):
    """Searches PriceSpy UK for all product variants matching the search term."""
    try:
        # 1. Fast path: try slug-based URL (works if term matches PriceSpy's slug format)
        slug = re.sub(r'[^a-z0-9]+', '-', suchbegriff.lower().strip()).strip('-')
        slug_url = f"https://pricespy.co.uk/s/{slug}/"
        log(f"PriceSpy: trying slug {slug_url}")
        try:
            head = requests.head(slug_url, headers=HEADERS, timeout=6, allow_redirects=True)
            if head.status_code == 200:
                shops, name = _pricespy_listing_laden(slug_url, max_shops)
                if shops:
                    return shops, name or suchbegriff, slug_url
        except Exception:
            pass

        # 2. Fallback: Amazon.co.uk (reliable, GBP prices)
        log(f"PriceSpy slug not found — falling back to Amazon.co.uk for '{suchbegriff}'")
        shops, name = _amazon_co_uk_suchen(suchbegriff)
        if shops:
            return shops, name or suchbegriff, ""
        return [], suchbegriff, ""
    except Exception as e:
        log(f"PriceSpy search error: {e}")
        return [], suchbegriff, ""


def _amazon_co_uk_suchen(suchbegriff):
    """Searches Amazon.co.uk for a product — returns GBP price."""
    try:
        url = "https://www.amazon.co.uk/s?k={}".format(requests.utils.quote(suchbegriff))
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for el in soup.select("[data-asin]:not([data-asin=''])"):
            asin = el.get("data-asin", "").strip()
            if not asin or len(asin) < 5: continue
            preis_el = el.select_one(".a-price .a-offscreen, .a-price-whole")
            preis = _pricespy_gbp(preis_el.get_text()) if preis_el else None
            if not preis:
                preis = _parse(preis_el.get_text()) if preis_el else None
            titel_el = el.select_one("h2 span, .a-text-normal")
            titel = titel_el.get_text(strip=True)[:60] if titel_el else suchbegriff
            if asin and preis:
                produkt_url = f"https://www.amazon.co.uk/dp/{asin}"
                return [{"name": "Amazon.co.uk", "url": produkt_url,
                         "preis": preis, "shop_key": "amazon_uk",
                         "shop_name": "Amazon.co.uk"}], titel
        return [], suchbegriff
    except Exception as e:
        log(f"Amazon.co.uk search error: {e}")
        return [], suchbegriff


def amazon_suchen(suchbegriff):
    """Searches Amazon.de for a product and returns its direct URL."""
    try:
        url = "https://www.amazon.de/s?k={}".format(requests.utils.quote(suchbegriff))
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for el in soup.select("[data-asin]:not([data-asin=''])"):
            asin = el.get("data-asin","").strip()
            if not asin or len(asin) < 5: continue
            preis_el = el.select_one(".a-price .a-offscreen, .a-price-whole")
            preis = _parse(preis_el.get_text()) if preis_el else None
            titel_el = el.select_one("h2 span, .a-text-normal")
            titel = titel_el.get_text(strip=True)[:60] if titel_el else suchbegriff
            if asin and preis:
                produkt_url = f"https://www.amazon.de/dp/{asin}"
                return [{"name": "Amazon.de", "url": produkt_url,
                         "preis": preis, "shop_key": "amazon",
                         "shop_name": "Amazon.de"}], titel
        return [], suchbegriff
    except Exception as e:
        log(f"Amazon search error: {e}")
        return [], suchbegriff


def _amazon_locale_suchen(suchbegriff, domain):
    """Search Amazon on the given domain (e.g. amazon.co.uk) and return one result."""
    try:
        url = f"https://www.{domain}/s?k={requests.utils.quote(suchbegriff)}"
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for el in soup.select("[data-asin]:not([data-asin=''])"):
            asin = el.get("data-asin", "").strip()
            if not asin or len(asin) < 5: continue
            preis_el = el.select_one(".a-price .a-offscreen, .a-price-whole")
            preis = _parse(preis_el.get_text()) if preis_el else None
            if not preis: continue
            titel_el = el.select_one("h2 span, .a-text-normal")
            titel = titel_el.get_text(strip=True)[:60] if titel_el else suchbegriff
            name = "Amazon." + domain.split("amazon.")[-1]
            produkt_url = f"https://www.{domain}/dp/{asin}"
            return [{"name": name, "url": produkt_url,
                     "preis": preis, "shop_key": "amazon", "shop_name": name}], titel
        return [], suchbegriff
    except Exception as e:
        log(f"Amazon {domain} search error: {e}")
        return [], suchbegriff


def _pricespy_slug_candidates(suchbegriff):
    """Generate slug candidates by splitting at digit/letter boundaries and permuting."""
    import itertools
    tokens = re.findall(r'[a-z]+|\d+', suchbegriff.lower())
    if not tokens:
        return []
    seen = set()
    candidates = []
    for perm in itertools.permutations(tokens[:5]):
        slug = '-'.join(perm)
        if slug not in seen:
            seen.add(slug)
            candidates.append(slug)
    return candidates


def region_suchen(suchbegriff, region_key, max_shops=999):
    """Main search function — dispatches based on region."""
    import concurrent.futures
    r = REGIONS.get(region_key, REGIONS["de"])
    engine = r["engine"]
    log(f"Region search: region={region_key} engine={engine} term='{suchbegriff}'")

    if engine == "geizhals":
        return geizhals_suchen(suchbegriff, max_shops)

    elif engine == "pricespy":
        domain = r["ps_domain"]
        candidates = _pricespy_slug_candidates(suchbegriff)
        log(f"PriceSpy: checking {len(candidates)} slug permutations on {domain}")

        def _head_check(slug):
            url = f"https://{domain}/s/{slug}/"
            try:
                resp = requests.head(url, headers=HEADERS, timeout=5, allow_redirects=True)
                return url if resp.status_code == 200 else None
            except Exception:
                return None

        found_url = None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(_head_check, s) for s in candidates]
            for fut in concurrent.futures.as_completed(futures):
                result = fut.result()
                if result:
                    found_url = result
                    break

        if found_url:
            log(f"PriceSpy: slug match → {found_url}")
            shops, name = _pricespy_listing_laden(found_url, max_shops)
            if shops:
                return shops, name or suchbegriff, found_url

        amz = r.get("amz")
        if amz:
            log(f"PriceSpy: no slug matched — falling back to {amz}")
            shops, name = _amazon_locale_suchen(suchbegriff, amz)
            if shops:
                return shops, name, ""
        return [], suchbegriff, ""

    elif engine == "amazon":
        amz = r.get("amz", "amazon.de")
        shops, name = _amazon_locale_suchen(suchbegriff, amz)
        return shops, name, ""

    return [], suchbegriff, ""


def alle_quellen_suchen(suchbegriff, max_shops=999):
    """Main entry: searches on all sources."""
    return geizhals_suchen(suchbegriff, max_shops)


APP_VERSION = "1.8.6"
GITHUB_API  = "https://api.github.com/repos/erdem-basar/price-alert-tracker/releases/latest"

def check_for_update():
    """Checks GitHub for a newer version. Returns (new_version, release_url, zip_url) or (None, None, None)."""
    try:
        r = requests.get(GITHUB_API, timeout=8,
                         headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 404:
            return None, None, None, None  # No releases yet
        if r.status_code == 200:
            data = r.json()
            latest   = data.get("tag_name","").lstrip("v").lstrip(".").strip()
            html_url = data.get("html_url","")
            zip_url  = data.get("zipball_url","")
            log(f"Update check: GitHub={latest} Local={APP_VERSION}")
            # Prefer Inno Setup installer, then direct EXE, then ZIP
            direct_exe_url = None
            for asset in data.get("assets", []):
                name = asset["name"]
                url  = asset["browser_download_url"]
                if name.startswith("PreisAlarm_Setup") and name.endswith(".exe"):
                    zip_url = url
                    direct_exe_url = None
                    break
                if name == "PreisAlarm.exe":
                    direct_exe_url = url
                elif name.endswith(".zip") and not direct_exe_url:
                    zip_url = url
            if direct_exe_url:
                zip_url = direct_exe_url
            notes = data.get("body", "No release notes available.")
            if latest and latest != APP_VERSION:
                # Only update if remote version is actually newer
                try:
                    def ver_tuple(v):
                        return tuple(int(x) for x in v.strip().split("."))
                    if ver_tuple(latest) > ver_tuple(APP_VERSION):
                        return latest, html_url, zip_url, notes
                except:
                    if latest != APP_VERSION:
                        return latest, html_url, zip_url, notes
            log(f"Update check: no update needed ({latest} <= {APP_VERSION})")
    except:
        pass
    return None, None, None, None


def email_preisaenderung(cfg, gruppe, geaenderte_shops):
    """Sends email with all shops that changed their price."""
    try:
        zeilen = ""
        for s in geaenderte_shops:
            name     = s["shop_name"]
            url      = s["url"]
            alt      = s["preis_alt"]
            neu      = s["preis_neu"]
            diff     = neu - alt
            pfeil    = "⬇" if diff < 0 else "⬆"
            farbe    = "#22c55e" if diff < 0 else "#ef4444"
            zeilen += f"""
            <tr>
              <td style="padding:10px;color:#f1f5f9;border-bottom:1px solid #2d2d2d">{name}</td>
              <td style="padding:10px;color:#94a3b8;border-bottom:1px solid #2d2d2d">{alt:.2f} €</td>
              <td style="padding:10px;font-weight:bold;color:{farbe};border-bottom:1px solid #2d2d2d">{neu:.2f} €</td>
              <td style="padding:10px;color:{farbe};border-bottom:1px solid #2d2d2d">{pfeil} {abs(diff):.2f} €</td>
              <td style="padding:10px;border-bottom:1px solid #2d2d2d">
                <a href="{url}" style="color:#378ADD;text-decoration:none">Open Shop</a>
              </td>
            </tr>"""

        from datetime import datetime as _dt
        html = f"""<html><body style="font-family:Arial;max-width:700px;margin:auto;
                   background:#0f0f0f;color:#f1f5f9;padding:24px">
        <div style="background:#1a3a5c;padding:16px;border-radius:8px;margin-bottom:20px">
          <h2 style="color:#60a5fa;margin:0">📊 Price Changes: {gruppe['name']}</h2>
          <p style="color:#94a3b8;margin:4px 0 0">{len(geaenderte_shops)} shop(s) changed their price</p>
        </div>
        <table style="width:100%;border-collapse:collapse">
          <tr style="background:#1a1a1a">
            <th style="padding:10px;text-align:left;color:#94a3b8">Shop</th>
            <th style="padding:10px;text-align:left;color:#94a3b8">Old Price</th>
            <th style="padding:10px;text-align:left;color:#94a3b8">New Price</th>
            <th style="padding:10px;text-align:left;color:#94a3b8">Change</th>
            <th style="padding:10px;text-align:left;color:#94a3b8">Link</th>
          </tr>
          {zeilen}
        </table>
        <p style="color:#6b7280;font-size:12px;margin-top:20px">
          Preis-Alarm Tracker · {_dt.now().strftime('%d.%m.%Y %H:%M')}
        </p>
        </body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 Price Changes: {gruppe['name']} ({len(geaenderte_shops)} shops)"
        msg["From"]    = formataddr(("Price Alert", cfg["email_absender"]))
        msg["To"]      = cfg["email_empfaenger"]
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as s:
            s.starttls()
            s.login(cfg["email_absender"], cfg["email_passwort"])
            s.sendmail(cfg["email_absender"], cfg["email_empfaenger"], msg.as_string())
        log(f"  Price change email sent ({len(geaenderte_shops)} Shops)")
        return True
    except Exception as e:
        log(f"  Email error: {e}")
        return False


def email_zusammenfassung(cfg, alle_aenderungen, alarme):
    """Sendet eine einzige zusammengefasste Mail nach dem Check."""
    try:
        from datetime import datetime as _dt
        hat_aenderungen = any(g["shops"] for g in alle_aenderungen)
        hat_alarme      = bool(alarme)
        if not hat_aenderungen and not hat_alarme:
            return

        # Use current language for email
        alarm_anzahl  = len(alarme)
        aender_anzahl = sum(len(g["shops"]) for g in alle_aenderungen)

        s_a  = "" if alarm_anzahl  == 1 else "s"
        s_m  = "" if aender_anzahl == 1 else "s"

        if hat_alarme:
            betreff = (T("email_subject_alarm")
                       .replace("{n}", str(alarm_anzahl)).replace("{s}", s_a)
                       .replace("{m}", str(aender_anzahl)).replace("{ms}", s_m))
        else:
            betreff = (T("email_subject_changes")
                       .replace("{n}", str(aender_anzahl)).replace("{s}", s_m))

        # Alarm section
        alarm_html = ""
        if hat_alarme:
            alarm_zeilen = ""
            for a in alarme:
                g_cur = a.get("currency","€")
                alarm_zeilen += f"""
                <tr>
                  <td style="padding:10px;color:#f1f5f9;font-weight:bold">{a['name']}</td>
                  <td style="padding:10px;color:#22c55e;font-size:18px;font-weight:bold">{g_cur}{a['bester']:.2f}</td>
                  <td style="padding:10px;color:#f1f5f9">{a['shop']}</td>
                </tr>"""
            alarm_html = f"""
            <div style="background:#14532d;border-radius:8px;padding:16px;margin-bottom:20px">
              <h2 style="color:#4ade80;margin:0 0 12px">{T("email_target_reached")}</h2>
              <table style="width:100%;border-collapse:collapse">
                <tr style="background:#166534">
                  <th style="padding:8px;text-align:left;color:#86efac">{T("email_product")}</th>
                  <th style="padding:8px;text-align:left;color:#86efac">{T("email_best_price")}</th>
                  <th style="padding:8px;text-align:left;color:#86efac">{T("email_shop")}</th>
                </tr>
                {alarm_zeilen}
              </table>
            </div>"""

        # Price changes per group
        aender_html = ""
        for gruppe in alle_aenderungen:
            if not gruppe["shops"]: continue
            ziel  = gruppe["zielpreis"]
            zeilen = ""
            for s in gruppe["shops"]:
                diff   = s["preis_neu"] - s["preis_alt"]
                pfeil  = "⬇" if diff < 0 else "⬆"
                f_diff = "#22c55e" if diff < 0 else "#f87171"
                ziel_badge = ""
                if s.get("ziel_erreicht"):
                    ziel_badge = f'<span style="background:#14532d;color:#4ade80;padding:2px 8px;border-radius:4px;font-size:11px;margin-left:6px">{T("email_target_badge")}</span>'
                zeilen += f"""
                <tr style="{'background:#1a2e1a' if s.get('ziel_erreicht') else ''}">
                  <td style="padding:10px;color:#f1f5f9;border-bottom:1px solid #2d2d2d">
                    {s['shop_name']}{ziel_badge}
                  </td>
                  <td style="padding:10px;color:#94a3b8;border-bottom:1px solid #2d2d2d">{s['preis_alt']:.2f} €</td>
                  <td style="padding:10px;font-weight:bold;color:{f_diff};border-bottom:1px solid #2d2d2d">
                    {s['preis_neu']:.2f} € &nbsp;{pfeil} {abs(diff):.2f} €
                  </td>
                  <td style="padding:10px;border-bottom:1px solid #2d2d2d">
                    <a href="{s['url']}" style="color:#60a5fa;text-decoration:none">{T("email_shop_link")}</a>
                  </td>
                </tr>"""

            aender_html += f"""
            <div style="margin-bottom:20px">
              <h3 style="color:#f1f5f9;margin:0 0 8px">{gruppe['gruppe_name']}
                <span style="color:#6b7280;font-size:12px;font-weight:normal;margin-left:8px">
                  {T("email_target_lbl")}: {ziel:.2f} €
                </span>
              </h3>
              <table style="width:100%;border-collapse:collapse;background:#1a1a1a;border-radius:8px">
                <tr style="background:#242424">
                  <th style="padding:8px;text-align:left;color:#94a3b8">{T("email_shop")}</th>
                  <th style="padding:8px;text-align:left;color:#94a3b8">{T("email_old_price")}</th>
                  <th style="padding:8px;text-align:left;color:#94a3b8">{T("email_new_price")}</th>
                  <th style="padding:8px;text-align:left;color:#94a3b8">{T("email_link")}</th>
                </tr>
                {zeilen}
              </table>
            </div>"""

        html = f"""<html><body style="font-family:Arial;max-width:700px;margin:auto;
                   background:#0f0f0f;color:#f1f5f9;padding:24px">
          <div style="border-bottom:1px solid #2d2d2d;padding-bottom:12px;margin-bottom:20px">
            <h1 style="color:#f1f5f9;margin:0;font-size:20px">🔔 Price Alert Tracker</h1>
            <p style="color:#6b7280;margin:4px 0 0;font-size:12px">
              {_dt.now().strftime('%d.%m.%Y %H:%M')}
            </p>
          </div>
          {alarm_html}
          {(f'<h2 style="color:#f1f5f9;margin:0 0 16px">{T("email_price_changes")}</h2>' + aender_html) if hat_aenderungen else ''}
          <p style="color:#4b5563;font-size:11px;margin-top:24px;border-top:1px solid #1f2937;padding-top:12px">
            Price Alert Tracker · {T("email_auto_check")}
          </p>
        </body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = betreff
        msg["From"]    = formataddr(("Price Alert", cfg["email_absender"]))
        msg["To"]      = cfg["email_empfaenger"]
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as s:
            s.starttls()
            s.login(cfg["email_absender"], cfg["email_passwort"])
            s.sendmail(cfg["email_absender"], cfg["email_empfaenger"], msg.as_string())
        log(f"Summary email sent ({aender_anzahl} Änderungen, {alarm_anzahl} Alarme)")
    except Exception as e:
        log(f"Email error: {e}")


def email_wochenbericht(cfg, vergleiche):
    """Sendet eine wöchentliche Zusammenfassung aller verfolgten Produkte."""
    try:
        from datetime import datetime as _dt
        if not vergleiche or not cfg.get("email_absender"):
            return

        alarm_produkte = []
        normal_produkte = []

        for g in vergleiche:
            shops_mit_preis = [s for s in g.get("shops", []) if s.get("preis")]
            if not shops_mit_preis:
                continue
            bester_shop = min(shops_mit_preis, key=lambda s: s["preis"])
            bester_preis = bester_shop["preis"]
            ziel = g.get("zielpreis", 0)
            cur  = g.get("currency", "€")
            ziel_erreicht = bool(ziel) and bester_preis <= ziel
            diff_pct = ((bester_preis - ziel) / ziel * 100) if ziel else 0
            eintrag = {
                "name":          g["name"],
                "preis":         bester_preis,
                "shop_name":     bester_shop.get("shop_name", ""),
                "url":           bester_shop.get("url", ""),
                "ziel":          ziel,
                "cur":           cur,
                "ziel_erreicht": ziel_erreicht,
                "diff_pct":      diff_pct,
            }
            if ziel_erreicht:
                alarm_produkte.append(eintrag)
            else:
                normal_produkte.append(eintrag)

        normal_produkte.sort(key=lambda x: x["diff_pct"])
        alle = alarm_produkte + normal_produkte
        if not alle:
            log("Digest: keine Produkte mit Preisen — nicht gesendet")
            return

        def tabellenzeile(e, alarm=False):
            bg       = "#1a2e1a" if alarm else ""
            preis_fg = "#22c55e" if alarm else "#f1f5f9"
            diff_txt = ""
            if e["ziel"]:
                if alarm:
                    diff_txt = f'<span style="color:#4ade80">✅ {T("digest_alarms")}</span>'
                else:
                    diff_txt = f'+{e["diff_pct"]:.1f}%'
            return f"""
            <tr style="{'background:' + bg if bg else ''}">
              <td style="padding:10px;color:#f1f5f9;border-bottom:1px solid #2d2d2d">{e['name']}</td>
              <td style="padding:10px;color:{preis_fg};font-weight:bold;border-bottom:1px solid #2d2d2d">{e['cur']}{e['preis']:.2f}</td>
              <td style="padding:10px;color:#94a3b8;border-bottom:1px solid #2d2d2d">{e['cur']}{e['ziel']:.2f if e['ziel'] else '—'}</td>
              <td style="padding:10px;color:#94a3b8;border-bottom:1px solid #2d2d2d">{diff_txt}</td>
              <td style="padding:10px;border-bottom:1px solid #2d2d2d">
                <a href="{e['url']}" style="color:#60a5fa;text-decoration:none">{e['shop_name']}</a>
              </td>
            </tr>"""

        zeilen = "".join(tabellenzeile(e, e["ziel_erreicht"]) for e in alle)
        tabellen_kopf = f"""
        <tr style="background:#1e293b">
          <th style="padding:8px;text-align:left;color:#94a3b8">{T("digest_col_product")}</th>
          <th style="padding:8px;text-align:left;color:#94a3b8">{T("digest_col_price")}</th>
          <th style="padding:8px;text-align:left;color:#94a3b8">{T("digest_col_target")}</th>
          <th style="padding:8px;text-align:left;color:#94a3b8">{T("digest_col_diff")}</th>
          <th style="padding:8px;text-align:left;color:#94a3b8">{T("digest_col_shop")}</th>
        </tr>"""

        alarm_badge = ""
        if alarm_produkte:
            alarm_badge = f"""
            <div style="background:#14532d;border-radius:6px;padding:8px 14px;margin-bottom:16px;display:inline-block">
              <span style="color:#4ade80;font-weight:bold">🔔 {len(alarm_produkte)} × {T("digest_alarms")}</span>
            </div>"""

        html = f"""<html><body style="font-family:Arial;max-width:750px;margin:auto;
                   background:#0f0f0f;color:#f1f5f9;padding:24px">
          <div style="border-bottom:1px solid #2d2d2d;padding-bottom:12px;margin-bottom:20px">
            <h1 style="color:#f1f5f9;margin:0;font-size:20px">📊 Price Alert Tracker</h1>
            <p style="color:#6b7280;margin:4px 0 0;font-size:12px">
              {T("digest_title")} · {_dt.now().strftime('%d.%m.%Y %H:%M')}
            </p>
          </div>
          {alarm_badge}
          <table style="width:100%;border-collapse:collapse">
            {tabellen_kopf}
            {zeilen}
          </table>
          <p style="color:#4b5563;font-size:11px;margin-top:24px;border-top:1px solid #1f2937;padding-top:12px">
            {T("digest_footer")}
          </p>
        </body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = T("digest_subject")
        msg["From"]    = formataddr(("Price Alert", cfg["email_absender"]))
        msg["To"]      = cfg["email_empfaenger"]
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as s:
            s.starttls()
            s.login(cfg["email_absender"], cfg["email_passwort"])
            s.sendmail(cfg["email_absender"], cfg["email_empfaenger"], msg.as_string())
        log(f"Wöchentlicher Bericht gesendet ({len(alle)} Produkte)")
    except Exception as e:
        log(f"Digest-Email Fehler: {e}")


def email_senden(cfg, gruppe, bester_preis, bester_shop):
    try:
        alle = "".join(
            f"<tr><td style='padding:8px;color:#94a3b8'>{s.get('shop_name') or SHOPS.get(s['shop'],s['shop'])}</td>"
            f"<td style='padding:8px;{'font-weight:bold;color:#22c55e' if s.get('preis')==bester_preis else ''}'>"
            f"{s.get('preis',0):.2f} €</td>"
            f"<td><a href='{s['url']}' style='color:#378ADD'>Shop</a></td></tr>"
            for s in gruppe.get("shops",[]) if s.get("preis")
        )
        html = f"""<html><body style="font-family:Arial;max-width:600px;margin:auto;background:#0f0f0f;color:#f1f5f9;padding:24px">
        <h2 style="color:#4ade80">🏆 Preisvergleich-Alarm!</h2>
        <h3>{gruppe['name']}</h3>
        <p>Best Price: <strong style="color:#22c55e;font-size:20px">{bester_preis:.2f} €</strong> bei {bester_shop}</p>
        <table style="width:100%;border-collapse:collapse">{alle}</table>
        <p style="color:#6b7280;font-size:12px">{datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        </body></html>"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🏆 {gruppe['name']} from {gruppe.get('currency','€')}{bester_preis:.2f}"
        msg["From"]    = formataddr(("Price Alert", cfg["email_absender"]))
        msg["To"]      = cfg["email_empfaenger"]
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as s:
            s.starttls()
            s.login(cfg["email_absender"], cfg["email_passwort"])
            s.sendmail(cfg["email_absender"], cfg["email_empfaenger"], msg.as_string())
        return True
    except Exception as e:
        log(f"Email error: {e}")
        return False

# ── Autostart & Tray ─────────────────────────────────────────────────────────
import winreg

AUTOSTART_KEY  = "Software\\Microsoft\\Windows\\CurrentVersion\\Run"
AUTOSTART_NAME = "PreisAlarmTracker"

def autostart_aktiv():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, AUTOSTART_NAME)
        winreg.CloseKey(key)
        return True
    except:
        return False

def autostart_setzen(aktiv):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        if aktiv:
            # pythonw.exe nutzen damit kein CMD-Fenster erscheint
            exe = sys.executable.replace("python.exe", "pythonw.exe")
            if not Path(exe).exists():
                exe = sys.executable  # Fallback
            script = str(Path(__file__).resolve())
            pfad = f'"{exe}" "{script}"' 
            winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ, pfad)
            log(f"Autostart set: {pfad}")
        else:
            try: winreg.DeleteValue(key, AUTOSTART_NAME)
            except: pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        log(f"Autostart error: {e}")
        return False

def tray_icon_erstellen():
    """Creates a proper bell icon for the tray."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    # Dark background circle
    d.ellipse([0, 0, size-1, size-1], fill="#1a1a1a")
    # Bell body
    d.ellipse([10, 12, 54, 46], fill="#22c55e")
    # Bell bottom flat
    d.rectangle([10, 28, 54, 46], fill="#22c55e")
    # Bell clapper
    d.ellipse([24, 44, 40, 56], fill="#22c55e")
    # Bell top stem
    d.rectangle([28, 4, 36, 14], fill="#22c55e")
    d.ellipse([24, 2, 40, 16], fill="#22c55e")
    # Shine effect
    d.ellipse([14, 14, 28, 26], fill="#4ade80")
    return img


def app_icon_erstellen():
    """Creates the window icon (32x32)."""
    size = 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    d.ellipse([0, 0, size-1, size-1], fill="#1a1a1a")
    d.ellipse([5, 6, 27, 23], fill="#22c55e")
    d.rectangle([5, 14, 27, 23], fill="#22c55e")
    d.ellipse([12, 22, 20, 28], fill="#22c55e")
    d.rectangle([14, 2, 18, 8], fill="#22c55e")
    d.ellipse([12, 1, 20, 9], fill="#22c55e")
    return img


def _geometry_auf_monitor(geo_str):
    """Prüft ob die gespeicherte Fensterposition auf einem der vorhandenen Monitore liegt.
    Gibt True zurück wenn sichtbar, False wenn außerhalb aller Monitore."""
    try:
        m = re.match(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', geo_str)
        if not m:
            return False
        w, h = int(m.group(1)), int(m.group(2))
        x, y = int(m.group(3)), int(m.group(4))
        # Fenstermittelpunkt berechnen
        cx, cy = x + w // 2, y + h // 2
        import ctypes
        user32 = ctypes.windll.user32
        # MONITOR_DEFAULTTONULL = 0: gibt NULL zurück wenn Punkt auf keinem Monitor
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT(cx, cy)
        monitor = user32.MonitorFromPoint(pt, 0)
        return monitor != 0
    except:
        return True  # Im Fehlerfall annehmen dass Position gültig ist

# ── GUI ───────────────────────────────────────────────────────────────────────
class PreisAlarmApp(tk.Tk):
    def _center_dialog(self, dlg, w, h):
        """Position dialog centered on the main window (works with multiple monitors)."""
        self.update_idletasks()
        dlg.update_idletasks()
        # Get main window position
        x = self.winfo_x() + (self.winfo_width()  - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

    def __init__(self):
        super().__init__()
        # Load config FIRST so geometry can be restored
        self.vergleiche  = lade_vergleiche()
        self.config_data = lade_config()
        self.title(T("app_title"))
        # Restore last window position/size — nur wenn Position auf einem Monitor liegt
        geo = self.config_data.get("window_geometry", "960x680")
        try:
            # Prüfe ob gespeicherte Größe zu groß ist (z.B. gespeichert im maximierten Zustand)
            m = re.match(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', geo)
            if m:
                try:
                    import ctypes
                    # Hole Monitor-Info für die gespeicherte Position
                    class POINT(ctypes.Structure):
                        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
                    class MONITORINFO(ctypes.Structure):
                        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", ctypes.c_long*4),
                                    ("rcWork", ctypes.c_long*4), ("dwFlags", ctypes.c_ulong)]
                    pt = POINT(int(m.group(3)), int(m.group(4)))
                    hmon = ctypes.windll.user32.MonitorFromPoint(pt, 2)  # DEFAULTTONEAREST
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)
                    ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
                    mon_w = mi.rcMonitor[2] - mi.rcMonitor[0]
                    mon_h = mi.rcMonitor[3] - mi.rcMonitor[1]
                    if int(m.group(1)) >= mon_w * 0.95 or int(m.group(2)) >= mon_h * 0.95:
                        geo = "960x680"
                except:
                    pass
            if _geometry_auf_monitor(geo):
                self.geometry(geo)
                self.update_idletasks()
                self.geometry(geo)
            else:
                self.geometry("960x680")  # Fallback: Standardgröße, zentriert auf Monitor 1
        except:
            self.geometry("960x680")
        # Fenster-Zustand wiederherstellen (maximiert?)
        if self.config_data.get("window_state") == "zoomed":
            self.after(10, lambda: self.state("zoomed"))
        self.minsize(800, 560)
        self.configure(bg=BG)
        # Save position on close (most reliable)
        self._geo_save_job = None
        def _save_geo(e=None):
            if self._geo_save_job:
                self.after_cancel(self._geo_save_job)
            self._geo_save_job = self.after(1000, _do_save)
        def _do_save():
            try:
                st = self.state()
                self.config_data["window_state"] = st
                # Geometry nur speichern wenn nicht maximiert — sonst würde Vollbild-Größe gespeichert
                if st not in ("zoomed", "fullscreen"):
                    g = self.geometry()
                    if g and "+" in g:
                        self.config_data["window_geometry"] = g
                speichere_config(self.config_data)
            except: pass
        self.bind("<Configure>", _save_geo)
        self._vg_shop_vars      = {}
        self.vg_aktuelle_gruppe = None
        self._setup_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._fenster_schliessen)
        # Set window icon
        try:
            icon_path = _resource_path("icon.ico")
            if icon_path.exists():
                self.iconbitmap(str(icon_path))
            elif TRAY_OK:
                icon_img = app_icon_erstellen()
                from PIL import ImageTk
                self._tk_icon = ImageTk.PhotoImage(icon_img)
                self.iconphoto(True, self._tk_icon)
        except: pass
        self._tray_icon = None
        self._tray_thread = None
        # Automatische Preisprüfung + Clipboard Monitor starten
        self._auto_check_starten()
        self._digest_scheduler_starten()
        self._clipboard_monitor_starten()

    # ── Hilfsmethoden ─────────────────────────────────────────────────────────
    def _btn(self, parent, text, cmd, bg=BG3, fg=TEXT):
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                         activebackground=bg, activeforeground=fg,
                         font=(UI_FONT, 10), relief="flat", cursor="hand2",
                         padx=14, pady=6, bd=0)

    def _aktuelle_vg(self):
        return next((g for g in self.vergleiche if g["id"] == self.vg_aktuelle_gruppe), None)

    # ── Style ──────────────────────────────────────────────────────────────────
    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, fieldbackground=BG3,
                    bordercolor=BORDER, troughcolor=BG2,
                    selectbackground=AKZENT, selectforeground="#000", font=(UI_FONT, 10))
        s.configure("Treeview", background=BG2, foreground=TEXT, fieldbackground=BG2,
                    rowheight=36, borderwidth=0, font=(UI_FONT, 10))
        s.configure("Treeview.Heading", background=BG3, foreground=TEXT2, relief="flat",
                    font=(UI_FONT, 9, "bold"), padding=[8, 10])
        s.map("Treeview",
              background=[("selected", BG3)],
              foreground=[("selected", AKZENT)])
        s.configure("TNotebook", background=BG2, borderwidth=0, tabmargins=[0,0,0,0])
        s.configure("TNotebook.Tab", background=BG2, foreground=GRAU,
                    padding=[20, 10], font=(UI_FONT, 10),
                    borderwidth=0, relief="flat")
        s.map("TNotebook.Tab",
              background=[("selected", BG2), ("active", BG2)],
              foreground=[("selected", TEXT), ("active", TEXT2)],
              expand=[("selected", [0, 0, 0, 0])])
        s.configure("TEntry", fieldbackground=BG3, foreground=TEXT, insertcolor=AKZENT,
                    bordercolor=BORDER, relief="flat", padding=8)
        s.configure("TCombobox", fieldbackground=BG3, foreground=TEXT,
                    selectbackground=AKZENT, selectforeground=BG,
                    arrowcolor=TEXT2, insertcolor=TEXT)
        s.map("TCombobox",
              fieldbackground=[("readonly", BG3)],
              foreground=[("readonly", TEXT)],
              selectbackground=[("readonly", BG3)],
              selectforeground=[("readonly", TEXT)])
        s.configure("TScrollbar", background=BG2, troughcolor=BG,
                    arrowcolor=GRAU, borderwidth=0, relief="flat")
        s.map("TScrollbar", background=[("active", BG3)])

    # ── Haupt-UI ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Top accent bar
        tk.Frame(self, bg=AKZENT, height=2).pack(fill="x")

        # Header
        hdr = tk.Frame(self, bg=BG2)
        hdr.pack(fill="x")
        inner_hdr = tk.Frame(hdr, bg=BG2)
        inner_hdr.pack(fill="x", padx=24, pady=12)

        # Logo + title
        logo_f = tk.Frame(inner_hdr, bg=BG2)
        logo_f.pack(side="left")
        tk.Label(logo_f, text="🔔", bg=BG2, fg=AKZENT,
                 font=(UI_FONT, 20)).pack(side="left", padx=(0,10))
        title_f = tk.Frame(logo_f, bg=BG2)
        title_f.pack(side="left")
        tk.Label(title_f, text=T("app_title"), bg=BG2, fg=TEXT,
                 font=(UI_FONT, 16, "bold")).pack(anchor="w")
        tk.Label(title_f, text=T("subtitle"), bg=BG2, fg=GRAU,
                 font=(UI_FONT, 8)).pack(anchor="w")

        # Version badge
        ver_f = tk.Frame(inner_hdr, bg=BG3, cursor="hand2")
        ver_f.pack(side="left", padx=16)
        self.update_lbl = tk.Label(ver_f, text=f"v{APP_VERSION}", bg=BG3, fg=GRAU,
                                   font=(UI_FONT, 8, "bold"), padx=8, pady=3,
                                   cursor="hand2")
        self.update_lbl.pack()
        ver_f.bind("<Button-1>", lambda e: self._update_pruefen())
        self.update_lbl.bind("<Button-1>", lambda e: self._update_pruefen())

        # Separator
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Check for update in background after 3s
        self.after(3000, lambda: threading.Thread(target=self._update_check_bg, daemon=True).start())

        # Chrome-style custom tab bar
        tab_bar = tk.Frame(self, bg=BG2)
        tab_bar.pack(fill="x")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Tab content frames
        self.tab_vergleich = tk.Frame(self, bg=BG)
        self.tab_einst     = tk.Frame(self, bg=BG)
        self.tab_log       = tk.Frame(self, bg=BG)

        self._active_tab = [None]
        self._tab_btns   = {}

        def switch_tab(frame, btn_key):
            for f in [self.tab_vergleich, self.tab_einst, self.tab_log]:
                f.pack_forget()
            frame.pack(fill="both", expand=True)
            # Update tab indicators
            for key, (btn, ind) in self._tab_btns.items():
                if key == btn_key:
                    btn.config(fg=TEXT)
                    ind.config(bg=AKZENT)
                else:
                    btn.config(fg=GRAU)
                    ind.config(bg=BG2)
            self._active_tab[0] = btn_key

        tabs = [
            ("compare", T("tab_compare"), self.tab_vergleich),
            ("settings",T("tab_settings"),          self.tab_einst),
            ("log",     T("tab_log"),              self.tab_log),
        ]
        for key, label, frame in tabs:
            col = tk.Frame(tab_bar, bg=BG2)
            col.pack(side="left")
            btn = tk.Button(col, text=label, bg=BG2, fg=GRAU,
                            font=(UI_FONT, 10), relief="flat",
                            cursor="hand2", borderwidth=0,
                            activebackground=BG2, activeforeground=TEXT,
                            padx=4, pady=10,
                            command=lambda f=frame, k=key: switch_tab(f, k))
            btn.pack()
            ind = tk.Frame(col, bg=BG2, height=2)
            ind.pack(fill="x")
            self._tab_btns[key] = (btn, ind)

        self._tab_vergleich()
        self._tab_einstellungen()
        self._tab_log()
        switch_tab(self.tab_vergleich, "compare")

    # ── Tab: Preisvergleich ───────────────────────────────────────────────────
    def _tab_vergleich(self):
        f = self.tab_vergleich
        bar = tk.Frame(f, bg=BG2)
        bar.pack(fill="x")
        tk.Frame(f, bg=BORDER, height=1).pack(fill="x")
        inner_bar = tk.Frame(bar, bg=BG2)
        inner_bar.pack(fill="x", padx=16, pady=10)
        self._btn(inner_bar, T("new_group"), self._vg_neu, AKZENT, "#000").pack(side="left", padx=(0,6))
        self._btn(inner_bar, "📁 " + T("new_category"), self._kategorie_neu, BG3, TEXT2).pack(side="left", padx=(0,6))
        self.btn_pruefen = self._btn(inner_bar, T("check_all"), self._vg_alle_pruefen, BG3, TEXT)
        self.btn_pruefen.pack(side="left", padx=(0,6))
        self.status_check_lbl = tk.Label(inner_bar, text="", bg=BG2, fg=TEXT2, font=(UI_FONT, 9))
        self.status_check_lbl.pack(side="left", padx=10)
        self._btn(inner_bar, T("delete"), self._vg_loeschen, BG3, ROT).pack(side="right")
        self.countdown_lbl = tk.Label(inner_bar, text="", bg=BG2, fg=GRAU, font=(UI_FONT, 8))
        self.countdown_lbl.pack(side="right", padx=12)

        pane = tk.Frame(f, bg=BG)
        pane.pack(fill="both", expand=True)

        left = tk.Frame(pane, bg=BG2, width=230)
        left.pack(side="left", fill="y", padx=(0,1))
        left.pack_propagate(False)
        lbl_f = tk.Frame(left, bg=BG2)
        lbl_f.pack(fill="x", padx=12, pady=(12,6))
        tk.Label(lbl_f, text=T("product_groups"), bg=BG2, fg=GRAU,
                 font=(UI_FONT, 8, "bold")).pack(side="left")
        # Listbox with scrollbar
        lb_frame = tk.Frame(left, bg=BG2)
        lb_frame.pack(fill="both", expand=True)
        lb_sb = ttk.Scrollbar(lb_frame, orient="vertical")
        lb_sb.pack(side="right", fill="y")
        self.vg_listbox = tk.Listbox(
            lb_frame, bg=BG2, fg=TEXT, selectbackground=BG3,
            selectforeground=AKZENT,
            font=(UI_FONT, 10), relief="flat", borderwidth=0, activestyle="none",
            highlightthickness=0, yscrollcommand=lb_sb.set)
        self.vg_listbox.pack(side="left", fill="both", expand=True)
        lb_sb.config(command=self.vg_listbox.yview)
        self.vg_listbox.bind("<<ListboxSelect>>", lambda e: self._vg_gruppe_waehlen())
        self.vg_listbox.bind("<Delete>",    lambda e: self._vg_loeschen())
        self.vg_listbox.bind("<BackSpace>", lambda e: self._vg_loeschen())

        # Drag & Drop — reorder groups AND assign to categories
        self._drag_start_idx = None

        def _drag_start(e):
            idx = self.vg_listbox.nearest(e.y)
            idx_map = getattr(self, "_vg_listbox_idx", [])
            # Only allow dragging actual groups, not category headers
            if idx_map and (idx >= len(idx_map) or idx_map[idx] is None):
                return
            self._drag_start_idx = idx
            self.vg_listbox.config(cursor="fleur")

        def _drag_motion(e):
            if self._drag_start_idx is None: return
            idx = self.vg_listbox.nearest(e.y)
            self.vg_listbox.selection_clear(0, "end")
            self.vg_listbox.selection_set(idx)
            # Change cursor to indicate category drop vs reorder
            idx_map = getattr(self, "_vg_listbox_idx", [])
            if idx_map and idx < len(idx_map) and idx_map[idx] is None:
                self.vg_listbox.config(cursor="target")  # dropping on category
            else:
                self.vg_listbox.config(cursor="fleur")

        def _drag_end(e):
            self.vg_listbox.config(cursor="")
            if self._drag_start_idx is None: return
            src_lb = self._drag_start_idx
            tgt_lb = self.vg_listbox.nearest(e.y)
            self._drag_start_idx = None
            if src_lb < 0 or tgt_lb < 0: return

            idx_map = getattr(self, "_vg_listbox_idx", [])

            # Get source group
            src_real = idx_map[src_lb] if idx_map and src_lb < len(idx_map) else src_lb
            if src_real is None: return
            g = self.vergleiche[src_real]

            # Check if dropping onto a category header
            if idx_map and tgt_lb < len(idx_map) and idx_map[tgt_lb] is None:
                # Assign group to this category
                cat_label = self.vg_listbox.get(tgt_lb)
                cat_name = cat_label.strip().strip("─").strip()
                # Remove "── " prefix
                cat_name = cat_name.replace("── ","").replace(" ──","").strip()
                g["kategorie"] = cat_name
                speichere_vergleiche(self.vergleiche)
                self._vg_listbox_laden()
                return

            # Otherwise reorder
            tgt_real = idx_map[tgt_lb] if idx_map and tgt_lb < len(idx_map) else tgt_lb
            if tgt_real is None or src_real == tgt_real: return
            self.vergleiche.pop(src_real)
            self.vergleiche.insert(tgt_real, g)
            speichere_vergleiche(self.vergleiche)
            self.vg_aktuelle_gruppe = g["id"]
            self._vg_listbox_laden()

        self.vg_listbox.bind("<ButtonPress-1>",  _drag_start)
        self.vg_listbox.bind("<B1-Motion>",      _drag_motion)
        self.vg_listbox.bind("<ButtonRelease-1>", _drag_end)

        right = tk.Frame(pane, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        hdr2 = tk.Frame(right, bg=BG)
        hdr2.pack(fill="x", padx=16, pady=(12,8))
        title_col = tk.Frame(hdr2, bg=BG)
        title_col.pack(side="left")
        self.vg_titel_lbl = tk.Label(title_col, text=T("select_group"),
                                     bg=BG, fg=TEXT2, font=(UI_FONT, 13, "bold"))
        self.vg_titel_lbl.pack(anchor="w")
        self.vg_ziel_lbl = tk.Label(title_col, text="", bg=BG, fg=AKZENT,
                                    font=(UI_FONT, 9), cursor="hand2")
        self.vg_ziel_lbl.pack(anchor="w")
        self.vg_ziel_lbl.bind("<Button-1>", lambda *_: self._zielpreis_bearbeiten())
        self.vg_buynow_lbl = tk.Label(title_col, text="", bg=BG, fg=GELB,
                                      font=(UI_FONT, 9), cursor="hand2")
        self.vg_buynow_lbl.pack(anchor="w")
        self.vg_buynow_lbl.bind("<Button-1>", lambda *_: self._buynow_bearbeiten())
        self.vg_notiz_lbl = tk.Label(title_col, text="", bg=BG, fg=GRAU,
                                     font=(UI_FONT, 8), cursor="hand2")
        self.vg_notiz_lbl.pack(anchor="w")
        self.vg_notiz_lbl.bind("<Button-1>", lambda e: self._notiz_bearbeiten())
        btn_col = tk.Frame(hdr2, bg=BG)
        btn_col.pack(side="right")
        self._btn(btn_col, "🤖 AI",       self._vg_ai_analyse,   BG3, PURPLE).pack(side="left", padx=(0,4))
        self._btn(btn_col, "📊 " + T("stats_btn"), self._vg_statistiken, BG3, TEXT2).pack(side="left", padx=(0,4))
        self._btn(btn_col, T("price_history"),  self._vg_chart_zeigen, BG3, TEXT2).pack(side="left", padx=(0,4))
        self._btn(btn_col, T("add_url"),       self._vg_shop_manuell, BG3, GRAU).pack(side="left")

        # Sortier-Status: col -> bool (True=aufsteigend)
        self._sort_col   = "preis"
        self._sort_asc   = True

        cols = ("shop","url","preis","diff","status","zuletzt")
        self.vg_tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        col_defs = [("shop","Shop ↕",140),("url","URL ↕",270),("preis",T("col_price")+" ↕",105),
                    ("diff",T("target_price_lbl")+" ↕",105),("status","Status ↕",115),("zuletzt",T("col_last")+" ↕",120)]
        for col, text, w in col_defs:
            self.vg_tree.heading(col, text=text,
                                 command=lambda c=col: self._vg_sort_klick(c))
            self.vg_tree.column(col, width=w,
                                anchor="w" if col in ("shop","url","status","zuletzt") else "e")
        # Header separator line
        tk.Frame(right, bg=BORDER, height=1).pack(fill="x")
        sb = ttk.Scrollbar(right, orient="vertical", command=self.vg_tree.yview)
        self.vg_tree.configure(yscrollcommand=sb.set)
        self.vg_tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.vg_tree.bind("<Delete>",    lambda e: self._vg_shop_loeschen())
        self.vg_tree.bind("<BackSpace>", lambda e: self._vg_shop_loeschen())
        self.vg_tree.bind("<Double-1>",  lambda e: self._vg_doppelklick(e))
        self.vg_tree.bind("<Button-3>",  lambda e: self._vg_kontextmenu(e))
        self.vg_tree.tag_configure("best",      foreground=AKZENT, font=(UI_FONT, 10, "bold"), background="#0d1f1a")
        self.vg_tree.tag_configure("alarm",     foreground=AKZENT)
        self.vg_tree.tag_configure("normal",    foreground=TEXT)
        self.vg_tree.tag_configure("fehler",    foreground=ROT)
        self.vg_tree.tag_configure("gesunken",  foreground="#6ee7b7", font=(UI_FONT, 10, "bold"), background="#0a1a14")
        self.vg_tree.tag_configure("gestiegen", foreground="#fbbf24", font=(UI_FONT, 10, "bold"), background="#1a1400")
        self.vg_tree.tag_configure("favorit",   foreground=GELB, font=(UI_FONT, 10, "bold"), background="#1a1500")
        self._vg_listbox_laden()

    # ── Tab: Einstellungen ────────────────────────────────────────────────────
    def _tab_einstellungen(self):
        f = self.tab_einst
        # Scrollable settings
        canvas = tk.Canvas(f, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(f, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        wrap = tk.Frame(canvas, bg=BG)
        wrap_id = canvas.create_window((0,0), window=wrap, anchor="nw")
        def _on_resize(e):
            canvas.itemconfig(wrap_id, width=e.width)
        canvas.bind("<Configure>", _on_resize)
        wrap.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # Mouse wheel scroll
        def _scroll(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _scroll)
        # Inner padding frame
        inner = tk.Frame(wrap, bg=BG)
        inner.pack(fill="both", expand=True, padx=40, pady=24)
        wrap = inner

        def section(text):
            tk.Label(wrap, text=text, bg=BG, fg=TEXT2,
                     font=(UI_FONT, 9, "bold")).pack(anchor="w", pady=(16,4))
            tk.Frame(wrap, bg=BORDER, height=1).pack(fill="x", pady=(0,8))

        def erow(label, var, show=""):
            r = tk.Frame(wrap, bg=BG)
            r.pack(fill="x", pady=5)
            tk.Label(r, text=label, bg=BG, fg=TEXT2, width=18, anchor="w",
                     font=(UI_FONT, 10)).pack(side="left")
            e = ttk.Entry(r, textvariable=var, show=show)
            e.pack(side="left", fill="x", expand=True, ipady=4)
            return e

        cfg = self.config_data
        self.v_abs  = tk.StringVar(value=cfg.get("email_absender",""))
        self.v_pw   = tk.StringVar(value=cfg.get("email_passwort",""))
        self.v_emp  = tk.StringVar(value=cfg.get("email_empfaenger",""))
        self.v_smtp = tk.StringVar(value=cfg.get("smtp_server","mail.gmx.net"))
        self.v_port = tk.StringVar(value=str(cfg.get("smtp_port",587)))
        self.v_int  = tk.StringVar(value=str(cfg.get("intervall",6)))

        section("📧  " + T("email_config"))
        erow(T("sender_email"),  self.v_abs)
        erow(T("password"),         self.v_pw,  show="●")
        erow(T("recipient_email"), self.v_emp)
        erow("SMTP Server",      self.v_smtp)
        erow("SMTP Port",        self.v_port)

        section("⏱  " + T("check_interval"))
        r = tk.Frame(wrap, bg=BG)
        r.pack(fill="x", pady=5)
        tk.Label(r, text=T("interval_label"), bg=BG, fg=TEXT2, width=18, anchor="w",
                 font=(UI_FONT, 10)).pack(side="left")
        # Nur Zahlen erlauben
        _vcmd_int = (self.register(lambda s: s.isdigit() or s == ""), "%P")
        int_combo = ttk.Combobox(r, textvariable=self.v_int, values=[str(i) for i in range(1, 25)],
                                 width=5, font=(UI_FONT, 10), validate="key", validatecommand=_vcmd_int)
        int_combo.pack(side="left", ipady=4)
        tk.Label(r, text=T("interval_hint"), bg=BG, fg=GRAU,
                 font=(UI_FONT, 9)).pack(side="left", padx=8)

        # Time window
        _stunden = [f"{h:02d}:00" for h in range(24)]
        _vcmd_time = (self.register(lambda s: all(c.isdigit() or c == ":" for c in s) and len(s) <= 5), "%P")
        time_row = tk.Frame(wrap, bg=BG)
        time_row.pack(fill="x", pady=5)
        tk.Label(time_row, text=T("check_window"), bg=BG, fg=TEXT2, width=18, anchor="w",
                 font=(UI_FONT, 10)).pack(side="left")
        self.v_time_active = tk.BooleanVar(value=cfg.get("check_window_active", False))
        ttk.Checkbutton(time_row, variable=self.v_time_active).pack(side="left", padx=(0,8))
        tk.Label(time_row, text=T("from_lbl"), bg=BG, fg=TEXT2, font=(UI_FONT, 9)).pack(side="left")
        self.v_time_from = tk.StringVar(value=cfg.get("check_time_from", "22:00"))
        ttk.Combobox(time_row, textvariable=self.v_time_from, values=_stunden, width=6,
                     font=(UI_FONT, 10), validate="key", validatecommand=_vcmd_time
                     ).pack(side="left", ipady=3, padx=(4,8))
        tk.Label(time_row, text=T("to_lbl"), bg=BG, fg=TEXT2, font=(UI_FONT, 9)).pack(side="left")
        self.v_time_to = tk.StringVar(value=cfg.get("check_time_to", "08:00"))
        ttk.Combobox(time_row, textvariable=self.v_time_to, values=_stunden, width=6,
                     font=(UI_FONT, 10), validate="key", validatecommand=_vcmd_time
                     ).pack(side="left", ipady=3, padx=(4,0))
        tk.Label(time_row, text=T("time_hint"), bg=BG, fg=GRAU, font=(UI_FONT, 8)).pack(side="left", padx=8)

        # Region selector
        src_row = tk.Frame(wrap, bg=BG)
        src_row.pack(fill="x", pady=5)
        tk.Label(src_row, text=T("search_source_label"), bg=BG, fg=TEXT2, width=18, anchor="w",
                 font=(UI_FONT, 10)).pack(side="left")
        cur_region = cfg.get("region", "de")
        self.v_region = tk.StringVar(value=_region_display(cur_region))
        region_combo = ttk.Combobox(src_row, textvariable=self.v_region,
                                    values=[_region_display(k) for k in REGIONS],
                                    state="readonly", width=26, font=(UI_FONT, 10))
        region_combo.pack(side="left", ipady=4)

        # Wöchentlicher Digest
        section("📊  " + T("digest_email"))
        digest_row = tk.Frame(wrap, bg=BG)
        digest_row.pack(fill="x", pady=5)
        tk.Label(digest_row, text=T("digest_active_lbl"), bg=BG, fg=TEXT2, width=18, anchor="w",
                 font=(UI_FONT, 10)).pack(side="left")
        self.v_digest_active = tk.BooleanVar(value=cfg.get("digest_active", False))
        ttk.Checkbutton(digest_row, variable=self.v_digest_active).pack(side="left")

        digest_day_row = tk.Frame(wrap, bg=BG)
        digest_day_row.pack(fill="x", pady=5)
        tk.Label(digest_day_row, text=T("digest_day_lbl"), bg=BG, fg=TEXT2, width=18, anchor="w",
                 font=(UI_FONT, 10)).pack(side="left")
        _wt = {"de": ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"],
               "en": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]}
        _lang = cfg.get("language", "en")
        _weekdays = _wt.get(_lang, _wt["en"])
        cur_day = min(cfg.get("digest_day", 0), 6)
        self.v_digest_day = tk.StringVar(value=_weekdays[cur_day])
        self._digest_weekdays = _weekdays
        ttk.Combobox(digest_day_row, textvariable=self.v_digest_day, values=_weekdays,
                     state="readonly", width=14, font=(UI_FONT, 10)).pack(side="left", ipady=4, padx=(0,12))
        tk.Label(digest_day_row, text=T("digest_time_lbl"), bg=BG, fg=TEXT2,
                 font=(UI_FONT, 10)).pack(side="left", padx=(0,6))
        self.v_digest_time = tk.StringVar(value=cfg.get("digest_time", "08:00"))
        ttk.Entry(digest_day_row, textvariable=self.v_digest_time, width=6).pack(side="left", ipady=3, padx=(0,12))
        self._btn(digest_day_row, T("digest_test"),
                  lambda: [self.status_check_lbl.config(text=T("digest_sent"), fg=AKZENT),
                           threading.Thread(target=email_wochenbericht,
                                            args=(self.config_data, self.vergleiche),
                                            daemon=True).start()],
                  BG3, TEXT).pack(side="left", ipady=2)

        tk.Frame(wrap, bg=BORDER, height=1).pack(fill="x", pady=16)
        btn_row = tk.Frame(wrap, bg=BG)
        btn_row.pack(fill="x")
        self._btn(btn_row, T("save"),  self._cfg_speichern, AKZENT, "#000").pack(side="left", padx=(0,10), ipady=4)
        self._btn(btn_row, T("test_email"), self._test_email, BG3, TEXT).pack(side="left", ipady=4, padx=(0,10))
        self._btn(btn_row, "🔔 Test", self._test_notification, BG3, TEXT).pack(side="left", ipady=4)

        section("🖥  System")
        # Language
        lang_row = tk.Frame(wrap, bg=BG)
        lang_row.pack(fill="x", pady=5)
        tk.Label(lang_row, text=T("language"), bg=BG, fg=TEXT2,
                 width=18, anchor="w", font=(UI_FONT, 10)).pack(side="left")
        cur_lang = self.config_data.get("language","en")
        self.v_lang = tk.StringVar(value=LANGUAGES.get(cur_lang, LANGUAGES["en"]))
        lang_combo = ttk.Combobox(lang_row, textvariable=self.v_lang,
                                   values=list(LANGUAGES.values()),
                                   state="readonly", width=26,
                                   font=(UI_FONT, 10))
        lang_combo.pack(side="left", ipady=4)
        lang_combo.bind("<<ComboboxSelected>>", lambda e: self._lang_aendern())

        # Theme selector
        theme_row = tk.Frame(wrap, bg=BG)
        theme_row.pack(fill="x", pady=5)
        tk.Label(theme_row, text=T("theme"), bg=BG, fg=TEXT2,
                 width=18, anchor="w", font=(UI_FONT, 10)).pack(side="left")
        cur_theme = self.config_data.get("theme", "dark_mint")
        self.v_theme = tk.StringVar(value=THEMES.get(cur_theme, THEMES["dark_mint"])["name"])
        theme_combo = ttk.Combobox(theme_row, textvariable=self.v_theme,
                                    values=[t["name"] for t in THEMES.values()],
                                    state="readonly", width=26, font=(UI_FONT, 10))
        theme_combo.pack(side="left", ipady=4)
        tk.Label(theme_row, text=f"  ← {T('theme_hint')}", bg=BG, fg=GRAU,
                 font=(UI_FONT, 8)).pack(side="left")
        theme_combo.bind("<<ComboboxSelected>>", lambda e: self._theme_aendern())

        # Font selector
        font_row = tk.Frame(wrap, bg=BG)
        font_row.pack(fill="x", pady=5)
        tk.Label(font_row, text=T("font_label"), bg=BG, fg=TEXT2,
                 width=18, anchor="w", font=(UI_FONT, 10)).pack(side="left")
        cur_font_id = self.config_data.get("font", "segoe")
        self.v_font = tk.StringVar(value=FONTS.get(cur_font_id, FONTS["segoe"])["label"])
        font_combo = ttk.Combobox(font_row, textvariable=self.v_font,
                                   values=[f["label"] for f in FONTS.values()],
                                   state="readonly", width=26, font=(UI_FONT, 10))
        font_combo.pack(side="left", ipady=4)
        font_combo.bind("<<ComboboxSelected>>", lambda e: self._font_aendern())

        sys_row = tk.Frame(wrap, bg=BG)
        sys_row.pack(fill="x", pady=5)
        self.v_autostart = tk.BooleanVar(value=autostart_aktiv())
        tk.Checkbutton(sys_row, variable=self.v_autostart,
                       bg=BG, fg=TEXT, activebackground=BG, selectcolor=BG3,
                       font=(UI_FONT, 10),
                       text=T("start_windows"),
                       command=self._autostart_toggle).pack(side="left")

        tray_row = tk.Frame(wrap, bg=BG)
        tray_row.pack(fill="x", pady=5)
        self.v_tray = tk.BooleanVar(value=self.config_data.get("minimize_to_tray", True))
        tk.Checkbutton(tray_row, variable=self.v_tray,
                       bg=BG, fg=TEXT, activebackground=BG, selectcolor=BG3,
                       font=(UI_FONT, 10),
                       text=T("minimize_tray"),
                       command=self._tray_toggle).pack(side="left")

        section("ℹ  " + T("smtp_presets"))
        SMTP_PRESETS = [
            ("GMX",          "mail.gmx.net",           587,  "@gmx.de / @gmx.net"),
            ("Web.de",       "smtp.web.de",             587,  "@web.de"),
            ("Freenet",      "mx.freenet.de",           587,  "@freenet.de"),
            ("T-Online",     "securesmtp.t-online.de",  465,  "@t-online.de"),
            ("1&1 / IONOS",  "smtp.1und1.de",           587,  "@1und1.de / @ionos.de"),
            ("Outlook/Live", "smtp.office365.com",      587,  "@outlook.com / @live.de / @hotmail.com"),
            ("Gmail",        "smtp.gmail.com",          587,  "@gmail.com  (App Password required)"),
            ("Yahoo",        "smtp.mail.yahoo.com",     587,  "@yahoo.com / @yahoo.de"),
            ("iCloud",       "smtp.mail.me.com",        587,  "@icloud.com / @me.com"),
            ("Posteo",       "posteo.de",               587,  "@posteo.de"),
            ("Mailbox.org",  "smtp.mailbox.org",        587,  "@mailbox.org"),
        ]
        presets_frame = tk.Frame(wrap, bg=BG)
        presets_frame.pack(fill="x", pady=(0,4))

        def apply_preset(server, port):
            self.v_smtp.set(server)
            self.v_port.set(str(port))

        for name, server, port, hint in SMTP_PRESETS:
            row_f = tk.Frame(presets_frame, bg=BG)
            row_f.pack(fill="x", pady=2)
            btn = tk.Button(row_f, text=name, bg=BG3, fg=TEXT,
                            activebackground=AKZENT, activeforeground="#000",
                            font=(UI_FONT, 9, "bold"), relief="flat",
                            cursor="hand2", padx=10, pady=3, width=12,
                            command=lambda s=server, p=port: apply_preset(s, p))
            btn.pack(side="left", padx=(0,8))
            tk.Label(row_f, text=f"{server}  |  Port: {port}   {hint}",
                     bg=BG, fg=GRAU, font=(UI_FONT, 9), anchor="w").pack(side="left")

    # ── Tab: Log ──────────────────────────────────────────────────────────────
    def _tab_log(self):
        f = self.tab_log
        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", padx=12, pady=(12,4))
        self._btn(bar, T("clear_log"), self._log_leeren, BG3, TEXT).pack(side="left")
        self.log_box = scrolledtext.ScrolledText(
            f, bg=BG2, fg=TEXT, font=("Consolas", 9),
            insertbackground=TEXT, borderwidth=0, relief="flat",
            state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self._log_refresh()

    # ── Vergleich: Gruppen-Logik ──────────────────────────────────────────────
    def _vg_listbox_laden(self):
        self.vg_listbox.delete(0, "end")
        self._vg_listbox_idx = []  # maps listbox index -> group index
        # Group by category
        cats = {}
        for idx, g in enumerate(self.vergleiche):
            cat = g.get("kategorie","").strip() or T("no_category")
            cats.setdefault(cat, []).append((idx, g))

        for cat, gruppe_list in sorted(cats.items()):
            # Show category header if any group has a category set
            has_cats = any(g.get("kategorie","").strip() for g in self.vergleiche)
            if has_cats:
                self.vg_listbox.insert("end", f"── {cat} ──")
                self.vg_listbox.itemconfig("end", fg=GRAU, selectbackground=BG2, selectforeground=GRAU)
                self._vg_listbox_idx.append(None)  # header row

            for idx, g in gruppe_list:
                shops_mit_preis = [s for s in g.get("shops",[]) if s.get("preis")]
                if shops_mit_preis:
                    bester = min(s["preis"] for s in shops_mit_preis)
                    cur = g.get("currency","€")
                    ziel = g.get("zielpreis",0)
                    icon = "🏆" if bester <= ziel else ""
                    label = f"  {g['name'][:20]}  {icon} {cur}{bester:.0f}"
                else:
                    label = f"  {g['name']}"
                self.vg_listbox.insert("end", label)
                self._vg_listbox_idx.append(idx)
        if self.vergleiche:
            idx = next((i for i,g in enumerate(self.vergleiche)
                        if g["id"] == self.vg_aktuelle_gruppe), 0)
            self.vg_listbox.selection_set(idx)
            self._vg_gruppe_waehlen()

    def _vg_gruppe_waehlen(self):
        sel = self.vg_listbox.curselection()
        if not sel: return
        idx_map = getattr(self, "_vg_listbox_idx", None)
        if idx_map:
            real_idx = idx_map[sel[0]] if sel[0] < len(idx_map) else None
            if real_idx is None: return  # header row clicked
            g = self.vergleiche[real_idx]
        elif sel[0] >= len(self.vergleiche):
            return
        else:
            g = self.vergleiche[sel[0]]
        self.vg_aktuelle_gruppe = g["id"]
        self.vg_titel_lbl.config(text=g["name"])
        self.vg_ziel_lbl.config(text=f"🔔 {T('alarm_price')}: {g.get('currency','€')}{g['zielpreis']:.2f}")
        buy_now = g.get("buy_now_price")
        if buy_now:
            self.vg_buynow_lbl.config(text=f"⚡ {T('buy_now_price')}: {g.get('currency','€')}{buy_now:.2f}")
        else:
            self.vg_buynow_lbl.config(text="")
        notiz = g.get("notiz","")
        self.vg_notiz_lbl.config(text=f"📝 {notiz}" if notiz else f"📝 {T('add_note')}")
        self._vg_tabelle_laden(g)

    def _vg_doppelklick(self, event):
        """Double-click on diff column = edit target price, else open URL."""
        col = self.vg_tree.identify_column(event.x)
        col_idx = int(col.replace("#","")) - 1
        cols = ("shop","url","preis","diff","status","zuletzt")
        if col_idx < len(cols) and cols[col_idx] == "diff":
            self._zielpreis_bearbeiten()
        else:
            self._vg_shop_oeffnen()

    def _notiz_bearbeiten(self):
        """Edit note for current group."""
        g = self._aktuelle_vg()
        if not g: return
        dlg = tk.Toplevel(self)
        dlg.title(T("note"))
        self._center_dialog(dlg, 400, 180)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        tk.Label(dlg, text=f"📝 {T('note')}:", bg=BG, fg=TEXT,
                 font=(UI_FONT, 10)).pack(anchor="w", padx=20, pady=(16,4))
        var = tk.StringVar(value=g.get("notiz",""))
        entry = ttk.Entry(dlg, textvariable=var, font=(UI_FONT, 11))
        entry.pack(fill="x", padx=20, ipady=6)
        entry.select_range(0, "end")
        entry.focus_set()
        def _save():
            g["notiz"] = var.get().strip()
            speichere_vergleiche(self.vergleiche)
            notiz = g.get("notiz","")
            self.vg_notiz_lbl.config(text=f"📝 {notiz}" if notiz else f"📝 {T('add_note')}")
            dlg.destroy()
        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=10)
        self._btn(btn_row, T("save"), _save, AKZENT, "#000").pack(side="left", padx=6, ipadx=10)
        self._btn(btn_row, T("close"), dlg.destroy, BG3, TEXT).pack(side="left", padx=6, ipadx=10)
        entry.bind("<Return>", lambda e: _save())
        entry.bind("<Escape>", lambda e: dlg.destroy())

    def _zielpreis_bearbeiten(self):
        """Edit target price inline via popup."""
        g = self._aktuelle_vg()
        if not g: return
        dlg = tk.Toplevel(self)
        dlg.title(T("target_lbl"))
        self._center_dialog(dlg, 320, 140)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        tk.Label(dlg, text=f"{T('target_lbl')}:", bg=BG, fg=TEXT,
                 font=(UI_FONT, 10)).pack(anchor="w", padx=20, pady=(16,4))
        var = tk.StringVar(value=str(g["zielpreis"]))
        entry = ttk.Entry(dlg, textvariable=var, font=(UI_FONT, 12), justify="center")
        entry.pack(fill="x", padx=20, ipady=6)
        entry.select_range(0, "end")
        entry.focus_set()
        def _save():
            try:
                g["zielpreis"] = float(var.get().replace(",","."))
                speichere_vergleiche(self.vergleiche)
                self._vg_tabelle_laden(g)
                self.vg_ziel_lbl.config(
                    text=f"{T('target_price_lbl')}: {g.get('currency','€')}{g['zielpreis']:.2f}")
                dlg.destroy()
            except ValueError:
                messagebox.showerror(T("error"), T("enter_valid_price"), parent=dlg)
        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=10)
        self._btn(btn_row, T("save"), _save, AKZENT, "#000").pack(side="left", padx=6, ipadx=10)
        self._btn(btn_row, T("close"), dlg.destroy, BG3, TEXT).pack(side="left", padx=6, ipadx=10)
        entry.bind("<Return>", lambda e: _save())
        entry.bind("<Escape>", lambda e: dlg.destroy())

    def _buynow_bearbeiten(self):
        """Edit buy-now price inline via popup."""
        g = self._aktuelle_vg()
        if not g: return
        dlg = tk.Toplevel(self)
        dlg.title(T("buy_now_price"))
        self._center_dialog(dlg, 320, 140)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()
        tk.Label(dlg, text=f"⚡ {T('buy_now_price')}:", bg=BG, fg=TEXT,
                 font=(UI_FONT, 10)).pack(anchor="w", padx=20, pady=(16,4))
        cur_val = str(g["buy_now_price"]) if g.get("buy_now_price") else ""
        var = tk.StringVar(value=cur_val)
        entry = ttk.Entry(dlg, textvariable=var, font=(UI_FONT, 12), justify="center")
        entry.pack(fill="x", padx=20, ipady=6)
        entry.select_range(0, "end")
        entry.focus_set()
        def _save():
            try:
                val = var.get().strip().replace(",", ".")
                g["buy_now_price"] = float(val) if val else None
                speichere_vergleiche(self.vergleiche)
                if g.get("buy_now_price"):
                    self.vg_buynow_lbl.config(
                        text=f"⚡ {T('buy_now_price')}: {g.get('currency','€')}{g['buy_now_price']:.2f}")
                else:
                    self.vg_buynow_lbl.config(text="")
                dlg.destroy()
            except ValueError:
                messagebox.showerror(T("error"), T("enter_valid_price"), parent=dlg)
        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=10)
        self._btn(btn_row, T("save"), _save, AKZENT, "#000").pack(side="left", padx=6, ipadx=10)
        self._btn(btn_row, T("close"), dlg.destroy, BG3, TEXT).pack(side="left", padx=6, ipadx=10)
        entry.bind("<Return>", lambda e: _save())
        entry.bind("<Escape>", lambda e: dlg.destroy())

    def _vg_kontextmenu(self, event):
        """Right-click context menu on shop row."""
        row = self.vg_tree.identify_row(event.y)
        if not row: return
        self.vg_tree.selection_set(row)
        g = self._aktuelle_vg()
        shop = next((s for s in g["shops"] if s["id"] == row), None) if g else None
        ist_favorit = shop.get("favorit", False) if shop else False
        menu = tk.Menu(self, tearoff=0, bg=BG3, fg=TEXT, activebackground=AKZENT,
                       activeforeground="#000", relief="flat", font=(UI_FONT, 10))
        menu.add_command(label="🌐  " + T("open_shop"),  command=self._vg_shop_oeffnen)
        menu.add_command(label="🔄  " + T("check_price"),   command=self._vg_shop_einzeln_pruefen)
        menu.add_command(label=("★  " + T("remove_favorite") if ist_favorit else "☆  " + T("mark_favorite")),
                         command=self._vg_shop_favorit_toggle)
        menu.add_separator()
        menu.add_command(label="🗑  " + T("delete_shop"), command=self._vg_shop_loeschen,
                         foreground=ROT)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _vg_sort_klick(self, col):
        """Click on column header: toggle ascending/descending sort."""
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True
        # Pfeil in Überschrift aktualisieren
        col_namen = {"shop":"Shop","url":"URL","preis":T("col_price"),
                     "diff":T("target_price_lbl"),"status":"Status","zuletzt":T("col_last")}
        for c, name in col_namen.items():
            if c == self._sort_col:
                pfeil = " ↑" if self._sort_asc else " ↓"
            else:
                pfeil = " ↕"
            self.vg_tree.heading(c, text=name + pfeil)
        g = self._aktuelle_vg()
        if g:
            self._vg_tabelle_laden(g)

    def _vg_filter_anwenden(self):
        g = self._aktuelle_vg()
        if g:
            self._vg_tabelle_laden(g)

    def _vg_tabelle_laden(self, gruppe):
        for row in self.vg_tree.get_children():
            self.vg_tree.delete(row)
        shops = list(gruppe.get("shops", []))
        if not shops: return

        # Filter anwenden
        filter_text = getattr(self, "filter_var", None)
        if filter_text:
            ft = filter_text.get().lower().strip()
            if ft:
                shops = [s for s in shops if
                         ft in (s.get("shop_name") or s["shop"]).lower() or
                         ft in s.get("url","").lower()]

        # Sortierung nach angeklickter Spalte
        col   = getattr(self, "_sort_col", "preis")
        asc   = getattr(self, "_sort_asc", True)
        key_map = {
            "shop":    lambda s: (s.get("shop_name") or s["shop"]).lower(),
            "url":     lambda s: s.get("url","").lower(),
            "preis":   lambda s: s.get("preis") or 99999,
            "diff":    lambda s: gruppe.get("zielpreis", 0),
            "status":  lambda s: s.get("preis") or 0,
            "zuletzt": lambda s: s.get("zuletzt",""),
        }
        if col in key_map:
            shops = sorted(shops, key=key_map[col], reverse=not asc)
        preise = [s["preis"] for s in shops if s.get("preis")]
        bester = min(preise) if preise else None
        for s in shops:
            preis = s.get("preis")
            ziel  = gruppe["zielpreis"]
            preis_vorher = s.get("preis_vorher")
            trend        = s.get("preis_trend", "")
            cur          = gruppe.get("currency", "€")
            # Price display with change arrow
            if preis and preis_vorher:
                diff  = preis - preis_vorher
                pfeil = "⬇" if diff < 0 else "⬆"
                p_str = f"{cur}{preis:.2f}  {pfeil} {abs(diff):.2f}"
            else:
                p_str = f"{cur}{preis:.2f}" if preis else "–"
            d_str    = f"{cur}{ziel:.2f}"
            ist_best = preis and bester and preis == bester
            alarm    = preis and preis <= ziel
            noch     = T("still_too_much").replace("{diff}", f"{preis-ziel:.2f} {cur}") if (preis and not alarm) else ""
            status   = T("best_price") if ist_best else (T("target_reached") if alarm else (f"⬇ {noch}" if preis else T("no_price")))
            # Tag: Favorit hat Vorrang, dann Preisänderung, dann normaler Status
            ist_favorit = s.get("favorit", False)
            if ist_favorit:
                tag = "favorit"
            elif trend == "gesunken":
                tag = "gesunken"
            elif trend == "gestiegen":
                tag = "gestiegen"
            else:
                tag = "best" if ist_best else ("alarm" if alarm else ("fehler" if not preis else "normal"))
            shop_anzeige = ("⭐ " if ist_favorit else "") + (s.get("shop_name") or SHOPS.get(s["shop"], s["shop"]))
            try:
                from urllib.parse import urlparse
                parsed = urlparse(s["url"])
                anzeige_url = parsed.netloc.replace("www.","") + (parsed.path[:30] if parsed.path != "/" else "")
            except:
                anzeige_url = s["url"][:50]
            self.vg_tree.insert("", "end", iid=s["id"],
                                values=(shop_anzeige, anzeige_url,
                                        p_str, d_str, status, s.get("zuletzt","–")),
                                tags=(tag,))

    # ── Neue Gruppe Dialog ────────────────────────────────────────────────────
    def _kategorie_neu(self):
        """Create a new category and optionally assign selected group to it."""
        dlg = tk.Toplevel(self)
        dlg.title(T("new_category"))
        self._center_dialog(dlg, 380, 200)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text="📁 " + T("new_category"), bg=BG, fg=TEXT,
                 font=(UI_FONT, 12, "bold")).pack(anchor="w", padx=24, pady=(20,4))
        tk.Label(dlg, text=T("category_name"), bg=BG, fg=TEXT2,
                 font=(UI_FONT, 9)).pack(anchor="w", padx=24)

        v_name = tk.StringVar()
        existing = sorted(set(g.get("kategorie","") for g in self.vergleiche if g.get("kategorie","")))
        entry = ttk.Combobox(dlg, textvariable=v_name, values=existing, font=(UI_FONT, 11))
        entry.pack(fill="x", padx=24, ipady=6, pady=(4,0))
        entry.focus_set()

        # Option to assign current group
        g = self._aktuelle_vg()
        v_assign = tk.BooleanVar(value=bool(g))
        if g:
            assign_row = tk.Frame(dlg, bg=BG)
            assign_row.pack(fill="x", padx=24, pady=(8,0))
            ttk.Checkbutton(assign_row, variable=v_assign).pack(side="left")
            tk.Label(assign_row, text=T("assign_current_group").replace("{name}", g["name"][:30]),
                     bg=BG, fg=GRAU, font=(UI_FONT, 9)).pack(side="left", padx=4)

        def _save():
            name = v_name.get().strip()
            if not name:
                messagebox.showerror(T("error"), T("enter_category_name"), parent=dlg)
                return
            if g and v_assign.get():
                g["kategorie"] = name
                speichere_vergleiche(self.vergleiche)
                self._vg_listbox_laden()
            dlg.destroy()

        btn_row = tk.Frame(dlg, bg=BG)
        btn_row.pack(pady=12)
        self._btn(btn_row, T("save"), _save, AKZENT, "#000").pack(side="left", padx=6, ipadx=16)
        self._btn(btn_row, T("close"), dlg.destroy, BG3, TEXT).pack(side="left", padx=6, ipadx=16)
        entry.bind("<Return>", lambda e: _save())
        entry.bind("<Escape>", lambda e: dlg.destroy())

    def _vg_neu(self, prefill_url=""):
        dlg = tk.Toplevel(self)
        dlg.title(T("new_group_title"))
        self._center_dialog(dlg, 660, 600)
        dlg.configure(bg=BG)
        dlg.resizable(True, True)
        dlg.minsize(580, 520)
        dlg.grab_set()

        # Category field
        cat_row = tk.Frame(dlg, bg=BG)
        cat_row.pack(fill="x", padx=24, pady=(16,0))
        tk.Label(cat_row, text=T("category"), bg=BG, fg=TEXT2,
                 font=(UI_FONT, 10, "bold")).pack(side="left")
        tk.Label(cat_row, text=f" ({T('optional')})", bg=BG, fg=GRAU,
                 font=(UI_FONT, 9)).pack(side="left")
        v_kat = tk.StringVar()
        existing_cats = sorted(set(g.get("kategorie","") for g in self.vergleiche if g.get("kategorie","")))
        cat_input_row = tk.Frame(dlg, bg=BG)
        cat_input_row.pack(fill="x", padx=24, pady=(4,0))
        cat_combo = ttk.Combobox(cat_input_row, textvariable=v_kat, values=existing_cats,
                                  font=(UI_FONT, 10))
        cat_combo.pack(side="left", fill="x", expand=True, ipady=4)

        tk.Label(dlg, text=T("search_hint"),
                 bg=BG, fg=TEXT2, font=(UI_FONT, 10)).pack(anchor="w", padx=20, pady=(16,4))

        hint_row = tk.Frame(dlg, bg=BG)
        hint_row.pack(fill="x", padx=20)
        tk.Label(hint_row, text=T("url_tip"),
                 bg=BG, fg=GRAU, font=(UI_FONT, 8)).pack(side="left")
        tk.Label(hint_row, text="   " + T("search_source_label") + ":", bg=BG, fg=GRAU,
                 font=(UI_FONT, 8)).pack(side="left", padx=(16,4))
        cur_region_key = self.config_data.get("region", "de")
        v_src = tk.StringVar(value=_region_display(cur_region_key))
        src_combo_dlg = ttk.Combobox(hint_row, textvariable=v_src,
                                     values=[_region_display(k) for k in REGIONS],
                                     state="readonly", width=22, font=(UI_FONT, 8))
        src_combo_dlg.pack(side="left", ipady=2)

        such_row = tk.Frame(dlg, bg=BG)
        such_row.pack(fill="x", padx=20, pady=(6,0))
        e_such = ttk.Entry(such_row, font=(UI_FONT, 10))
        e_such.pack(side="left", fill="x", expand=True, ipady=5)
        e_such.focus()

        status_lbl = tk.Label(dlg, text="", bg=BG, fg=TEXT2, font=(UI_FONT, 9), anchor="w")
        status_lbl.pack(fill="x", padx=20, pady=(4,0))

        self._vg_shop_vars = {}
        canvas = tk.Canvas(dlg, bg=BG, height=170, highlightthickness=0)
        scroll = ttk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
        inner  = tk.Frame(canvas, bg=BG)
        canvas.create_window((0,0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.pack(fill="both", expand=True, padx=20, pady=(4,0))
        scroll.pack(side="right", fill="y")

        prices_frame = tk.Frame(dlg, bg=BG)
        prices_frame.pack(fill="x", padx=20, pady=(10,0))

        def _get_dialog_currency():
            eingabe = e_such.get().strip()
            # URL paste: detect currency from domain
            if eingabe.startswith("http"):
                for _, r in REGIONS.items():
                    ps = r.get("ps_domain", "")
                    if ps and ps in eingabe:
                        return r["currency"]
                    amz = r.get("amz", "")
                    if amz and amz in eingabe:
                        return r["currency"]
                return "€"
            # Text search: use selected region
            sel = v_src.get()
            region_key = next((k for k in REGIONS if _region_display(k) == sel), "de")
            return _region_currency(region_key)

        def _is_gbp_source():
            return _get_dialog_currency() == "£"

        # Alarm price row
        ziel_row = tk.Frame(prices_frame, bg=BG)
        ziel_row.pack(fill="x", pady=(0,6))
        lbl_ziel = tk.Label(ziel_row, text="🔔 " + T("alarm_price") + " (£)" if _is_gbp_source() else "🔔 " + T("alarm_price") + " (€)",
                            bg=BG, fg=TEXT2, width=22, anchor="w", font=(UI_FONT, 10))
        lbl_ziel.pack(side="left")
        e_ziel = ttk.Entry(ziel_row, width=12)
        e_ziel.pack(side="left", ipady=5)
        tk.Label(ziel_row, text="  " + T("alert_hint"),
                 bg=BG, fg=GRAU, font=(UI_FONT, 8), wraplength=250).pack(side="left")

        # Buy now price row
        buynow_row = tk.Frame(prices_frame, bg=BG)
        buynow_row.pack(fill="x")
        lbl_buynow = tk.Label(buynow_row, text="⚡ " + T("buy_now_price") + " (£)" if _is_gbp_source() else "⚡ " + T("buy_now_price") + " (€)",
                              bg=BG, fg=GELB, width=22, anchor="w", font=(UI_FONT, 10))
        lbl_buynow.pack(side="left")

        def _cur_aktualisieren(*_):
            sym = _get_dialog_currency()
            lbl_ziel.config(text="🔔 " + T("alarm_price") + f" ({sym})")
            lbl_buynow.config(text="⚡ " + T("buy_now_price") + f" ({sym})")
        v_src.trace_add("write", _cur_aktualisieren)
        e_such.bind("<KeyRelease>", _cur_aktualisieren)
        e_buynow = ttk.Entry(buynow_row, width=12)
        e_buynow.pack(side="left", ipady=5)
        tk.Label(buynow_row, text="  " + T("buy_now_hint"),
                 bg=BG, fg=GRAU, font=(UI_FONT, 8), wraplength=250).pack(side="left")

        gefunden = []
        gefundene_source_url = [""]  # Mutable container for thread

        def suchen(*_):
            eingabe = e_such.get().strip()
            if not eingabe: return
            for w in inner.winfo_children(): w.destroy()
            self._vg_shop_vars.clear()
            gefunden.clear()
            btn_such.config(state="disabled", text="  ⏳  ")
            ist_url = eingabe.startswith("http") and any(
                d in eingabe for d in [
                    "geizhals.de", "geizhals.eu", "geizhals.at",
                    "pricespy.co.uk", "pricespy.com",
                    "amazon.de", "amazon.co.uk", "amazon.com",
                ])
            status_lbl.config(
                text=T("loading_url") if ist_url else f"🔍  Searching on {v_src.get()}...",
                fg=TEXT2)

            def _thread():
                if ist_url:
                    if any(d in eingabe for d in ["pricespy.co.uk","pricespy.com"]):
                        shops, name = pricespy_laden(eingabe)
                    elif any(d in eingabe for d in ["amazon.de","amazon.co.uk","amazon.com"]):
                        # Single Amazon product URL — fetch price directly
                        shop = _shop_aus_url(eingabe)
                        p = preis_holen(eingabe, shop)
                        shops = [{"name": "Amazon.de", "url": eingabe,
                                  "preis": p, "shop_key": "amazon",
                                  "shop_name": "Amazon.de"}] if p else []
                        name = eingabe
                    else:
                        shops, name = shops_aus_url_laden(eingabe)
                    gefundene_source_url[0] = eingabe
                else:
                    region_key = next((k for k in REGIONS if _region_display(k) == v_src.get()), "de")
                    result = region_suchen(eingabe, region_key)
                    shops, name = result[0], result[1]
                    if len(result) > 2 and result[2]:
                        gefundene_source_url[0] = result[2]
                self.after(0, lambda: _fertig(shops, name))

            threading.Thread(target=_thread, daemon=True).start()

        def _fertig(shops, name):
            btn_such.config(state="normal", text=T("search_btn"))
            if not shops:
                status_lbl.config(
                    text="⚠  No shops found. Tip: Paste a shop URL directly or use '+ Add URL'.",
                    fg=GELB)
                return
            status_lbl.config(
                text=f"✅  {len(shops)} shops found — uncheck to exclude:",
                fg=AKZENT)
            gefunden.extend(shops)
            # Produktname als Gruppenname vorschlagen
            if name and name != e_such.get().strip():
                e_such.delete(0, "end")
                e_such.insert(0, name)

            ctrl = tk.Frame(inner, bg=BG)
            ctrl.pack(fill="x", pady=(0,4))
            tk.Button(ctrl, text=T("all_btn"),  bg=BG3, fg=TEXT2, font=(UI_FONT,8), relief="flat", padx=6, pady=2,
                      command=lambda: [v.set(True)  for v,_ in self._vg_shop_vars.values()]).pack(side="left", padx=(0,4))
            tk.Button(ctrl, text=T("none_btn"), bg=BG3, fg=TEXT2, font=(UI_FONT,8), relief="flat", padx=6, pady=2,
                      command=lambda: [v.set(False) for v,_ in self._vg_shop_vars.values()]).pack(side="left")
            tk.Label(ctrl, text="  Preise werden nach der Auswahl geladen", bg=BG, fg=GRAU,
                     font=(UI_FONT, 8)).pack(side="left", padx=8)

            min_preis = min((s["preis"] for s in shops if s["preis"] > 0), default=0)
            # Detect currency from entered URL or selected region
            dialog_cur = _get_dialog_currency()
            for i, s in enumerate(shops):
                var = tk.BooleanVar(value=True)
                self._vg_shop_vars[str(i)] = (var, s)
                row_f = tk.Frame(inner, bg=BG)
                row_f.pack(fill="x", pady=1)
                tk.Checkbutton(row_f, variable=var, bg=BG, fg=TEXT,
                               activebackground=BG, selectcolor=BG3,
                               font=(UI_FONT,9)).pack(side="left")
                tk.Label(row_f, text=s["name"], bg=BG, fg=TEXT,
                         font=(UI_FONT,9,"bold"), width=24, anchor="w").pack(side="left")
                if s["preis"] > 0:
                    col = AKZENT if s["preis"] == min_preis else TEXT2
                    preis_txt = f"{dialog_cur}{s['preis']:.2f}"
                else:
                    col = TEXT2
                    preis_txt = "–"
                tk.Label(row_f, text=preis_txt, bg=BG, fg=col,
                         font=(UI_FONT,9,"bold"), width=9, anchor="e").pack(side="left")

            if not e_ziel.get() and min_preis > 0:
                e_ziel.insert(0, f"{min_preis * 0.90:.2f}")
            e_ziel.focus()

        def speichern(*_):
            name = e_such.get().strip()
            # Falls URL eingegeben wurde und kein Produktname gefunden: ersten Shop-Namen nehmen
            if name.startswith("http"):
                name = ""
            if not name and gefunden:
                name = gefunden[0].get("name","")[:60]
            if not name:
                messagebox.showerror("Error", "Please enter a name.", parent=dlg); return
            try:
                ziel = float(e_ziel.get().replace(",","."))
            except:
                messagebox.showerror(T("error"), T("enter_valid_price"), parent=dlg); return

            # Geizhals/Idealo URL merken für spätere Preisaktualisierungen
            eingabe_url = e_such.get().strip()
            if eingabe_url.startswith("http") and any(
                    d in eingabe_url for d in [
                        "geizhals.de", "geizhals.eu", "geizhals.at",
                        "pricespy.co.uk", "pricespy.com",
                    ]):
                source_url = eingabe_url
            elif eingabe_url.startswith("http") and any(
                    d in eingabe_url for d in ["amazon.de","amazon.co.uk","amazon.com"]):
                source_url = eingabe_url  # Direct Amazon URL
            elif gefundene_source_url[0]:
                source_url = gefundene_source_url[0]
            else:
                source_url = ""
            log(f"Group source_url: {source_url[:60]}" if source_url else "Gruppe ohne source_url")
            # Detect currency from source
            waehrung = _get_dialog_currency()
            try:
                buy_now_val = float(e_buynow.get().replace(",",".")) if e_buynow.get().strip() else None
            except: buy_now_val = None
            # ── PriceSpy listing: create one group per selected manufacturer variant ──
            is_ps_listing = bool(source_url and "/s/" in source_url and "pricespy." in source_url)
            if is_ps_listing:
                selected_variants = [(sid, s) for sid, (var, s) in self._vg_shop_vars.items() if var.get()]
                if not selected_variants:
                    messagebox.showerror(T("error"), "Please select at least one variant.", parent=dlg)
                    return
                kat = v_kat.get().strip()
                dlg.destroy()

                def _create_groups(_variants=selected_variants, _ziel=ziel,
                                   _bnv=buy_now_val, _kat=kat, _cur=waehrung):
                    total = len(_variants)
                    for i, (_, variant) in enumerate(_variants, 1):
                        vname = variant.get("name", variant.get("shop_name", "Product"))
                        self.after(0, lambda t=f"⏳ Loading shops {i}/{total}: {vname[:28]}...":
                                   self.status_check_lbl.config(text=t, fg=TEXT2))
                        try:
                            actual_shops, _ = pricespy_laden(variant["url"])
                        except Exception as e:
                            log(f"Error loading shops for {vname}: {e}")
                            actual_shops = []
                        if not actual_shops:
                            actual_shops = [variant]

                        g = {"id":           str(int(time.time()*1000)) + str(i),
                             "name":          vname,
                             "zielpreis":     _ziel,
                             "buy_now_price": _bnv,
                             "kategorie":     _kat,
                             "shops":         [],
                             "alarm_gesendet": False,
                             "source_url":    variant["url"],
                             "currency":      _cur}
                        for j, s in enumerate(actual_shops):
                            g["shops"].append({
                                "id":        str(int(time.time()*1000)) + str(i) + str(j),
                                "url":       s["url"],
                                "shop":      s.get("shop_key", _shop_aus_url(s["url"])),
                                "shop_name": s.get("shop_name", s.get("name", "")),
                                "preis":     s["preis"],
                                "zuletzt":   datetime.now().strftime("%d.%m. %H:%M"),
                            })
                        self.vergleiche.append(g)
                        self.vg_aktuelle_gruppe = g["id"]

                    speichere_vergleiche(self.vergleiche)
                    self.after(0, self._vg_listbox_laden)
                    self.after(0, lambda: self.status_check_lbl.config(
                        text=f"✅ {total} groups created from PriceSpy listing", fg=AKZENT))

                threading.Thread(target=_create_groups, daemon=True).start()
                return
            # ── Geizhals listing: create one group per selected product variant ──────
            is_gh_listing = bool(source_url and "?fs=" in source_url and
                                 any(d in source_url for d in ["geizhals.de", "geizhals.eu", "geizhals.at"]))
            if is_gh_listing:
                selected_variants = [(sid, s) for sid, (var, s) in self._vg_shop_vars.items() if var.get()]
                if not selected_variants:
                    messagebox.showerror(T("error"), "Please select at least one variant.", parent=dlg)
                    return
                kat = v_kat.get().strip()
                dlg.destroy()

                def _create_gh_groups(_variants=selected_variants, _ziel=ziel,
                                      _bnv=buy_now_val, _kat=kat, _cur=waehrung):
                    total = len(_variants)
                    for i, (_, variant) in enumerate(_variants, 1):
                        vname = variant.get("name", variant.get("shop_name", "Product"))
                        self.after(0, lambda t=f"⏳ Loading shops {i}/{total}: {vname[:28]}...":
                                   self.status_check_lbl.config(text=t, fg=TEXT2))
                        try:
                            actual_shops, _ = shops_aus_url_laden(variant["url"])
                        except Exception as e:
                            log(f"Error loading shops for {vname}: {e}")
                            actual_shops = []
                        if not actual_shops:
                            actual_shops = [variant]

                        g = {"id":           str(int(time.time()*1000)) + str(i),
                             "name":          vname,
                             "zielpreis":     _ziel,
                             "buy_now_price": _bnv,
                             "kategorie":     _kat,
                             "shops":         [],
                             "alarm_gesendet": False,
                             "source_url":    variant["url"],
                             "currency":      _cur}
                        for j, s in enumerate(actual_shops):
                            g["shops"].append({
                                "id":        str(int(time.time()*1000)) + str(i) + str(j),
                                "url":       s["url"],
                                "shop":      s.get("shop_key", _shop_aus_url(s["url"])),
                                "shop_name": s.get("shop_name", s.get("name", "")),
                                "preis":     s["preis"],
                                "zuletzt":   datetime.now().strftime("%d.%m. %H:%M"),
                            })
                        self.vergleiche.append(g)
                        self.vg_aktuelle_gruppe = g["id"]

                    speichere_vergleiche(self.vergleiche)
                    self.after(0, self._vg_listbox_laden)
                    self.after(0, lambda: self.status_check_lbl.config(
                        text=f"✅ {total} groups created from Geizhals search", fg=AKZENT))

                threading.Thread(target=_create_gh_groups, daemon=True).start()
                return
            # ── Single group (normal path) ────────────────────────────────────────────
            g = {"id": str(int(time.time()*1000)), "name": name, "zielpreis": ziel,
                 "buy_now_price": buy_now_val, "kategorie": v_kat.get().strip(),
                 "shops": [], "alarm_gesendet": False, "source_url": source_url,
                 "currency": waehrung}
            # Shops erst mit Redirect-URL speichern, dann im Hintergrund auflösen
            shops_roh = []
            for sid, (var, s) in self._vg_shop_vars.items():
                if var.get():
                    shops_roh.append((sid, s))
                    g["shops"].append({
                        "id":        str(int(time.time()*1000)) + sid,
                        "url":       s["url"],  # Erst Redirect-URL
                        "shop":      s["shop_key"],
                        "shop_name": s.get("shop_name", s.get("name", s["shop_key"])),
                        "preis":     s["preis"],
                        "zuletzt":   datetime.now().strftime("%d.%m. %H:%M"),
                    })
            self.vergleiche.append(g)
            speichere_vergleiche(self.vergleiche)
            self.vg_aktuelle_gruppe = g["id"]
            self._vg_listbox_laden()
            dlg.destroy()

            # Im Hintergrund echte URLs auflösen
            def _urls_aufloesen():
                hat_redirects = any(
                    "geizhals.de/redir/" in s.get("url","") or "geizhals.at/redir/" in s.get("url","") or "geizhals.eu/redir/" in s.get("url","")
                    for s in g["shops"]
                )
                if not hat_redirects:
                    return
                gesamt = len([s for s in g["shops"] if "redir" in s.get("url","")])
                self.after(0, lambda: self.status_check_lbl.config(
                    text=f"🔗 Resolving {gesamt} shop URLs (one-time, ~{gesamt//3+1} min.)...",
                    fg=TEXT2))

                # Produktseite einmal laden, alle Shop-Links in neuen Tabs öffnen
                url_map = redirects_aufloesen_via_produktseite(source_url, g["shops"])

                # Ergebnisse eintragen
                aufgeloest = 0
                for s in g["shops"]:
                    shop_name = s.get("shop_name") or s["shop"]
                    if shop_name in url_map:
                        s["url"]  = url_map[shop_name]
                        s["shop"] = _shop_aus_url(url_map[shop_name])
                        aufgeloest += 1

                speichere_vergleiche(self.vergleiche)
                self.after(0, lambda: self.status_check_lbl.config(
                    text=f"✅ {aufgeloest}/{gesamt} URLs resolved", fg=AKZENT))
                ag = self._aktuelle_vg()
                if ag and ag["id"] == g["id"]:
                    self.after(0, lambda: self._vg_tabelle_laden(ag))

            threading.Thread(target=_urls_aufloesen, daemon=True).start()

        btn_such = self._btn(such_row, T("search_btn"), suchen, BG3, AKZENT)
        btn_such.pack(side="left", padx=(8,0), ipady=5)
        e_such.bind("<Return>", suchen)
        e_ziel.bind("<Return>", speichern)
        self._btn(dlg, T("create_group"), speichern, AKZENT, "#000").pack(
            padx=20, pady=(10,12), fill="x", ipady=8)
        dlg.lift()
        dlg.focus_force()
        if prefill_url:
            e_such.insert(0, prefill_url)
            dlg.after(300, suchen)

    # ── Shop manuell hinzufügen ───────────────────────────────────────────────
    def _vg_shop_manuell(self):
        g = self._aktuelle_vg()
        if not g:
            messagebox.showinfo(T("info"), T("select_group")); return
        dlg = tk.Toplevel(self)
        dlg.title(f"Add Shop — {g['name']}")
        self._center_dialog(dlg, 540, 220)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text="Product URL", bg=BG, fg=TEXT2,
                 font=(UI_FONT,10)).pack(anchor="w", padx=20, pady=(16,4))
        url_row = tk.Frame(dlg, bg=BG)
        url_row.pack(fill="x", padx=20)
        e_url = ttk.Entry(url_row)
        e_url.pack(side="left", fill="x", expand=True, ipady=5)
        e_url.focus()
        status_lbl = tk.Label(dlg, text="", bg=BG, fg=TEXT2, font=(UI_FONT,9), anchor="w")
        status_lbl.pack(fill="x", padx=20, pady=4)
        preis_var = tk.StringVar()

        def laden():
            url = e_url.get().strip()
            if not url.startswith("http"): return
            status_lbl.config(text="🔄  Loading price...", fg=TEXT2)
            def _t():
                shop = _shop_aus_url(url)
                p = preis_holen(url, shop)
                self.after(0, lambda: (
                    preis_var.set(f"{p:.2f}" if p else ""),
                    status_lbl.config(
                        text=f"✅ {p:.2f} €" if p else "⚠ Not found — please enter manually",
                        fg=AKZENT if p else GELB)
                ))
            threading.Thread(target=_t, daemon=True).start()

        self._btn(url_row, "🔍", laden, BG3, TEXT).pack(side="left", padx=(6,0), ipady=5)

        preis_row = tk.Frame(dlg, bg=BG)
        preis_row.pack(fill="x", padx=20, pady=4)
        tk.Label(preis_row, text="Price (€)", bg=BG, fg=TEXT2, width=10, anchor="w",
                 font=(UI_FONT,10)).pack(side="left")
        ttk.Entry(preis_row, textvariable=preis_var, width=10).pack(side="left", ipady=4)

        def hinzufuegen(*_):
            url = e_url.get().strip()
            if not url.startswith("http"):
                messagebox.showerror("Error", "Invalid URL.", parent=dlg); return
            try: preis = float(preis_var.get().replace(",","."))
            except: preis = None
            g["shops"].append({
                "id":      str(int(time.time()*1000)),
                "url":     url,
                "shop":    _shop_aus_url(url),
                "preis":   preis,
                "zuletzt": datetime.now().strftime("%d.%m. %H:%M"),
            })
            speichere_vergleiche(self.vergleiche)
            self._vg_tabelle_laden(g)
            dlg.destroy()

        e_url.bind("<Return>", lambda e: laden())
        self._btn(dlg, "➕  Add", hinzufuegen, AKZENT, "#000").pack(
            padx=20, pady=(4,12), fill="x", ipady=7)
        dlg.lift(); dlg.focus_force()

    # ── Löschen ───────────────────────────────────────────────────────────────
    def _vg_shop_oeffnen(self):
        """Öffnet Shop-URL im Browser bei Doppelklick."""
        sel = self.vg_tree.selection()
        if not sel: return
        g = self._aktuelle_vg()
        if not g: return
        shop = next((s for s in g["shops"] if s["id"] == sel[0]), None)
        if not shop: return
        import webbrowser
        webbrowser.open(shop["url"])

    def _vg_loeschen(self):
        sel = self.vg_listbox.curselection()
        if not sel: return
        g = self.vergleiche[sel[0]]
        if messagebox.askyesno(T("delete"), T("delete_confirm").replace("{name}", g["name"])):
            self.vergleiche = [x for x in self.vergleiche if x["id"] != g["id"]]
            self.vg_aktuelle_gruppe = None
            speichere_vergleiche(self.vergleiche)
            self.vg_titel_lbl.config(text=T("select_group"))
            self.vg_ziel_lbl.config(text="")
            for row in self.vg_tree.get_children(): self.vg_tree.delete(row)
            self._vg_listbox_laden()

    def _vg_shop_loeschen(self):
        sel = self.vg_tree.selection()
        if not sel: return
        g = self._aktuelle_vg()
        if not g: return
        shop = next((s for s in g["shops"] if s["id"] == sel[0]), None)
        if not shop: return
        if messagebox.askyesno("Remove",
                               f"'{shop.get('shop_name') or SHOPS.get(shop['shop'], shop['shop'])}' remove from group?"):
            g["shops"] = [s for s in g["shops"] if s["id"] != sel[0]]
            speichere_vergleiche(self.vergleiche)
            self._vg_tabelle_laden(g)

    def _vg_shop_einzeln_pruefen(self):
        """Prüft den Preis eines einzelnen Shops manuell (Rechtsklick → Check Price)."""
        sel = self.vg_tree.selection()
        if not sel: return
        g = self._aktuelle_vg()
        if not g: return
        shop = next((s for s in g["shops"] if s["id"] == sel[0]), None)
        if not shop: return
        shop_name = shop.get("shop_name") or shop["shop"]
        self.status_check_lbl.config(text=f"🔄 Checking {shop_name}...", fg=TEXT2)

        def _thread():
            source_url = g.get("source_url", "")
            is_pricespy = any(d in source_url for d in ["pricespy.co.uk","pricespy.com"]) if source_url else False
            preis = None
            if source_url and ("geizhals.de" in source_url or "geizhals.eu" in source_url or "geizhals.at" in source_url or is_pricespy):
                if is_pricespy:
                    neue_shops, _ = pricespy_laden(source_url, max_shops=999)
                else:
                    neue_shops, _ = shops_aus_url_laden(source_url, max_shops=999)
                if neue_shops:
                    preis_map = {s["name"].lower().strip(): s["preis"] for s in neue_shops}
                    sn = shop_name.lower().strip()
                    preis = preis_map.get(sn)
                    if not preis:
                        for key, val in preis_map.items():
                            if key in sn or sn in key:
                                preis = val
                                break
                    if not preis and len(sn) >= 4:
                        for key, val in preis_map.items():
                            if key[:5] == sn[:5]:
                                preis = val
                                break
            else:
                preis = preis_holen(shop["url"], shop["shop"])

            ts = datetime.now().strftime("%d.%m. %H:%M")
            shop["zuletzt"] = ts
            if preis:
                preis_alt = shop.get("preis")
                if preis_alt and abs(preis - preis_alt) > 0.01:
                    shop["preis_vorher"] = preis_alt
                    shop["preis_trend"] = "gesunken" if preis < preis_alt else "gestiegen"
                else:
                    shop.pop("preis_vorher", None)
                    shop.pop("preis_trend", None)
                shop["preis"] = preis
                verlauf = shop.get("verlauf", [])
                verlauf.append({"datum": datetime.now().strftime("%Y-%m-%d %H:%M"), "preis": preis})
                shop["verlauf"] = verlauf[-1000:]
            speichere_vergleiche(self.vergleiche)

            def _done():
                self._vg_tabelle_laden(g)
                self._vg_listbox_laden()
                cur = g.get("currency", "€")
                if preis:
                    self.status_check_lbl.config(
                        text=f"✅ {shop_name}: {cur}{preis:.2f}", fg=AKZENT)
                else:
                    self.status_check_lbl.config(
                        text=f"⚠ {shop_name}: no price found", fg=GELB)
            self.after(0, _done)

        threading.Thread(target=_thread, daemon=True).start()

    def _vg_shop_favorit_toggle(self):
        """Setzt oder entfernt den Favoriten-Status eines Shops."""
        sel = self.vg_tree.selection()
        if not sel: return
        g = self._aktuelle_vg()
        if not g: return
        shop = next((s for s in g["shops"] if s["id"] == sel[0]), None)
        if not shop: return
        shop["favorit"] = not shop.get("favorit", False)
        speichere_vergleiche(self.vergleiche)
        self._vg_tabelle_laden(g)

    # ── Preise prüfen ─────────────────────────────────────────────────────────
    def _vg_alle_pruefen(self):
        if not self.vergleiche:
            self.status_check_lbl.config(text=T("no_groups"), fg=GELB)
            return
        self.btn_pruefen.config(state="disabled", text=T("checking"))
        self.status_check_lbl.config(text="Fetching prices...", fg=TEXT2)
        threading.Thread(target=self._vg_check_alle, daemon=True).start()

    def _vg_check_alle(self):
        log("Price check started")
        gesamt_shops = sum(len(g["shops"]) for g in self.vergleiche)
        geprueft = 0
        alarme = []
        alle_aenderungen = []  # {gruppe_name, gruppe_ziel, shops: [...]}
        geaenderte_shops = []  # Shops with price change for current group

        for g in self.vergleiche:
            self.after(0, lambda name=g["name"]: self.status_check_lbl.config(
                text=T("checking_status").replace("{name}", name[:30]), fg=TEXT2))

            source_url = g.get("source_url", "")
            ts = datetime.now().strftime("%d.%m. %H:%M")

            is_pricespy = any(d in source_url for d in ["pricespy.co.uk","pricespy.com"]) if source_url else False
            if source_url and ("geizhals.de" in source_url or "geizhals.eu" in source_url or is_pricespy):
                # ── Geizhals/Idealo: Produktseite komplett neu laden
                log(f"  Loading product page: {source_url[:60]}")
                if is_pricespy:
                    neue_shops, _ = pricespy_laden(source_url, max_shops=999)
                else:
                    neue_shops, _ = shops_aus_url_laden(source_url, max_shops=999)
                if neue_shops:
                    # Preis-Map: Name (lowercase) → Preis
                    preis_map = {s["name"].lower().strip(): s["preis"] for s in neue_shops}
                    log(f"  Found: {list(preis_map.keys())[:5]}...")
                    for s in g["shops"]:
                        shop_name = (s.get("shop_name") or s["shop"]).lower().strip()
                        # 1. Exakter Match
                        preis = preis_map.get(shop_name)
                        # 2. Teilstring-Match
                        if not preis:
                            for key, val in preis_map.items():
                                if key in shop_name or shop_name in key:
                                    preis = val
                                    break
                        # 3. Fuzzy: ersten 5 Zeichen vergleichen
                        if not preis and len(shop_name) >= 4:
                            prefix = shop_name[:5]
                            for key, val in preis_map.items():
                                if key.startswith(prefix) or key[:5] == prefix:
                                    preis = val
                                    break
                        name_anzeige = s.get("shop_name") or s["shop"]
                        s["zuletzt"] = ts
                        if preis:
                            preis_alt = s.get("preis")
                            # Preisänderung erkennen (mehr als 0.01€ Unterschied)
                            if preis_alt and abs(preis - preis_alt) > 0.01:
                                # Echte Shop-URL ermitteln (nicht Geizhals-Redirect)
                                shop_url = s.get("url_real") or s["url"]
                                if "geizhals.de/redir/" in shop_url or "geizhals.at/redir/" in shop_url or "geizhals.eu/redir/" in shop_url:
                                    # Redirect per requests auflösen
                                    try:
                                        r = requests.get(shop_url, headers=HEADERS,
                                                         timeout=10, allow_redirects=True, stream=True)
                                        aufgeloest = r.url
                                        r.close()
                                        if "geizhals" not in aufgeloest:
                                            shop_url = aufgeloest
                                            s["url_real"] = aufgeloest
                                    except:
                                        pass
                                geaenderte_shops.append({
                                    "shop_name": name_anzeige,
                                    "url":       shop_url,
                                    "preis_alt": preis_alt,
                                    "preis_neu": preis,
                                })
                                # Änderung im Shop-Objekt merken für Tabellenanzeige
                                s["preis_vorher"] = preis_alt
                                s["preis_trend"]  = "gesunken" if preis < preis_alt else "gestiegen"
                            else:
                                # Keine Änderung: alten Trend nach 1 Prüfzyklus löschen
                                s.pop("preis_vorher", None)
                                s.pop("preis_trend",  None)
                            s["preis"] = preis
                            # Preisverlauf: jeden Check speichern (max 1000 Einträge)
                            verlauf = s.get("verlauf", [])
                            jetzt = datetime.now().strftime("%Y-%m-%d %H:%M")
                            verlauf.append({"datum": jetzt, "preis": preis})
                            verlauf = verlauf[-1000:]
                            s["verlauf"] = verlauf
                            log(f"  {name_anzeige}: {preis:.2f} ✓")
                        else:
                            log(f"  {name_anzeige}: nicht gefunden (gespeichert: '{shop_name}')")
                        geprueft += 1

                    # Neue Shops hinzufügen + nicht mehr gelistete entfernen
                    geizhals_namen = {ns["name"].lower() for ns in neue_shops}
                    bestehende_namen = {(s.get("shop_name") or s["shop"]).lower() for s in g["shops"]}

                    # Neue Shops hinzufügen
                    for ns in neue_shops:
                        if ns["name"].lower() not in bestehende_namen:
                            # Redirect durch Geizhals-Produktseite ersetzen
                            shop_url = source_url if ("geizhals.de/redir/" in ns["url"] or "geizhals.at/redir/" in ns["url"] or "geizhals.eu/redir/" in ns["url"]) else ns["url"]
                            g["shops"].append({
                                "id":        str(int(time.time()*1000)) + ns["name"][:5],
                                "url":       shop_url,
                                "url_redir": ns["url"],
                                "shop":      ns["shop_key"],
                                "shop_name": ns["name"],
                                "preis":     ns["preis"],
                                "zuletzt":   ts,
                            })
                            log(f"  New shop added: {ns['name']} ({ns['preis']:.2f} €)")

                    # Nicht mehr gelistete Shops entfernen
                    vorher = len(g["shops"])
                    g["shops"] = [
                        s for s in g["shops"]
                        if (s.get("shop_name") or s["shop"]).lower() in geizhals_namen
                    ]
                    entfernt = vorher - len(g["shops"])
                    if entfernt > 0:
                        log(f"  {entfernt} shop(s) no longer on Geizhals — removed")
                else:
                    log(f"  Product page could not be loaded")
                    geprueft += len(g["shops"])
            else:
                # ── Keine Geizhals-URL: Einzelne Shop-URLs prüfen
                for s in g["shops"]:
                    shop_anzeige = s.get("shop_name") or s["shop"]
                    self.after(0, lambda n=shop_anzeige, i=geprueft, t=gesamt_shops:
                        self.status_check_lbl.config(text=f"🔄  {n} ({i+1}/{t})", fg=TEXT2))
                    p = preis_holen(s["url"], s["shop"])
                    log(f"  {shop_anzeige}: {p:.2f} € ✓" if p else f"  {shop_anzeige}: kein Preis")
                    s["zuletzt"] = ts  # immer aktualisieren
                    if p:
                        s["preis"] = p
                    geprueft += 1

            # Tabelle live aktualisieren
            ag = self._aktuelle_vg()
            if ag and ag["id"] == g["id"]:
                self.after(0, lambda gg=g: self._vg_tabelle_laden(gg))

            preise = [s["preis"] for s in g["shops"] if s.get("preis")]
            if preise:
                bester = min(preise)
                bester_shop = next((s.get("shop_name") or SHOPS.get(s["shop"],s["shop"])
                                    for s in g["shops"] if s.get("preis") == bester), "")
                log(f"  {g['name']}: {g.get('currency','€')}{bester:.2f} at {bester_shop}")

                # Zielpreis-Alarm
                cur = g.get("currency", "EUR")
                cur_sym = "GBP" if cur == "£" else "EUR"
                buy_now = g.get("buy_now_price")
                if buy_now and bester <= buy_now and not g.get("buynow_gesendet"):
                    g["buynow_gesendet"] = True
                    _titel = T("buy_now_notif")
                    _text  = f"{g['name'][:40]}\n{bester_shop}: {bester:.2f} {cur_sym}"
                    self.after(0, lambda t=_titel, x=_text: toast(t, x))
                elif buy_now and bester > buy_now:
                    g["buynow_gesendet"] = False

                if bester <= g["zielpreis"] and not g.get("alarm_gesendet"):
                    g["alarm_gesendet"] = True
                    alarme.append({"name": g["name"], "bester": bester, "shop": bester_shop, "currency": cur})
                    _titel = T("target_reached_notif")
                    _text  = f"{g['name'][:40]}\n{bester_shop}: {bester:.2f} {cur_sym}"
                    self.after(0, lambda t=_titel, x=_text: toast(t, x))
                elif bester > g["zielpreis"]:
                    g["alarm_gesendet"] = False

                # Änderungen sammeln für Gesamt-Mail am Ende
                if geaenderte_shops:
                    gesunken  = len([s for s in geaenderte_shops if s["preis_neu"] < s["preis_alt"]])
                    gestiegen = len([s for s in geaenderte_shops if s["preis_neu"] > s["preis_alt"]])
                    log(f"  Price changes: {gesunken} decreased, {gestiegen} increased")
                    # Zielpreis-Info pro Shop hinzufügen
                    for s in geaenderte_shops:
                        s["zielpreis"]       = g["zielpreis"]
                        s["ziel_erreicht"]   = s["preis_neu"] <= g["zielpreis"]
                    alle_aenderungen.append({
                        "gruppe_name": g["name"],
                        "zielpreis":   g["zielpreis"],
                        "currency":    g.get("currency", "€"),
                        "shops":       list(geaenderte_shops),
                    })

            geaenderte_shops = []  # Reset for next group

        speichere_vergleiche(self.vergleiche)
        ts = datetime.now().strftime("%H:%M")

        # Eine zusammengefasste Mail für alle Änderungen + Alarme
        if self.config_data.get("email_absender") and (alle_aenderungen or alarme):
            threading.Thread(
                target=email_zusammenfassung,
                args=(self.config_data, alle_aenderungen, alarme),
                daemon=True
            ).start()

        def _fertig():
            self.btn_pruefen.config(state="normal", text=T("check_all"))
            # Countdown neu starten nach manuellem Check
            intervall = self.config_data.get("intervall", 6) * 3600
            self._naechster_check_ts = time.time() + intervall
            self._countdown_update()
            if alarme:
                self.status_check_lbl.config(
                    text=f"🔔 Alert! {alarme[0]['name']}: {alarme[0].get('currency','€')}{alarme[0]['bester']:.2f}", fg=AKZENT)
            else:
                self.status_check_lbl.config(
                    text=T("prices_checked").replace("{n}", str(geprueft)).replace("{ts}", ts), fg=AKZENT)
            self._vg_listbox_laden()
            ag = self._aktuelle_vg()
            if ag:
                self._vg_tabelle_laden(ag)
            self._log_refresh()

        self.after(0, _fertig)
        # Gruppen ohne source_url hinweisen
        ohne_quelle = [g["name"] for g in self.vergleiche if not g.get("source_url")]
        if ohne_quelle:
            log(f"  Note: {len(ohne_quelle)} Gruppe(n) ohne Geizhals-URL — Gruppe löschen und neu anlegen für automatische Updates")
        log(f"Price check completed ({geprueft} Shops)")

    # ── Einstellungen ─────────────────────────────────────────────────────────
    def _cfg_speichern(self):
        region_key = next((k for k in REGIONS if _region_display(k) == self.v_region.get()), "de")
        digest_day_idx = self._digest_weekdays.index(self.v_digest_day.get()) \
                         if self.v_digest_day.get() in self._digest_weekdays else 0
        self.config_data.update({
            "email_absender":      self.v_abs.get().strip(),
            "email_passwort":      self.v_pw.get(),
            "email_empfaenger":    self.v_emp.get().strip(),
            "smtp_server":         self.v_smtp.get().strip(),
            "smtp_port":           int(self.v_port.get() or 587),
            "intervall":           max(1, min(24, int(self.v_int.get() or 6))),
            "check_window_active": self.v_time_active.get(),
            "check_time_from":     self.v_time_from.get(),
            "check_time_to":       self.v_time_to.get(),
            "region":              region_key,
            "digest_active":       self.v_digest_active.get(),
            "digest_day":          digest_day_idx,
            "digest_time":         self.v_digest_time.get(),
        })
        speichere_config(self.config_data)
        messagebox.showinfo(T("saved"), T("settings_saved"))

    def _test_notification(self):
        """Send a test Windows notification with real shop data if available."""
        # Try to show real data from current group
        g = self._aktuelle_vg()
        if g and g.get("shops"):
            preise = [s for s in g["shops"] if s.get("preis")]
            if preise:
                bester = min(preise, key=lambda s: s["preis"])
                cur = g.get("currency", "€")
                cur_sym = "GBP" if cur == "£" else "EUR"
                shop_name = bester.get("shop_name") or bester.get("shop", "")
                titel = "Price Alert Tracker - Test"
                text  = f"{g['name'][:40]}\nBest: {bester['preis']:.2f} {cur_sym} at {shop_name}"
                toast(titel, text)
                self.status_check_lbl.config(
                    text=f"Test: {bester['preis']:.2f} {cur_sym} at {shop_name}", fg=AKZENT)
                return
        # Fallback if no group selected
        toast("Price Alert Tracker", "Test - notifications are working!")
        self.status_check_lbl.config(text="Test notification sent", fg=AKZENT)

    def _test_email(self):
        if not self.config_data.get("email_absender"):
            messagebox.showerror(T("error"), T("save_first")); return
        ok = email_senden(self.config_data, {"name":"Test","shops":[]}, 99.99, "Testshop")
        if ok:
            messagebox.showinfo(T("success"), T("email_sent"))
        else:
            messagebox.showerror("Error", "Email could not be sent.")

    # ── Autostart & Tray ─────────────────────────────────────────────────────
    def _lang_aendern(self):
        """Switch language live — no restart needed."""
        selected = self.v_lang.get()
        lang_code = next((k for k, v in LANGUAGES.items() if v == selected), "en")
        self.config_data["language"] = lang_code
        speichere_config(self.config_data)
        self._rebuild_ui()

    def _font_aendern(self):
        """Switch font live — no restart needed."""
        selected_label = self.v_font.get()
        font_id = next((k for k, v in FONTS.items() if v["label"] == selected_label), "segoe")
        self.config_data["font"] = font_id
        speichere_config(self.config_data)
        global UI_FONT
        UI_FONT = FONTS[font_id]["name"]
        self._rebuild_ui()

    def _rebuild_ui(self):
        """Rebuild entire UI with current language and font."""
        # Remember active tab
        active = self._active_tab[0] if self._active_tab else "compare"
        # Destroy everything below the accent bar
        for widget in self.winfo_children():
            widget.destroy()
        # Reset state
        self._tab_btns = {}
        self._active_tab = [None]
        # Rebuild
        self._build_ui()
        # Restore active tab
        tab_map = {
            "compare":  self.tab_vergleich,
            "settings": self.tab_einst,
            "log":      self.tab_log,
        }
        if active in self._tab_btns and active in tab_map:
            btn, ind = self._tab_btns[active]
            for f in [self.tab_vergleich, self.tab_einst, self.tab_log]:
                f.pack_forget()
            tab_map[active].pack(fill="both", expand=True)
            for key, (b, i) in self._tab_btns.items():
                b.config(fg=TEXT if key == active else GRAU)
                i.config(bg=AKZENT if key == active else BG2)
            self._active_tab[0] = active
        # Reload group list
        self._vg_laden()

    def _theme_aendern(self):
        """Switch theme and restart app."""
        selected_name = self.v_theme.get()
        theme_id = next((k for k, v in THEMES.items() if v["name"] == selected_name), "dark_mint")
        self.config_data["theme"] = theme_id
        speichere_config(self.config_data)
        import subprocess as _sp
        script = str(Path(__file__).resolve())
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        if not Path(exe).exists():
            exe = sys.executable
        _sp.Popen([exe, script], creationflags=getattr(_sp, "DETACHED_PROCESS", 0))
        self.after(300, self.destroy)

    def _autostart_toggle(self):
        aktiv = self.v_autostart.get()
        if autostart_setzen(aktiv):
            msg = "Autostart enabled." if aktiv else "Autostart disabled."
            self.status_check_lbl.config(text=f"✅ {msg}", fg=AKZENT)
        else:
            messagebox.showerror("Error", "Autostart could not be set.")
            self.v_autostart.set(not aktiv)

    def _tray_toggle(self):
        self.config_data["minimize_to_tray"] = self.v_tray.get()
        speichere_config(self.config_data)

    def _fenster_schliessen(self):
        """X button: minimize to tray or quit depending on setting."""
        if self.config_data.get("minimize_to_tray", True) and TRAY_OK:
            self.withdraw()  # Fenster verstecken
            self._tray_starten()
        else:
            self._beenden()

    def _tray_starten(self):
        if self._tray_icon:
            return
        if not TRAY_OK:
            return

        def zeigen(icon, item):
            icon.stop()
            self._tray_icon = None
            self.after(0, self.deiconify)
            self.after(0, self.lift)

        def beenden(icon, item):
            icon.stop()
            self._tray_icon = None
            self.after(0, self._beenden)

        def pruefen(icon, item):
            self.after(0, self._vg_alle_pruefen)

        menu = pystray.Menu(
            TrayItem(T("app_title"), zeigen, default=True),
            TrayItem("🔄 Check Now",         pruefen),
            pystray.Menu.SEPARATOR,
            TrayItem("❌ Quit",               beenden),
        )
        # Use icon.ico for tray if available
        icon_path = _resource_path("icon.ico")
        if icon_path.exists():
            from PIL import Image as _PilImg
            img = _PilImg.open(str(icon_path))
        else:
            img = tray_icon_erstellen()
        self._tray_icon = pystray.Icon("PreisAlarm", img, "Price Alert Tracker", menu)
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._tray_thread.start()

    def _beenden(self):
        if self._tray_icon:
            try: self._tray_icon.stop()
            except: pass
        self.destroy()

    def _clipboard_monitor_starten(self):
        """Überwacht die Zwischenablage auf Shop-URLs und zeigt ein Popup."""
        self._last_clipboard  = ""
        self._clipboard_busy  = False

        SUPPORTED = [
            "geizhals.de", "geizhals.eu", "geizhals.at",
            "amazon.de", "amazon.co.uk", "amazon.com",
            "pricespy.co.uk", "pricespy.com", "idealo.de",
        ]

        def _check():
            if not self._clipboard_busy:
                try:
                    text = self.clipboard_get().strip()
                    if text != self._last_clipboard:
                        self._last_clipboard = text
                        if text.startswith("http") and any(d in text for d in SUPPORTED):
                            bereits = any(
                                g.get("source_url","") == text or
                                any(s.get("url","") == text for s in g.get("shops",[]))
                                for g in self.vergleiche
                            )
                            if not bereits:
                                self._clipboard_busy = True
                                self.after(0, lambda u=text: self._clipboard_popup(u))
                except:
                    pass
            self.after(1500, _check)

        self.after(3000, _check)

    def _clipboard_popup(self, url):
        """Zeigt ein kleines Popup wenn eine Shop-URL erkannt wurde."""
        popup = tk.Toplevel(self)
        popup.title("")
        popup.attributes("-topmost", True)
        popup.configure(bg=BG2)
        popup.resizable(False, False)
        popup.overrideredirect(True)

        # Position: unten rechts auf dem Bildschirm
        pw, ph = 400, 105
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        popup.geometry(f"{pw}x{ph}+{sw - pw - 20}+{sh - ph - 60}")

        tk.Frame(popup, bg=AKZENT, height=3).pack(fill="x")
        main_f = tk.Frame(popup, bg=BG2)
        main_f.pack(fill="both", expand=True, padx=14, pady=10)

        tk.Label(main_f, text="📋  " + T("clipboard_detected"),
                 bg=BG2, fg=TEXT, font=(UI_FONT, 10, "bold")).pack(anchor="w")
        display_url = url[:55] + "…" if len(url) > 55 else url
        tk.Label(main_f, text=display_url, bg=BG2, fg=GRAU,
                 font=(UI_FONT, 8)).pack(anchor="w", pady=(2, 6))

        btn_f = tk.Frame(main_f, bg=BG2)
        btn_f.pack(anchor="e")

        def _add():
            popup.destroy()
            self._clipboard_busy = False
            self._vg_neu(prefill_url=url)

        def _skip():
            popup.destroy()
            self._clipboard_busy = False

        self._btn(btn_f, "➕  " + T("add_to_tracker"), _add, AKZENT, "#000").pack(side="left", padx=(0, 6))
        self._btn(btn_f, "✕", _skip, BG3, TEXT2).pack(side="left")

        # Countdown-Balken (8 Sekunden)
        bar_frame = tk.Frame(popup, bg=BG3, height=3)
        bar_frame.pack(fill="x", side="bottom")
        bar = tk.Frame(bar_frame, bg=AKZENT, height=3)
        bar.place(relwidth=1.0, rely=0, relheight=1.0)

        start = time.time()
        duration = 8.0

        def _tick():
            if not popup.winfo_exists():
                return
            elapsed = time.time() - start
            remaining = max(0.0, 1.0 - elapsed / duration)
            bar.place(relwidth=remaining)
            if remaining > 0:
                popup.after(50, _tick)
            else:
                _skip()

        popup.after(50, _tick)

    def _auto_check_starten(self):
        """Starts automatic price check — first check after X hours (per interval setting)."""
        def check_und_planen():
            if self.vergleiche:
                threading.Thread(target=self._vg_check_alle, daemon=True).start()
            intervall = self.config_data.get("intervall", 6) * 3600 * 1000
            self._naechster_check_ts = time.time() + intervall / 1000
            self.after(intervall, check_und_planen)

        intervall = self.config_data.get("intervall", 6) * 3600 * 1000
        self._naechster_check_ts = time.time() + intervall / 1000
        self.after(intervall, check_und_planen)
        self._countdown_update()

    def _digest_scheduler_starten(self):
        """Prüft jede Minute ob der wöchentliche Bericht gesendet werden soll."""
        def _check():
            try:
                cfg = self.config_data
                if cfg.get("digest_active"):
                    from datetime import datetime as _dt
                    now = _dt.now()
                    digest_day  = cfg.get("digest_day", 0)   # 0=Montag
                    digest_time = cfg.get("digest_time", "08:00")
                    if now.weekday() == digest_day:
                        try:
                            h, m = map(int, digest_time.split(":"))
                            in_fenster = (now.hour == h and m <= now.minute <= m + 4)
                        except:
                            in_fenster = False
                        if in_fenster:
                            last = cfg.get("digest_last_sent", "")
                            today = now.strftime("%Y-%m-%d")
                            if last != today:
                                cfg["digest_last_sent"] = today
                                speichere_config(cfg)
                                threading.Thread(
                                    target=email_wochenbericht,
                                    args=(cfg, self.vergleiche),
                                    daemon=True
                                ).start()
                                log("Wöchentlicher Bericht wird gesendet")
            except Exception:
                pass
            self.after(60000, _check)
        self.after(60000, _check)

    def _countdown_update(self):
        """Aktualisiert das Countdown-Label jede Minute."""
        try:
            verbleibend = int(self._naechster_check_ts - time.time())
            if verbleibend <= 0:
                self.countdown_lbl.config(text="⏳ checking soon...")
            else:
                h = verbleibend // 3600
                m = (verbleibend % 3600) // 60
                if h > 0:
                    self.countdown_lbl.config(text=f"⏱ next check in {h}h {m:02d}m")
                else:
                    self.countdown_lbl.config(text=f"⏱ next check in {m}m")
        except:
            pass
        self.after(30000, self._countdown_update)

    # ── AI Analysis ───────────────────────────────────────────────────────────
    def _vg_ai_analyse(self):
        g = self._aktuelle_vg()
        if not g:
            messagebox.showinfo(T("info"), T("select_group"))
            return
        shops  = g.get("shops", [])
        cur    = g.get("currency", "€")
        ziel   = g["zielpreis"]

        # Collect price history
        alle_punkte = []
        for s in shops:
            for e in s.get("verlauf", []):
                try:
                    from datetime import datetime as _dt
                    ts = _dt.strptime(e["datum"][:16], "%Y-%m-%d %H:%M").timestamp()
                    alle_punkte.append((ts, e["preis"]))
                except: pass
        alle_punkte.sort()

        preise_aktuell = [s["preis"] for s in shops if s.get("preis")]
        if not preise_aktuell:
            messagebox.showinfo(T("info"), T("no_prices_yet"))
            return

        preis_jetzt = min(preise_aktuell)
        preis_avg   = sum(preise_aktuell) / len(preise_aktuell)

        # ── Analyse-Algorithmen ────────────────────────────────────────────────
        import statistics as _stats

        # 1. Trendanalyse (lineare Regression)
        trend_text = "Not enough data"
        trend_pct  = 0
        if len(alle_punkte) >= 3:
            xs = [p[0] for p in alle_punkte]
            ys = [p[1] for p in alle_punkte]
            n  = len(xs)
            x_mean = sum(xs) / n
            y_mean = sum(ys) / n
            num   = sum((xs[i]-x_mean)*(ys[i]-y_mean) for i in range(n))
            denom = sum((xs[i]-x_mean)**2 for i in range(n))
            slope = num/denom if denom != 0 else 0
            # Slope per day
            slope_per_day = slope * 86400
            trend_pct = (slope_per_day / y_mean) * 100 if y_mean else 0
            if trend_pct < -0.5:
                trend_text = T("trend_falling").replace("{pct}", f"{trend_pct:.1f}")
            elif trend_pct > 0.5:
                trend_text = T("trend_rising").replace("{pct}", f"+{trend_pct:.1f}")
            else:
                trend_text = T("trend_stable").replace("{pct}", f"{trend_pct:+.1f}")

        # 2. Volatilität
        volatil_text = "Not enough data"
        if len(alle_punkte) >= 4:
            vals = [p[1] for p in alle_punkte]
            try:
                std = _stats.stdev(vals)
                cv  = (std / _stats.mean(vals)) * 100
                if cv < 2:
                    volatil_text = T("volat_stable").replace("{pct}", f"{cv:.1f}")
                elif cv < 5:
                    volatil_text = T("volat_moderate").replace("{pct}", f"{cv:.1f}")
                else:
                    volatil_text = T("volat_high").replace("{pct}", f"{cv:.1f}")
            except: pass

        # 3. Saisonale Muster
        saison_text = ""
        if len(alle_punkte) >= 10:
            from datetime import datetime as _dt
            monat_preise = {}
            for ts, pr in alle_punkte:
                m = _dt.fromtimestamp(ts).month
                monat_preise.setdefault(m, []).append(pr)
            if monat_preise:
                guenstigster_monat = min(monat_preise, key=lambda m: sum(monat_preise[m])/len(monat_preise[m]))
                monate = ["Jan","Feb","Mar","Apr","May","Jun",
                          "Jul","Aug","Sep","Oct","Nov","Dec"]
                saison_text = T("hist_cheapest").replace("{month}", monate[guenstigster_monat-1])

        # 4. Kaufempfehlung
        abstand_zum_ziel = ((preis_jetzt - ziel) / ziel) * 100 if ziel else 0

        if preis_jetzt <= ziel:
            empfehlung = T("buy_now")
            empf_grund = f"{T('at_target')} ({cur}{ziel:.2f})"
            empf_farbe = "#22c55e"
        elif len(alle_punkte) >= 3 and trend_pct < -0.3 and abstand_zum_ziel < 15:
            empfehlung = T("wait_falling")
            empf_grund = T("above_target_falling").replace("{pct}", f"{abstand_zum_ziel:.1f}")
            empf_farbe = "#f59e0b"
        elif len(alle_punkte) >= 3 and trend_pct > 0.5:
            empfehlung = T("buy_soon")
            empf_grund = T("price_rising_grund")
            empf_farbe = "#ef4444"
        elif abstand_zum_ziel < 5:
            empfehlung = T("almost")
            empf_grund = T("almost_grund").replace("{pct}", f"{abstand_zum_ziel:.1f}")
            empf_farbe = "#f59e0b"
        elif abstand_zum_ziel > 30:
            empfehlung = T("wait")
            empf_grund = T("above_target_wait").replace("{pct}", f"{abstand_zum_ziel:.1f}")
            empf_farbe = "#60a5fa"
        else:
            empfehlung = T("monitor")
            empf_grund = T("above_target_track").replace("{pct}", f"{abstand_zum_ziel:.1f}")
            empf_farbe = "#94a3b8"

        # 5. Allzeit-Tief vs. jetzt
        allzeit_text = ""
        if alle_punkte:
            allzeit_tief = min(p[1] for p in alle_punkte)
            diff_vom_tief = ((preis_jetzt - allzeit_tief) / allzeit_tief) * 100
            if diff_vom_tief < 2:
                allzeit_text = T("alltime_low_near").replace("{pct}", f"{diff_vom_tief:.1f}")
            elif diff_vom_tief < 10:
                allzeit_text = T("alltime_low_close").replace("{pct}", f"{diff_vom_tief:.1f}")
            else:
                allzeit_text = T("alltime_above").replace("{pct}", f"{diff_vom_tief:.1f}").replace("{cur}", cur).replace("{price}", f"{allzeit_tief:.2f}")

        # ── UI ─────────────────────────────────────────────────────────────────
        dlg = tk.Toplevel(self)
        dlg.title(f"🤖 {T('ai_title')} — {g['name']}")
        self._center_dialog(dlg, 600, 780)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)

        # Header
        hdr_f = tk.Frame(dlg, bg="#1e1b4b")
        hdr_f.pack(fill="x")
        tk.Label(hdr_f, text="🤖  " + T("ai_title"), bg="#1e1b4b", fg="#a78bfa",
                 font=(UI_FONT, 13, "bold")).pack(anchor="w", padx=20, pady=(14,2))
        tk.Label(hdr_f, text=g["name"], bg="#1e1b4b", fg=TEXT2,
                 font=(UI_FONT, 10)).pack(anchor="w", padx=20, pady=(0,12))

        # Recommendation box
        rec_f = tk.Frame(dlg, bg=BG2)
        rec_f.pack(fill="x", padx=16, pady=(12,4))
        tk.Label(rec_f, text=T("recommendation"), bg=BG2, fg=TEXT2,
                 font=(UI_FONT, 8, "bold")).pack(anchor="w", padx=14, pady=(10,4))
        tk.Label(rec_f, text=empfehlung, bg=BG2, fg=empf_farbe,
                 font=(UI_FONT, 16, "bold")).pack(anchor="w", padx=14, pady=(0,4))
        tk.Label(rec_f, text=empf_grund, bg=BG2, fg=TEXT2,
                 font=(UI_FONT, 9), wraplength=500, justify="left").pack(
                 anchor="w", padx=14, pady=(0,12))

        def section(text):
            tk.Label(dlg, text=text, bg=BG, fg="#a78bfa",
                     font=(UI_FONT, 9, "bold")).pack(anchor="w", padx=16, pady=(10,2))
            tk.Frame(dlg, bg="#2d2060", height=1).pack(fill="x", padx=16)

        def row(label, value, color=TEXT2):
            r = tk.Frame(dlg, bg=BG2)
            r.pack(fill="x", padx=16, pady=1)
            tk.Label(r, text=label, bg=BG2, fg=GRAU,
                     font=(UI_FONT, 9), width=22, anchor="w").pack(side="left", padx=10, pady=6)
            tk.Label(r, text=value, bg=BG2, fg=color,
                     font=(UI_FONT, 9, "bold"), anchor="e").pack(side="right", padx=10)

        section("📊  " + T("price_analysis"))
        row(T("cur_best"),   f"{cur}{preis_jetzt:.2f}", AKZENT)
        row(T("your_target"),          f"{cur}{ziel:.2f}", "#a78bfa")
        row(T("dist_target"),   f"{abstand_zum_ziel:+.1f}%",
            AKZENT if abstand_zum_ziel <= 0 else ("#f59e0b" if abstand_zum_ziel < 10 else TEXT2))
        if allzeit_text:
            row(T("vs_alltime"), allzeit_text, AKZENT if "all-time low" in allzeit_text else TEXT2)

        section("📈  " + T("trend_volatility"))
        row(T("price_trend"),      trend_text)
        row(T("price_stab"),  volatil_text)
        row(T("data_points"),      str(len(alle_punkte)))
        if saison_text:
            row(T("seasonal"), saison_text, "#60a5fa")

        section("💡  " + T("insight"))
        # Extra insight
        if len(preise_aktuell) > 1:
            spread = max(preise_aktuell) - min(preise_aktuell)
            row(T("price_spread"), f"{cur}{spread:.2f}",
                AKZENT if spread > 20 else TEXT2)
            if spread > 20:
                insight = f"Big difference between shops! Cheapest saves you {cur}{spread:.2f} vs most expensive."
            else:
                insight = "Shops are closely priced — not much to gain from switching shops."
            r2 = tk.Frame(dlg, bg=BG2)
            r2.pack(fill="x", padx=16, pady=1)
            tk.Label(r2, text=insight, bg=BG2, fg=TEXT2,
                     font=(UI_FONT, 9), wraplength=460, justify="left").pack(
                     anchor="w", padx=10, pady=8)

        note = tk.Label(dlg,
            text="ℹ  Analysis based on collected price data. More data = better accuracy.",
            bg=BG, fg=GRAU, font=(UI_FONT, 8), wraplength=460)
        note.pack(anchor="w", padx=16, pady=(8,4))

        self._btn(dlg, T("close"), dlg.destroy, BG3, TEXT).pack(pady=10, ipadx=20)
        dlg.lift()
        dlg.focus_force()

    # ── Statistics ────────────────────────────────────────────────────────────
    def _vg_statistiken(self):
        g = self._aktuelle_vg()
        if not g:
            messagebox.showinfo(T("info"), T("select_group"))
            return
        shops = g.get("shops", [])
        if not shops:
            messagebox.showinfo(T("info"), T("no_prices_yet"))
            return
        cur = g.get("currency", "€")
        preise = [s["preis"] for s in shops if s.get("preis")]
        if not preise:
            messagebox.showinfo(T("info"), T("no_prices_yet"))
            return
        alle_verlauf = []
        for s in shops:
            for e in s.get("verlauf", []):
                alle_verlauf.append(e["preis"])
        guenstigster_shop = min(shops, key=lambda s: s.get("preis") or 99999)
        teuerster_shop    = max(shops, key=lambda s: s.get("preis") or 0)
        dlg = tk.Toplevel(self)
        dlg.title(f"{T('price_analysis')} — {g['name']}")
        self._center_dialog(dlg, 560, 660)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)

        tk.Label(dlg, text=f"📊  {g['name']}", bg=BG, fg=TEXT,
                 font=(UI_FONT, 13, "bold")).pack(anchor="w", padx=20, pady=(16,12))

        def stat_row(label, value, color=TEXT):
            r = tk.Frame(dlg, bg=BG2)
            r.pack(fill="x", padx=20, pady=2)
            tk.Label(r, text=label, bg=BG2, fg=TEXT2,
                     font=(UI_FONT, 10), width=24, anchor="w").pack(side="left", padx=12, pady=8)
            tk.Label(r, text=value, bg=BG2, fg=color,
                     font=(UI_FONT, 10, "bold"), anchor="e").pack(side="right", padx=12)

        stat_row(T("shops_tracked"),    str(len(shops)))
        stat_row(T("target_price_lbl"), f"{cur}{g['zielpreis']:.2f}")
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x", padx=20, pady=6)
        stat_row(T("cur_best"),   f"{cur}{min(preise):.2f}", AKZENT)
        stat_row(T("cur_avg"),    f"{cur}{sum(preise)/len(preise):.2f}", "#60a5fa")
        stat_row(T("cur_worst"),  f"{cur}{max(preise):.2f}", "#f87171")
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x", padx=20, pady=6)
        if alle_verlauf:
            stat_row(T("alltime_low"),  f"{cur}{min(alle_verlauf):.2f}", AKZENT)
            stat_row(T("alltime_high"), f"{cur}{max(alle_verlauf):.2f}", "#f87171")
            stat_row(T("alltime_avg"),  f"{cur}{sum(alle_verlauf)/len(alle_verlauf):.2f}", "#60a5fa")
            stat_row(T("total_points"), str(len(alle_verlauf)))
        tk.Frame(dlg, bg=BORDER, height=1).pack(fill="x", padx=20, pady=6)
        sn = guenstigster_shop.get("shop_name") or guenstigster_shop["shop"]
        stat_row(T("cheapest_shop"),   f"{sn}  ({cur}{guenstigster_shop.get('preis',0):.2f})", AKZENT)
        sn2 = teuerster_shop.get("shop_name") or teuerster_shop["shop"]
        stat_row(T("expensive_shop"),  f"{sn2}  ({cur}{teuerster_shop.get('preis',0):.2f})", "#f87171")
        savings = max(preise) - min(preise)
        stat_row(T("max_savings"), f"{cur}{savings:.2f}", AKZENT)
        self._btn(dlg, T("close"), dlg.destroy, BG3, TEXT).pack(pady=16, ipadx=20)
        dlg.lift()
        dlg.focus_force()

    # ── Preisverlauf Chart ───────────────────────────────────────────────────
    def _vg_chart_zeigen(self):
        g = self._aktuelle_vg()
        if not g:
            messagebox.showinfo(T("info"), T("select_group"))
            return

        # Preisverlauf: pro Zeitpunkt günstigsten UND Durchschnittspreis sammeln
        tages_preise = {}   # timestamp -> lowest price
        tages_summen = {}   # timestamp -> [all prices] for average
        for s in g["shops"]:
            for eintrag in s.get("verlauf", []):
                datum = eintrag["datum"][:16]
                preis = eintrag["preis"]
                if datum not in tages_preise or preis < tages_preise[datum]:
                    tages_preise[datum] = preis
                tages_summen.setdefault(datum, []).append(preis)

        if len(tages_preise) < 1:
            messagebox.showinfo("Info",
                T("no_data_chart"))
            return
        if len(tages_preise) < 2:
            # Nur ein Datenpunkt — trotzdem anzeigen
            erster = list(tages_preise.items())[0]
            tages_preise[erster[0] + " (2)"] = erster[1]  # Duplicate point for line rendering

        # Sortiert nach Datum/Uhrzeit
        punkte    = sorted(tages_preise.items())
        daten     = [p[0][:16] for p in punkte]
        preise    = [p[1] for p in punkte]
        avg_preise = [round(sum(tages_summen.get(d, [p])) / len(tages_summen.get(d, [p])), 2)
                      for d, p in punkte]
        ziel    = g["zielpreis"]

        # Chart-Fenster
        dlg = tk.Toplevel(self)
        dlg.title(f"{T('price_history_title')} — {g['name']}")
        # Position on same monitor as main window, then maximize
        self.update_idletasks()
        mx = self.winfo_x()
        my = self.winfo_y()
        mw = self.winfo_width()
        mh = self.winfo_height()
        # First set size to fill the monitor area, then maximize
        dlg.geometry(f"{mw}x{mh}+{mx}+{my}")
        dlg.update_idletasks()
        dlg.state("zoomed")
        dlg.configure(bg=BG)
        dlg.resizable(True, True)

        # Zeitraum-Buttons
        zeitraum_bar = tk.Frame(dlg, bg=BG)
        zeitraum_bar.pack(fill="x", padx=16, pady=(12,0))
        zeitraum_var = tk.StringVar(value=T("all_btn"))

        def zeitraum_filtern():
            from datetime import datetime as _dt, timedelta
            zr = zeitraum_var.get()
            jetzt = _dt.now()
            if zr == T("day"):
                grenze = (jetzt - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
            elif zr == T("week"):
                grenze = (jetzt - timedelta(weeks=1)).strftime("%Y-%m-%d %H:%M")
            elif zr == T("month"):
                grenze = (jetzt - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
            else:
                grenze = ""
            if grenze:
                gefiltert = {d: p for d, p in tages_preise.items() if d >= grenze}
                gefiltert_avg = {d: tages_summen[d] for d in gefiltert if d in tages_summen}
            else:
                gefiltert = tages_preise
                gefiltert_avg = tages_summen
            if not gefiltert:
                return
            pkt = sorted(gefiltert.items())
            return pkt, gefiltert_avg

        tk.Label(zeitraum_bar, text=T("period"), bg=BG, fg=TEXT2,
                 font=(UI_FONT, 9)).pack(side="left", padx=(0,8))
        for zr in [T("day"), T("week"), T("month"), T("all_btn")]:
            tk.Radiobutton(zeitraum_bar, text=zr, variable=zeitraum_var, value=zr,
                           bg=BG, fg=TEXT, activebackground=BG, selectcolor=BG3,
                           font=(UI_FONT, 9),
                           command=lambda: canvas.event_generate("<Configure>")
                           ).pack(side="left", padx=4)

        # Canvas für Chart
        canvas = tk.Canvas(dlg, bg=BG2, highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=16, pady=(8,16))

        def zeichnen(event=None):
            canvas.delete("all")
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w < 50 or h < 50:
                return

            # Zeitraum-Filter anwenden
            from datetime import datetime as _dt, timedelta
            zr = zeitraum_var.get()
            jetzt = _dt.now()
            if zr == T("day"):
                grenze = (jetzt - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
            elif zr == T("week"):
                grenze = (jetzt - timedelta(weeks=1)).strftime("%Y-%m-%d %H:%M")
            elif zr == T("month"):
                grenze = (jetzt - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
            else:
                grenze = ""
            gefiltertes_dict = {d: p for d, p in tages_preise.items()
                                if not grenze or d >= grenze}
            if not gefiltertes_dict:
                canvas.create_text(w//2, h//2, text="No data for this period",
                                   fill=TEXT2, font=(UI_FONT, 11))
                return
            pkt_gefiltert = sorted(gefiltertes_dict.items())
            daten   = [p[0][:16] for p in pkt_gefiltert]
            preise  = [p[1] for p in pkt_gefiltert]
            avg_preise = [round(sum(tages_summen.get(d, [p])) /
                               len(tages_summen.get(d, [p])), 2)
                          for d, p in pkt_gefiltert]

            pad_l, pad_r, pad_t, pad_b = 70, 90, 75, 50
            chart_w = w - pad_l - pad_r
            chart_h = h - pad_t - pad_b

            alle_werte = preise + avg_preise + [ziel]
            min_p = min(alle_werte) * 0.97
            max_p = max(alle_werte) * 1.03

            def cx(i):
                return pad_l + (i / max(len(preise)-1, 1)) * chart_w

            def cy(p):
                return pad_t + (1 - (p - min_p) / (max_p - min_p)) * chart_h

            # Farblegende oben links
            legende = [
                (T("cur_best"), TEXT2, False),
                (T("avg_legend"),    "#60a5fa", True),
                (T("target_price_lbl"), AKZENT, True),
            ]
            lx = pad_l
            for i, (ltext, lfarbe, gestrichelt) in enumerate(legende):
                ly = 14 + i * 18
                dash = (5,3) if gestrichelt else None
                kw = {"fill": lfarbe, "width": 2}
                if dash: kw["dash"] = dash
                canvas.create_line(lx, ly, lx+30, ly, **kw)
                canvas.create_text(lx+34, ly, text=ltext, fill=lfarbe,
                                   font=(UI_FONT, 8), anchor="w")

            # Info-Zeile oben rechts
            info = (f"{T('data_points')}: {len(preise)}   "
                    f"Min: {min(preise):.2f}€   "
                    f"Ø {T('cur_avg')[:3]}: {avg_preise[-1]:.2f}€   "
                    f"{T('cur_best')[:4]}: {preise[-1]:.2f}€")
            canvas.create_text(w - pad_r + 80, 14, text=info,
                               fill=TEXT2, font=(UI_FONT, 8), anchor="e")

            # Gitternetz
            for step in range(5):
                py = pad_t + step * chart_h / 4
                preis_val = max_p - step * (max_p - min_p) / 4
                canvas.create_line(pad_l, py, pad_l + chart_w, py,
                                   fill="#2a2a2a", dash=(4,4))
                canvas.create_text(pad_l - 6, py, text=f"{preis_val:.0f}€",
                                   fill=TEXT2, font=(UI_FONT, 8), anchor="e")

            # Zielpreis-Linie
            yz = cy(ziel)
            canvas.create_line(pad_l, yz, pad_l + chart_w, yz,
                               fill=AKZENT, dash=(6,3), width=1.5)
            canvas.create_text(pad_l + chart_w + 6, yz,
                               text=f"Ziel {ziel:.0f}€",
                               fill=AKZENT, font=(UI_FONT, 8), anchor="w")

            # Durchschnittslinie
            avg_xy = [(cx(i), cy(avg_preise[i])) for i in range(len(avg_preise))]
            if len(avg_xy) >= 2:
                for i in range(len(avg_xy)-1):
                    canvas.create_line(avg_xy[i][0], avg_xy[i][1],
                                       avg_xy[i+1][0], avg_xy[i+1][1],
                                       fill="#60a5fa", width=2, dash=(5,3))

            # Günstigster-Preis-Linie
            punkte_xy = [(cx(i), cy(p)) for i, p in enumerate(preise)]
            if len(punkte_xy) >= 2:
                for i in range(len(punkte_xy)-1):
                    farbe = AKZENT if preise[i] <= ziel else TEXT2
                    canvas.create_line(punkte_xy[i][0], punkte_xy[i][1],
                                       punkte_xy[i+1][0], punkte_xy[i+1][1],
                                       fill=farbe, width=2.5)

            # Datenpunkte mit Labels
            for i, (px, py2) in enumerate(punkte_xy):
                farbe = AKZENT if preise[i] <= ziel else "#378ADD"
                canvas.create_oval(px-4, py2-4, px+4, py2+4, fill=farbe, outline="")
                if i == 0 or i == len(preise)-1 or preise[i] == min(preise):
                    anker = "sw" if i == len(preise)-1 else "se"
                    canvas.create_text(px, py2-8, text=f"{preise[i]:.0f}€",
                                       fill=TEXT, font=(UI_FONT, 8, "bold"), anchor=anker)

            # X-Achse — smart label deduplication
            zr = zeitraum_var.get()
            is_day = zr == T("day")
            max_labels = max(2, min(len(daten), chart_w // 65))
            schritt = max(1, len(daten) // max_labels)
            seen_labels = set()
            for i in range(0, len(daten), schritt):
                px = cx(i)
                raw = daten[i]  # "2024-03-15 10:49"
                if is_day:
                    label = raw[11:16]        # HH:MM
                elif zr == T("week"):
                    label = raw[5:10]         # MM-DD
                else:
                    label = raw[5:10]         # MM-DD (deduplicated)
                # Skip duplicate date labels
                if not is_day and label in seen_labels:
                    continue
                seen_labels.add(label)
                canvas.create_text(px, pad_t + chart_h + 14, text=label,
                                   fill=TEXT2, font=(UI_FONT, 8), anchor="n")
                canvas.create_line(px, pad_t + chart_h, px, pad_t + chart_h + 5, fill=BORDER)

            # Achsenlinien
            canvas.create_line(pad_l, pad_t, pad_l, pad_t + chart_h, fill=BORDER, width=1)
            canvas.create_line(pad_l, pad_t + chart_h, pad_l + chart_w,
                               pad_t + chart_h, fill=BORDER, width=1)

        canvas.bind("<Configure>", zeichnen)
        dlg.after(100, zeichnen)

        # Mouseover-Tooltip
        def _tooltip(event):
            canvas.delete("tooltip")
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w < 50 or h < 50:
                return
            # Aktuell gefilterte Daten ermitteln
            from datetime import datetime as _dt, timedelta
            zr = zeitraum_var.get()
            jetzt = _dt.now()
            if zr == T("day"):
                grenze = (jetzt - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
            elif zr == T("week"):
                grenze = (jetzt - timedelta(weeks=1)).strftime("%Y-%m-%d %H:%M")
            elif zr == T("month"):
                grenze = (jetzt - timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
            else:
                grenze = ""
            gefiltert = {d: p for d, p in tages_preise.items() if not grenze or d >= grenze}
            if not gefiltert:
                return
            pkt = sorted(gefiltert.items())
            p_preise = [p[1] for p in pkt]
            p_avg    = [round(sum(tages_summen.get(d, [p])) / len(tages_summen.get(d, [p])), 2)
                        for d, p in pkt]
            pad_l, pad_r, pad_t, pad_b = 70, 90, 75, 50
            chart_w = w - pad_l - pad_r
            n = len(p_preise)
            if n < 1:
                return
            # Nächsten Datenpunkt zum Mauszeiger finden
            mx = event.x
            if mx < pad_l or mx > pad_l + chart_w:
                return
            idx = round((mx - pad_l) / chart_w * (n - 1))
            idx = max(0, min(n - 1, idx))
            alle_werte = p_preise + p_avg + [ziel]
            min_p = min(alle_werte) * 0.97
            max_p = max(alle_werte) * 1.03
            def cx(i): return pad_l + (i / max(n - 1, 1)) * chart_w
            def cy(p): return pad_t + (1 - (p - min_p) / (max_p - min_p)) * (h - pad_t - pad_b)
            tx = cx(idx)
            ty = cy(p_preise[idx])
            datum = pkt[idx][0]
            best  = p_preise[idx]
            avg   = p_avg[idx]
            cur   = g.get("currency", "€")
            lines = [datum[:16], f"{T('chart_tooltip_best')}: {cur}{best:.2f}",
                     f"{T('chart_tooltip_avg')}: {cur}{avg:.2f}"]
            tw, th, pad = 150, 54, 6
            # Position: links vom Punkt wenn zu weit rechts
            bx = tx + 12 if tx + tw + 20 < w else tx - tw - 12
            by = max(pad_t, ty - th // 2)
            canvas.create_rectangle(bx, by, bx + tw, by + th,
                                    fill="#1e293b", outline="#4b5563", width=1, tags="tooltip")
            for i, line in enumerate(lines):
                canvas.create_text(bx + pad, by + pad + i * 16, text=line,
                                   fill=TEXT if i > 0 else TEXT2,
                                   font=(UI_FONT, 8, "bold" if i == 0 else ""),
                                   anchor="nw", tags="tooltip")
            # Kreis am Punkt hervorheben
            canvas.create_oval(tx - 5, ty - 5, tx + 5, ty + 5,
                                fill=AKZENT if best <= ziel else "#378ADD",
                                outline="white", width=1.5, tags="tooltip")

        canvas.bind("<Motion>", _tooltip)
        canvas.bind("<Leave>", lambda *_: canvas.delete("tooltip"))

    # ── Update ────────────────────────────────────────────────────────────────
    def _update_check_bg(self):
        new_ver, url, zip_url, notes = check_for_update()
        if new_ver:
            self.after(0, lambda: self._update_verfuegbar(new_ver, url, zip_url, notes))

    def _update_verfuegbar(self, new_ver, url, zip_url="", notes=""):
        self.update_lbl.config(
            text=f"🆕 Update available — v{new_ver}  (click to install)",
            fg=AKZENT)
        self._update_url     = url
        self._update_zip_url = zip_url
        self._update_version = new_ver
        self._update_notes   = notes

    def _update_pruefen(self):
        # If update already detected, use stored info
        new_ver  = getattr(self, "_update_version", None)
        zip_url  = getattr(self, "_update_zip_url", "")
        html_url = getattr(self, "_update_url", "")
        notes    = getattr(self, "_update_notes", "")

        if not new_ver:
            new_ver, html_url, zip_url, notes = check_for_update()

        if not new_ver:
            messagebox.showinfo("Up to date",
                f"You are running the latest version (v{APP_VERSION}).")
            return

        # Show release notes dialog
        dlg = tk.Toplevel(self)
        dlg.title(f"Update Available — v{new_ver}")
        self._center_dialog(dlg, 560, 480)
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        # Header
        hdr_f = tk.Frame(dlg, bg="#14532d")
        hdr_f.pack(fill="x")
        tk.Label(hdr_f, text=f"🆕  Version {new_ver} available!",
                 bg="#14532d", fg="#4ade80",
                 font=(UI_FONT, 13, "bold")).pack(anchor="w", padx=20, pady=(14,2))
        tk.Label(hdr_f, text=f"You are on v{APP_VERSION}",
                 bg="#14532d", fg="#86efac",
                 font=(UI_FONT, 9)).pack(anchor="w", padx=20, pady=(0,12))

        # Release notes
        tk.Label(dlg, text="What's new:", bg=BG, fg=TEXT2,
                 font=(UI_FONT, 10, "bold")).pack(anchor="w", padx=16, pady=(12,4))

        from tkinter import scrolledtext as _st
        notes_box = _st.ScrolledText(dlg, bg=BG2, fg=TEXT, font=(UI_FONT, 9),
                                      height=12, borderwidth=0, relief="flat",
                                      wrap="word", state="normal")
        notes_box.pack(fill="both", expand=True, padx=16, pady=(0,8))
        notes_box.insert("1.0", notes or "No release notes provided.")
        notes_box.config(state="disabled")

        # Buttons
        btn_f = tk.Frame(dlg, bg=BG)
        btn_f.pack(fill="x", padx=16, pady=(0,16))

        antwort = [False]

        def do_install():
            antwort[0] = True
            dlg.destroy()

        self._btn(btn_f, "✅  Install Update", do_install, AKZENT, "#000").pack(
            side="left", ipady=6, padx=(0,8))
        self._btn(btn_f, "Later", dlg.destroy, BG3, TEXT2).pack(
            side="left", ipady=6)

        dlg.wait_window()
        if not antwort[0]:
            return

        # Download and install in background
        self.update_lbl.config(text="⬇ Downloading update...", fg=GELB)
        threading.Thread(target=self._update_installieren,
                         args=(new_ver, zip_url, html_url), daemon=True).start()

    def _update_installieren(self, new_ver, asset_url, html_url):
        """Downloads and installs the update. EXE: runs Inno Setup installer. Script: replaces .py."""
        import tempfile, shutil
        try:
            log(f"Downloading update v{new_ver} from {asset_url[:60]}")
            self.after(0, lambda: self.update_lbl.config(text="⬇  0%", fg=GELB))

            tmp_suffix = ".exe" if asset_url.endswith(".exe") else ".zip"
            fd, tmp_str = tempfile.mkstemp(suffix=tmp_suffix)
            os.close(fd)
            tmp = Path(tmp_str)

            r = requests.get(asset_url, timeout=120, stream=True)
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded / total * 100)
                        self.after(0, lambda p=pct: self.update_lbl.config(
                            text=f"⬇  {p}%", fg=GELB))

            self.after(0, lambda: self.update_lbl.config(text="📦 Installing...", fg=GELB))

            if getattr(sys, "frozen", False):
                import subprocess as _sp
                if not str(tmp).endswith(".exe"):
                    # Kein EXE-Asset — manuell herunterladen
                    tmp.unlink(missing_ok=True)
                    self.after(0, lambda: (
                        self.update_lbl.config(text="🔗 Download update manually", fg=AKZENT),
                        messagebox.showinfo("Update Available",
                            f"v{new_ver} is available.\n\nPlease download manually from GitHub.\n{html_url}")
                    ))
                    return
                if "PreisAlarm_Setup" in asset_url:
                    # ── Inno Setup Installer ──────────────────────────────────
                    log(f"Launching installer {tmp}")
                    _sp.Popen(
                        [str(tmp), "/SILENT", "/FORCECLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
                        creationflags=_sp.DETACHED_PROCESS)
                else:
                    # ── Direct EXE self-replace via batch script ──────────────
                    current_exe = Path(sys.executable).resolve()
                    bat = (
                        "@echo off\r\n"
                        "timeout /t 2 /nobreak > nul\r\n"
                        f"copy /y \"{tmp}\" \"{current_exe}\"\r\n"
                        f"del \"{tmp}\"\r\n"
                        f"start \"\" \"{current_exe}\"\r\n"
                        "del \"%~f0\"\r\n"
                    )
                    import tempfile as _tf
                    fd_bat, bat_path = _tf.mkstemp(suffix=".bat")
                    os.close(fd_bat)
                    Path(bat_path).write_text(bat, encoding="cp1252")
                    log(f"Self-replace via batch: {bat_path}")
                    _sp.Popen(
                        ["cmd", "/c", bat_path],
                        creationflags=_sp.DETACHED_PROCESS | _sp.CREATE_NO_WINDOW,
                        close_fds=True)
                self.after(800, lambda: os._exit(0))
            else:
                # ── Running as Python script: replace .py and restart ──────────
                import zipfile
                script_path = Path(__file__).resolve()
                with zipfile.ZipFile(tmp, "r") as z:
                    for name in z.namelist():
                        if name.endswith("price_alert_tracker.py"):
                            fd2, tmp_py_str = tempfile.mkstemp(suffix=".py")
                            os.close(fd2)
                            tmp_py = Path(tmp_py_str)
                            with z.open(name) as src, open(tmp_py, "wb") as dst:
                                shutil.copyfileobj(src, dst)
                            shutil.move(str(tmp_py), str(script_path))
                            log(f"Updated script from {name}")
                            break
                tmp.unlink(missing_ok=True)
                self.after(0, lambda: self._update_neustart(new_ver))

        except Exception as e:
            log(f"Update failed: {e}")
            self.after(0, lambda err=str(e): (
                self.update_lbl.config(text="❌ Update failed — click to retry", fg=ROT),
                messagebox.showerror("Update Failed",
                    f"Could not install update automatically.\nError: {err}\n\n"
                    f"Please download manually from GitHub.")
            ))

    def _update_neustart(self, new_ver):
        """Shows restart dialog and restarts the app."""
        messagebox.showinfo("Update Installed",
            f"Version {new_ver} installed successfully!\n"
            f"The app will now restart.")
        import subprocess
        script = str(Path(__file__).resolve())
        # Use pythonw.exe if available (no CMD window)
        exe = sys.executable
        pythonw = exe.replace("python.exe", "pythonw.exe")
        if Path(pythonw).exists():
            exe = pythonw
        # Start new process then close this one
        subprocess.Popen([exe, script],
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        self.after(500, self.destroy)

    # ── Log ───────────────────────────────────────────────────────────────────
    def _log_refresh(self):
        try:
            inhalt = open(LOG_DATEI, "r", encoding="utf-8").read() if LOG_DATEI.exists() else ""
            self.log_box.config(state="normal")
            self.log_box.delete("1.0", "end")
            self.log_box.insert("end", inhalt)
            self.log_box.see("end")
            self.log_box.config(state="disabled")
        except:
            pass

    def _log_leeren(self):
        open(LOG_DATEI, "w").close()
        self._log_refresh()


if __name__ == "__main__":
    # pystray + Pillow installieren falls fehlt
    try:
        import pystray
        from PIL import Image
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "pystray", "pillow", "--quiet"])
    import traceback as _tb
    def _report_cb_exception(exc, val, tb):
        print("\n=== CALLBACK ERROR ===", flush=True)
        _tb.print_exception(exc, val, tb)
        print("======================\n", flush=True)
    import threading as _threading
    def _thread_excepthook(args):
        print("\n=== THREAD ERROR ===", flush=True)
        _tb.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
        print("====================\n", flush=True)
    _threading.excepthook = _thread_excepthook

    app = PreisAlarmApp()
    app.report_callback_exception = _report_cb_exception
    app.mainloop()
