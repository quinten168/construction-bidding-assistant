#!/usr/bin/env bash
# Open the Plan Reader SQLite database (csi_v2.db) in DB Browser for SQLite.
# Usage: bash 04_tools/open_db.sh    (or chmod +x once, then ./04_tools/open_db.sh)

# Absolute path to the database so this works from any directory.
DB_PATH="/Users/t/Library/Mobile Documents/com~apple~CloudDocs/00 MSBA + Coding/00_summer 2026/00_CSI_ELP/01_Summer_2026/02_modules/plan_reader/csi_v2.db"

# Hand the file to the GUI viewer.
open -a "DB Browser for SQLite" "$DB_PATH"
