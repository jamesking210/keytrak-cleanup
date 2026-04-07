# KeyTrak Cleanup

A simple self-hosted web app for comparing **Zeus inventory** against **KeyTrak current inventory**, with an optional **Items Out by User** enrichment report.

Since **Zeus is the truth source**, the core output is:

**KeyTrak current inventory - Zeus**

That leftover list is your cleanup list of likely sold or stale units still sitting in KeyTrak.

## What it does

- Drag-and-drop upload page for 3 CSV files
- Required inputs:
  - **Zeus inventory CSV**
  - **KeyTrak current inventory CSV**
- Optional input:
  - **KeyTrak Items Out by User CSV**
- Shows live processing status on the webpage
- Shows errors on the webpage if something fails
- Shows a preview of the first 25 leftover result rows
- Emails a copy of the result CSV
- Deletes uploaded source files after successful processing
- Cleans up temporary task files after completion
- Writes persistent logs for processing, cleanup, and email activity

## Truth logic

This project does **not** do a two-way difference report.

It does this only:

**KeyTrak current inventory minus Zeus**

That means:

- **In both Zeus and KeyTrak current inventory** = ignore
- **In Zeus but not KeyTrak current inventory** = ignored for this report
- **In KeyTrak current inventory but not Zeus** = output list

That output list represents vehicles that are likely sold, stale, or otherwise should no longer be sitting in KeyTrak.

## Optional Items Out by User merge

If you upload the **Items Out by User** file, the app will match on **Stock #** and attach:

- `User ID`
- `Reason`
- `Time Out`

If the same stock number appears more than once in Items Out by User, the app keeps the **most recent Time Out** row.

## Final output columns

The emailed CSV uses this order:

- `Stock #`
- `Stock Type`
- `Year`
- `Make`
- `Model`
- `Exterior Color`
- `User ID`
- `Reason`
- `Time Out`

No extra columns are included in the emailed CSV.

## Expected CSV formats

### Zeus inventory
Example file: `Inv_Mgrs.csv`

- Uses the standard header row
- **Stock number is column 2**

### KeyTrak current inventory
Example file: `Lombard Toyota_Current Inventory_04-02-2026_15-33_PM.csv`

- Has a title row and blank row before the real header
- The app automatically skips the first 2 rows
- **Stock number is column 1**

### Items Out by User
Example file: `Lombard Toyota_Items Out by User_04-06-2026_16-19_PM.csv`

- Has a title row and blank row before the real header
- The app automatically skips the first 2 rows
- Uses:
  - `Stock #`
  - `User ID`
  - `Reason`
  - `Time Out`

## Email-only workflow

This app does not offer CSV download from the website.

The website is used for:

- uploading the CSV files
- watching processing status
- seeing preview rows
- seeing errors
- confirming which email address received the CSV

The final cleanup CSV is delivered by email only.

Because of that:

- **SMTP must be configured**
- a recipient email address must be provided or stored in `.env`

## Default port

This app runs on:

**8088**

Open it in your browser at:

```text
http://YOUR-HOST-IP:8088
```

## File layout

```text
keytrak-cleanup/
├── app.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── .dockerignore
├── README.md
├── templates/
│   └── index.html
├── tmp/
└── logs/
    └── app.log
```

## Environment file

Create your local `.env` file from the example:

```bash
cp .env.example .env
nano .env
```

Example values:

```env
SMTP_ENABLED=true
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_username
SMTP_PASSWORD=your_password
SMTP_FROM=you@example.com
SMTP_TO=you@example.com
SMTP_USE_TLS=true
SMTP_USE_SSL=false

APP_TITLE=KeyTrak Cleanup
APP_SUBTITLE=Upload Zeus, KeyTrak current inventory, and optional Items Out by User CSVs. Compare them, preview the cleanup list, and email yourself a copy.
APP_PORT=8088
RESULT_RETENTION_MINUTES=30
MAX_CONTENT_LENGTH_MB=20
LOG_LEVEL=INFO
```

## Docker deploy

### 1. Clone the repo

```bash
cd /opt
git clone https://github.com/jamesking210/keytrak-cleanup.git
cd keytrak-cleanup
```

### 2. Create your env file

```bash
cp .env.example .env
nano .env
```

### 3. Start the app

```bash
docker compose up -d --build
```

### 4. Check status

```bash
docker compose ps
docker compose logs -f
```

### 5. Open the app

```text
http://YOUR-HOST-IP:8088
```

## Updating the app

When you make changes in GitHub:

```bash
cd /opt/keytrak-cleanup
git pull
docker compose down
docker compose up -d --build
```

## Logs

### Docker logs

```bash
docker compose logs -f
```

### Application log file

```bash
tail -f logs/app.log
```

The log file includes activity such as:

- homepage loads
- uploads accepted/rejected
- Zeus file parsing
- KeyTrak file parsing
- Items Out by User parsing
- compare results
- CSV generation
- email send attempts
- email success/failure
- cleanup
- stack traces for failures

## How cleanup works

After a successful run:

- uploaded source CSV files are deleted
- result files stay only temporarily on disk
- the result CSV is emailed to you
- completed task files are cleaned up after the retention window

The retention window is controlled by:

```env
RESULT_RETENTION_MINUTES=30
```

## Security notes

This repo is safe to keep public **only if you do not commit sensitive data**.

Do **not** commit:

- `.env`
- real SMTP credentials
- real dealership CSV exports
- generated result CSVs
- logs with sensitive info
- internal-only secrets

The repo already ignores the important local files through `.gitignore`.

## Recommended host sizing

For a small Docker LXC or VM, a good starting point is:

- 2 vCPU
- 2 GB RAM
- 12 GB disk

That is enough for normal use of this app.
