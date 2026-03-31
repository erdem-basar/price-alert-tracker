# -*- coding: utf-8 -*-
"""
Preis-Alarm Tracker — Windows Service
Läuft im Hintergrund und prüft Preise automatisch,
auch wenn kein Benutzer eingeloggt ist.

Installation:
  PreisAlarmService.exe install
  PreisAlarmService.exe start

Deinstallation:
  PreisAlarmService.exe stop
  PreisAlarmService.exe remove
"""

import sys
import os
import re
import time
import json
import threading
import logging
from pathlib import Path
from datetime import datetime

import win32serviceutil
import win32service
import win32event
import servicemanager

import requests
from bs4 import BeautifulSoup

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False


# ── Pfade ────────────────────────────────────────────────────────────────────
def _finde_data_dir() -> Path:
    """
    Sucht C:\\Users\\*\\AppData\\Roaming\\PreisAlarm nach einer vorhandenen
    config.json. Nimmt den neuesten Treffer (zuletzt aktiver Benutzer).
    Fallback: C:\\ProgramData\\PreisAlarm.
    """
    users_root = Path("C:/Users")
    kandidaten = []
    if users_root.exists():
        for user_dir in users_root.iterdir():
            try:
                candidate = user_dir / "AppData" / "Roaming" / "PreisAlarm"
                cfg = candidate / "config.json"
                if cfg.exists():
                    kandidaten.append((cfg.stat().st_mtime, candidate))
            except Exception:
                pass
    if kandidaten:
        kandidaten.sort(reverse=True)
        return kandidaten[0][1]
    fallback = Path(os.environ.get("ALLUSERSPROFILE", "C:/ProgramData")) / "PreisAlarm"
    return fallback


DATA_DIR = _finde_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_DATEI  = DATA_DIR / "config.json"
VERGLEICH_DATEI = DATA_DIR / "vergleich.json"
LOG_DATEI     = DATA_DIR / "service.log"

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=str(LOG_DATEI),
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%d.%m.%Y %H:%M",
    encoding="utf-8",
)

def log(msg):
    logging.info(msg)


# ── Config & Daten ───────────────────────────────────────────────────────────
def lade_config():
    defaults = {
        "email_absender": "", "email_passwort": "", "email_empfaenger": "",
        "smtp_server": "mail.gmx.net", "smtp_port": 587, "intervall": 6,
    }
    cfg_datei = _finde_data_dir() / "config.json"
    if cfg_datei.exists():
        try:
            with open(cfg_datei, "r", encoding="utf-8") as f:
                return {**defaults, **json.load(f)}
        except Exception as e:
            log(f"Config Ladefehler: {e}")
    return defaults


def lade_vergleiche():
    vgl_datei = _finde_data_dir() / "vergleich.json"
    if vgl_datei.exists():
        try:
            with open(vgl_datei, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"Vergleiche Ladefehler: {e}")
    return []


def speichere_vergleiche(liste):
    vgl_datei = _finde_data_dir() / "vergleich.json"
    try:
        with open(vgl_datei, "w", encoding="utf-8") as f:
            json.dump(liste, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Vergleiche Speicherfehler: {e}")


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}

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


# ── Selenium (headless) ──────────────────────────────────────────────────────
def _selenium_get(url, wait=5):
    """Lädt eine URL mit headless Chrome. Funktioniert ohne angemeldeten Benutzer."""
    if not SELENIUM_OK:
        log("Selenium nicht verfügbar")
        return ""
    driver = None
    try:
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("--lang=de-DE")
        opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])

        service = ChromeService(ChromeDriverManager().install())
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
            except:
                pass

        time.sleep(wait)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
        time.sleep(1.5)

        # Geizhals: alle Angebote laden ("Mehr Angebote" klicken)
        ist_geizhals = any(d in url for d in ["geizhals.de", "geizhals.eu", "geizhals.at"])
        if ist_geizhals:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)
            for i in range(15):
                geklickt = driver.execute_script("""
                    var selectors = [
                        '.button--load-more-offers',
                        '[class*="load-more-offer"]',
                        '[class*="load-more"]',
                        '.listview__load-more'
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
                else:
                    break

        return driver.page_source
    except Exception as e:
        log(f"Selenium Fehler: {e}")
        return ""
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def shops_aus_url_laden(url):
    """
    Lädt alle Shops von einer Geizhals-Produktseite via headless Chrome.
    Gibt Liste von {shop_name, preis} zurück.
    """
    shops = []
    try:
        html = _selenium_get(url, wait=5)
        if not html:
            # Fallback ohne Selenium (funktioniert bei Geizhals meist nicht)
            r = requests.get(url, headers=HEADERS, timeout=20)
            html = r.text

        soup = BeautifulSoup(html, "html.parser")
        anbieter = set()

        # JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                for item in (data if isinstance(data, list) else [data]):
                    offers = item.get("offers", [])
                    if isinstance(offers, dict):
                        offers = [offers]
                    for offer in offers:
                        seller = offer.get("seller", {})
                        name = seller.get("name", "") if isinstance(seller, dict) else str(seller)
                        preis = _parse(str(offer.get("price", "")))
                        if name and preis and name not in anbieter:
                            anbieter.add(name)
                            shops.append({"shop_name": name, "preis": preis})
            except:
                pass

        log(f"JSON-LD: {len(shops)} Shops gefunden")

        # Geizhals HTML-Parsing (alte Struktur: class="offer")
        if not shops:
            for offer in soup.find_all(class_="offer"):
                try:
                    preis_el = offer.find(class_="gh_price")
                    if not preis_el:
                        continue
                    preis = _parse(preis_el.get_text(strip=True))
                    if not preis:
                        continue
                    shop_name = ""
                    skip = {"zum angebot", "agb", "infos", "bewertung", "store"}
                    for a in offer.find_all("a", href=True):
                        text = a.get_text(strip=True)
                        if "redir" in a["href"] and text and text.lower() not in skip and len(text) > 1:
                            shop_name = text
                            break
                    if shop_name and shop_name not in anbieter:
                        anbieter.add(shop_name)
                        shops.append({"shop_name": shop_name, "preis": preis})
                except:
                    continue
            log(f"Geizhals HTML (alt): {len(shops)} Shops gefunden")

        # Geizhals HTML-Parsing (neue Struktur: listview__item)
        if not shops:
            skip = {"zum angebot", "agb", "infos", "bewertung", "store"}
            for item in soup.find_all(
                lambda t: t.name and any("listview__item" in c for c in t.get("class", []))
            ):
                try:
                    preis_el = item.find(
                        lambda t: t.name and any("listview__price" in c for c in t.get("class", []))
                    )
                    if not preis_el:
                        continue
                    preis = _parse(preis_el.get_text(strip=True))
                    if not preis:
                        continue
                    shop_name = ""
                    merchant_el = item.find(
                        lambda t: t.name and any("merchant" in c.lower() for c in t.get("class", []))
                    )
                    if merchant_el:
                        shop_name = merchant_el.get_text(strip=True)
                    if not shop_name:
                        for a in item.find_all("a", href=True):
                            text = a.get_text(strip=True)
                            if "redir" in a["href"] and text and text.lower() not in skip and len(text) > 1:
                                shop_name = text
                                break
                    if shop_name and shop_name not in anbieter:
                        anbieter.add(shop_name)
                        shops.append({"shop_name": shop_name, "preis": preis})
                except:
                    continue
            log(f"Geizhals HTML (neu): {len(shops)} Shops gefunden")

        log(f"Total: {len(shops)} Shops von {url[:60]}")
        return shops
    except Exception as e:
        log(f"Ladefehler {url[:60]}: {e}")
        return []


# ── E-Mail ───────────────────────────────────────────────────────────────────
def email_senden(cfg, alarme, aenderungen):
    if not alarme and not aenderungen:
        return
    if not cfg.get("email_absender"):
        return
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.utils import formataddr

        alarm_html = ""
        if alarme:
            zeilen = "".join(
                f"<tr><td style='padding:8px;color:#f1f5f9;font-weight:bold'>{a['name']}</td>"
                f"<td style='padding:8px;color:#22c55e;font-weight:bold'>€{a['preis']:.2f}</td>"
                f"<td style='padding:8px;color:#f1f5f9'>{a['shop_name']}</td></tr>"
                for a in alarme
            )
            alarm_html = f"""
            <div style="background:#14532d;border-radius:8px;padding:16px;margin-bottom:20px">
              <h2 style="color:#4ade80;margin:0 0 12px">🔔 Zielpreis erreicht!</h2>
              <table style="width:100%;border-collapse:collapse">
                <tr style="background:#166534">
                  <th style="padding:8px;text-align:left;color:#86efac">Produkt</th>
                  <th style="padding:8px;text-align:left;color:#86efac">Preis</th>
                  <th style="padding:8px;text-align:left;color:#86efac">Shop</th>
                </tr>
                {zeilen}
              </table>
            </div>"""

        aend_html = ""
        if aenderungen:
            zeilen = "".join(
                f"<tr><td style='padding:8px;color:#f1f5f9'>{a['name']}</td>"
                f"<td style='padding:8px;color:#94a3b8'>{a['alt']:.2f}€</td>"
                f"<td style='padding:8px;font-weight:bold;color:{'#22c55e' if a['neu']<a['alt'] else '#f87171'}'>"
                f"{a['neu']:.2f}€ {'⬇' if a['neu']<a['alt'] else '⬆'}</td>"
                f"<td style='padding:8px;color:#f1f5f9'>{a['shop_name']}</td></tr>"
                for a in aenderungen
            )
            aend_html = f"""
            <div style="margin-bottom:20px">
              <h2 style="color:#f1f5f9;margin:0 0 12px">📊 Preisänderungen</h2>
              <table style="width:100%;border-collapse:collapse">
                <tr style="background:#1e293b">
                  <th style="padding:8px;text-align:left;color:#94a3b8">Produkt</th>
                  <th style="padding:8px;text-align:left;color:#94a3b8">Alter Preis</th>
                  <th style="padding:8px;text-align:left;color:#94a3b8">Neuer Preis</th>
                  <th style="padding:8px;text-align:left;color:#94a3b8">Shop</th>
                </tr>
                {zeilen}
              </table>
            </div>"""

        betreff = f"🔔 {len(alarme)} Alarm(e)" if alarme else f"📊 {len(aenderungen)} Preisänderung(en)"
        html = f"""<html><body style="font-family:Arial;max-width:700px;margin:auto;
                   background:#0f0f0f;color:#f1f5f9;padding:24px">
          <h1 style="color:#f1f5f9;margin:0 0 4px;font-size:20px">🔔 Preis-Alarm Tracker</h1>
          <p style="color:#6b7280;font-size:12px;margin:0 0 20px">
            {datetime.now().strftime('%d.%m.%Y %H:%M')} · Service-Modus
          </p>
          {alarm_html}{aend_html}
          <p style="color:#4b5563;font-size:11px;margin-top:24px;border-top:1px solid #1f2937;padding-top:12px">
            Preis-Alarm Tracker · Automatischer Preischeck
          </p>
        </body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = betreff
        msg["From"]    = formataddr(("Price Alert", cfg["email_absender"]))
        msg["To"]      = cfg["email_empfaenger"]
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(cfg["smtp_server"], int(cfg["smtp_port"])) as s:
            s.starttls()
            s.login(cfg["email_absender"], cfg["email_passwort"])
            s.sendmail(cfg["email_absender"], cfg["email_empfaenger"], msg.as_string())
        log(f"E-Mail gesendet: {betreff}")
    except Exception as e:
        log(f"E-Mail Fehler: {e}")


# ── Preis-Check Loop ─────────────────────────────────────────────────────────
def preis_check_ausfuehren():
    """Prüft alle Produkte via Geizhals (headless Selenium) und sendet E-Mails."""
    data_dir = _finde_data_dir()
    log(f"Preis-Check gestartet... (Daten: {data_dir})")
    cfg        = lade_config()
    vergleiche = lade_vergleiche()

    if not vergleiche:
        log("Keine Produkte zu prüfen.")
        return

    alarme      = []
    aenderungen = []
    jetzt       = datetime.now().strftime("%d.%m. %H:%M")

    for g in vergleiche:
        source_url = g.get("source_url", "")
        ziel       = g.get("zielpreis", 0)
        name       = g.get("name", "")

        if not source_url:
            log(f"  {name}: keine source_url, übersprungen")
            continue

        log(f"  Lade: {name} — {source_url[:60]}")
        neue_shops = shops_aus_url_laden(source_url)

        if not neue_shops:
            log(f"  {name}: keine Shops geladen")
            continue

        # Preis-Map: Shop-Name (lowercase) → Preis
        preis_map = {s["shop_name"].lower().strip(): s["preis"] for s in neue_shops}

        for s in g.get("shops", []):
            shop_name = (s.get("shop_name") or s.get("shop", "")).lower().strip()

            # Shop-Preis per exaktem Match, Teilstring oder Prefix suchen
            preis = preis_map.get(shop_name)
            if not preis:
                for key, val in preis_map.items():
                    if key in shop_name or shop_name in key:
                        preis = val
                        break
            if not preis and len(shop_name) >= 4:
                prefix = shop_name[:5]
                for key, val in preis_map.items():
                    if key.startswith(prefix) or key[:5] == prefix:
                        preis = val
                        break

            if preis is None:
                continue

            s["zuletzt"] = jetzt
            alter_preis = s.get("preis", 0)

            if alter_preis and abs(preis - alter_preis) > 0.01:
                aenderungen.append({
                    "name":      name,
                    "alt":       alter_preis,
                    "neu":       preis,
                    "shop_name": s.get("shop_name") or s.get("shop", ""),
                })
                s["preis_vorher"] = alter_preis
                s["preis_trend"]  = "gesunken" if preis < alter_preis else "gestiegen"
            else:
                s.pop("preis_vorher", None)
                s.pop("preis_trend",  None)

            s["preis"] = preis
            verlauf = s.get("verlauf", [])
            verlauf.append({"datum": datetime.now().strftime("%Y-%m-%d %H:%M"), "preis": preis})
            s["verlauf"] = verlauf[-1000:]

            if ziel and preis <= ziel and not g.get("alarm_gesendet"):
                alarme.append({
                    "name":      name,
                    "preis":     preis,
                    "shop_name": s.get("shop_name") or s.get("shop", ""),
                })
                g["alarm_gesendet"] = True

        log(f"  {name}: {len(preis_map)} Shops geladen")

    speichere_vergleiche(vergleiche)
    log(f"Check fertig: {len(aenderungen)} Änderungen, {len(alarme)} Alarme")
    email_senden(cfg, alarme, aenderungen)


# ── Windows Service ──────────────────────────────────────────────────────────
class PreisAlarmService(win32serviceutil.ServiceFramework):
    _svc_name_         = "PreisAlarmService"
    _svc_display_name_ = "Preis-Alarm Tracker Service"
    _svc_description_  = "Automatische Preisüberwachung — prüft Preise und sendet E-Mail-Alerts."

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self._stop     = threading.Event()

    def SvcStop(self):
        log("Service wird gestoppt...")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self._stop.set()

    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, "")
        )
        log("Preis-Alarm Service gestartet.")
        self._run()

    def _run(self):
        while not self._stop.is_set():
            try:
                preis_check_ausfuehren()
            except Exception as e:
                log(f"Check-Fehler: {e}")

            cfg = lade_config()
            intervall = cfg.get("intervall", 6) * 3600
            log(f"Nächster Check in {cfg.get('intervall', 6)} Stunden.")
            self._stop.wait(timeout=intervall)


# ── Einstiegspunkt ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PreisAlarmService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PreisAlarmService)
