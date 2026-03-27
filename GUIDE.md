# 🔔 Preis-Alarm Tracker

Überwacht Produktpreise auf Amazon, MediaMarkt, OTTO, eBay & Co.
Sendet E-Mail + Windows-Popup wenn der Zielpreis erreicht wird.

---

## 📦 Installation (einmalig)

1. **Alle Dateien** in einen Ordner entpacken (z. B. `C:\PreisAlarm\`)
2. **`setup_und_build.bat`** mit Rechtsklick → "Als Administrator ausführen"
   - Installiert Python automatisch (falls nicht vorhanden)
   - Installiert alle Bibliotheken
   - Erstellt `PreisAlarm.exe` im Ordner `dist\`
   - Erstellt Desktop-Verknüpfung

> ⚠ Beim ersten Start kann Windows Defender warnen ("Unbekannte App").
> Klicke auf **"Weitere Informationen" → "Trotzdem ausführen"**.

---

## 🚀 App starten

- **Option A:** Doppelklick auf `dist\PreisAlarm.exe`
- **Option B:** Doppelklick auf `starten.bat` (startet mit Python direkt)
- **Option C:** Desktop-Verknüpfung (nach Setup automatisch erstellt)

---

## ⚙ Erste Schritte

### 1. E-Mail einrichten (Tab "Einstellungen")

Für Gmail:
1. Google-Konto → Sicherheit → 2-Schritt-Verifizierung aktivieren
2. Sicherheit → App-Passwörter → "Mail" auswählen → 16-stelligen Code kopieren
3. Im Tracker eintragen:
   - Absender: `deine@gmail.com`
   - App-Passwort: 16-stelliger Code (ohne Leerzeichen)
   - Empfänger: deine@email.de (kann gleiche Adresse sein)
   - SMTP: `smtp.gmail.com`, Port: `587`

Für andere Anbieter:
| Anbieter | SMTP Server | Port |
|----------|-------------|------|
| Gmail    | smtp.gmail.com | 587 |
| Outlook  | smtp.office365.com | 587 |
| GMX      | mail.gmx.net | 587 |
| Web.de   | smtp.web.de | 587 |

### 2. Produkt hinzufügen (Tab "Hinzufügen")

1. Produktnamen eingeben (z. B. "Sony Kopfhörer XM5")
2. Produkt-URL von der Shop-Seite kopieren und einfügen
3. Shop auswählen
4. Aktuellen Preis eintragen
5. Zielpreis eintragen (bei diesem Preis kommt der Alarm)
6. "Produkt hinzufügen" klicken

### 3. Tracker starten (Tab "Produkte")

- "▶ Tracker starten" klicken
- Prüft automatisch alle X Stunden (einstellbar)
- App kann minimiert im Hintergrund laufen

---

## 📁 Datenspeicherung

Alle Daten werden gespeichert in:
`C:\Users\[Dein Name]\AppData\Roaming\PreisAlarm\`

- `produkte.json` — Produktliste & Preisverlauf
- `config.json` — E-Mail-Einstellungen
- `log.txt` — Aktivitätsprotokoll

---

## ❓ Häufige Fragen

**Q: Der Preis wird nicht gefunden (⚠ Fehler)?**
A: Manche Shops blockieren automatische Abrufe. Versuche die direkte Produkt-URL (nicht Suchergebnis). Bei Amazon: URL auf `/dp/XXXXXXXXXX` kürzen.

**Q: Keine E-Mail erhalten?**
A: Spam-Ordner prüfen. Bei Gmail: App-Passwort (nicht normales Passwort) verwenden.

**Q: App startet nicht?**
A: `starten.bat` verwenden → Fehlermeldung notieren → `setup_und_build.bat` erneut ausführen.
