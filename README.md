# KeyTrak Cleanup

A lightweight Docker-friendly web app that compares **KeyTrak inventory against Zeus inventory**.

This tool is built for a simple monthly workflow:
- upload the current **Zeus** CSV
- upload the current **KeyTrak** CSV
- treat **Zeus as the truth source**
- remove Zeus in-stock units from the KeyTrak list
- download the leftover KeyTrak rows as a cleanup CSV
- email yourself a copy automatically
- clean up uploaded files after the run

---

## Business logic

This app is intentionally **one-way**:

**KeyTrak - Zeus**

Meaning:
- stock numbers found in both files are ignored
- stock numbers found only in Zeus are ignored for this report
- stock numbers found only in KeyTrak are returned as the cleanup list

Those leftover KeyTrak rows are treated as **likely sold or stale units still sitting in KeyTrak**.

---

## Expected file formats

### Zeus CSV
- Example filename: `Inv_Mgrs.csv`
- Stock number is read from **column 2**

### KeyTrak CSV
- Example filename: `Lombard Toyota_Current Inventory_04-02-2026_15-33_PM.csv`
- Stock number is read from **column 1**
- The first **2 lines are skipped automatically** because the export starts with a title row and a blank row

---

## Features

- Clean single-page upload interface
- Status updates shown live on the webpage
- Error messages shown on the webpage
- Downloadable result CSV
- Result email with CSV attachment
- Uploaded source files deleted after processing
- Old temp/result files cleaned up automatically
- Docker-ready and easy to move between hosts

---

## Repo safety

This repo is safe to keep public **as long as you do not upload real data or secrets**.

Do **not** commit:
- `.env`
- real SMTP credentials
- dealership CSV exports
- generated result CSVs
- logs or temp files

This repo already includes a `.gitignore` to help prevent that.

---

## Quick start

### 1. Clone the repo

```bash
git clone https://github.com/jamesking210/keytrak-cleanup.git
cd keytrak-cleanup
```

### 2. Create your env file

```bash
cp .env.example .env
nano .env
```

Fill in your real SMTP settings in `.env`.

### 3. Build and start the app

```bash
docker compose up -d --build
```

### 4. Open it in your browser

```text
http://YOUR-HOST-IP:8000
```

---

## Environment variables

See `.env.example` for the full list.

### App settings

```env
APP_TITLE=KeyTrak Cleanup
APP_SUBTITLE=Upload Zeus and KeyTrak inventory files, compare them, download the cleanup list, and email yourself a copy.
RESULT_RETENTION_MINUTES=30
MAX_CONTENT_LENGTH_MB=20
```

### SMTP settings

```env
SMTP_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_username
SMTP_PASSWORD=your_password
SMTP_USE_TLS=true
SMTP_USE_SSL=false
SMTP_FROM=you@example.com
SMTP_TO=you@example.com
```

If you use SSL on port 465 instead:

```env
SMTP_PORT=465
SMTP_USE_TLS=false
SMTP_USE_SSL=true
```

---

## Running commands

### Start

```bash
docker compose up -d --build
```

### Stop

```bash
docker compose down
```

### View logs

```bash
docker compose logs -f
```

### Rebuild after updates

```bash
git pull
docker compose up -d --build
```

---

## Hosting ideas

### Proxmox
- great in a small Debian LXC or VM
- simple internal tool for dealership use

### TrueNAS
- works as a custom app or Docker/Compose deployment
- keep `.env` and `tmp` on persistent storage

### Why it is portable
- no database required for the MVP
- no external dependencies beyond SMTP
- local temp files only
- same codebase should run anywhere Docker runs

---

## File layout

```text
keytrak-cleanup/
├── .dockerignore
├── .env.example
├── .gitignore
├── app.py
├── docker-compose.yml
├── Dockerfile
├── README.md
├── requirements.txt
└── templates/
    └── index.html
```

---

## Future ideas

- basic login/auth
- save run history with SQLite
- multiple email recipients
- scheduled monthly processing
- upload validation improvements
- KeyTrak API integration
- direct pull from a network share
- optional second report for `Zeus - KeyTrak`

---

## Notes

This project is intentionally simple for the first version.

The goal is to make the monthly KeyTrak cleanup easy, repeatable, and portable without overbuilding it.
