# 🔔 Price Alert Tracker

Automatic price comparison for Windows — monitors shops via Geizhals, PriceSpy and Amazon, and sends notifications when your target price is reached.

![Version](https://img.shields.io/badge/version-1.6.2-green)
![Platform](https://img.shields.io/badge/platform-Windows-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-yellow)
![License](https://img.shields.io/badge/license-MIT-orange)

## ✨ Features

**Price Tracking**
- 🔍 Search by product name or paste a Geizhals / PriceSpy / Amazon URL
- 📊 Compare prices across all available shops at once
- 🎯 Set a target price — get notified when a shop drops below it
- 🔄 Automatic price checks every X hours (configurable)
- 🖱 Drag & drop to reorder product groups

**Analysis**
- 📈 Price history chart — Day / Week / Month / All time
- 📊 Statistics — all-time low, high, average, cheapest shop
- 🤖 AI Price Analysis — smart buy recommendation based on trend, volatility and distance to target

**Notifications**
- 🔔 Windows desktop notifications when target price is reached
- 📧 Email alerts with full price change summary
- 🧪 Test notification button in Settings

**Customization**
- 🎨 6 Color themes — Dark Mint, Dark Blue, Dark Purple, Dark Orange, Light, Light Blue
- 🔤 8 Font options — Segoe UI, Bahnschrift, Calibri, Verdana and more
- 🌍 13 Languages — switch instantly without restart
- 📐 Window position remembered between sessions

**System**
- 🖥 Runs in system tray — silent background monitoring
- ⚡ Optional autostart with Windows
- 🆕 Auto-update — notified when new version is available, installs with one click

## 🚀 Installation

1. Clone the repository:
```
git clone https://github.com/erdem-basar/price-alert-tracker.git
```
2. Run `setup.bat` as Administrator — installs all dependencies
3. Run `start.bat` to launch the app
4. Go to **Settings** → configure your email and check interval

## 🌍 Supported Price Sources

| Source | Region |
|---|---|
| Geizhals.de | Germany |
| Geizhals.eu | Europe (DE/AT/CH/EU/UK/PL) |
| Geizhals.at | Austria |
| PriceSpy UK | United Kingdom |
| Amazon.de | Germany (fallback) |

## 📧 Supported Email Providers

GMX · Web.de · Freenet · T-Online · 1&1 / IONOS · Outlook / Live · Gmail · Yahoo · iCloud · Posteo · Mailbox.org

Click any preset in Settings to auto-fill SMTP server and port.

## 🗣 Languages

🇬🇧 English · 🇩🇪 Deutsch · 🇫🇷 Français · 🇪🇸 Español · 🇮🇹 Italiano · 🇳🇱 Nederlands · 🇵🇱 Polski · 🇵🇹 Português · 🇹🇷 Türkçe · 🇷🇺 Русский · 🇨🇳 中文 · 🇯🇵 日本語 · 🇸🇦 العربية

## 🤝 Contributing

Translations live in the `locales/` folder as simple JSON files. Copy `en.json`, translate the values and submit a pull request!

## 📋 Changelog

See [Releases](https://github.com/erdem-basar/price-alert-tracker/releases) for full changelog.

## 📄 License

MIT License — free to use, modify and distribute.
