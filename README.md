# KeyTrak Cleanup

A simple self-hosted web app for comparing **Zeus inventory** against **KeyTrak inventory**.

The goal is to identify units that are still in **KeyTrak** but are **no longer in Zeus**.

Since **Zeus is the truth source**, the output is:

**KeyTrak - Zeus**

That leftover list is your cleanup list of likely **sold** or **stale** units still sitting in KeyTrak.

---

## What it does

- Clean upload page for two CSV files
- Compares:
  - **Zeus CSV** = truth source
  - **KeyTrak CSV** = inventory to clean up
- Removes all in-stock Zeus stock numbers from the KeyTrak list
- Shows processing status on the webpage
- Shows errors on the webpage if something fails
- Shows a preview of the first 25 leftover result rows
- Emails a copy of the result CSV
- Deletes uploaded source files after successful processing
- Cleans up temporary task files after completion
- Writes persistent logs for processing, cleanup, and email activity

---

## Truth logic

This project does **not** do a two-way difference report.

It does this only:

**KeyTrak minus Zeus**

That means:

- **In both Zeus and KeyTrak** = ignore
- **In Zeus but not KeyTrak** = ignored for this report
- **In KeyTrak but not Zeus** = output list

That output list represents vehicles that are likely:

- sold
- stale
- or otherwise should no longer be sitting in KeyTrak

---

## Expected CSV formats

### Zeus inventory
Example file: `Inv_Mgrs.csv`

- Uses the standard header row
- **Stock number is column 2**

### KeyTrak inventory
Example file: `Lombard Toyota_Current Inventory_04-02-2026_15-33_PM.csv`

- Has a title row and blank row before the real header
- The app automatically skips the first 2 rows
- **Stock number is column 1**

---

## Email-only workflow

This app no longer offers CSV download from the website.

The website is used for:

- uploading the two CSV files
- watching processing status
- seeing preview rows
- seeing errors
- confirming which email address received the CSV

The final cleanup CSV is delivered by email only.

Because of that:

- **SMTP must be configured**
- a recipient email address must be provided or stored in `.env`

---

## Features

- Portable Docker deployment
- Works well on:
  - Proxmox
  - TrueNAS
  - Debian/Ubuntu Docker host
- Persistent application log file
- No sensitive data stored in the public repo
- `.env` stays local on your host
- Temporary uploads/results stored in local mounted folders

---

## Default port

This app runs on:

**8088**

Open it in your browser at:

```text
http://YOUR-HOST-IP:8088
