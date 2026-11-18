# Insider Scanner — Persistent Data Branch
This orphan branch serves as the persistent storage layer for the Insider Activity Scanner.

## Contents
- \output/scanner.db\: SQLite database containing historical flags, outcomes, and audit logs.
- \output/scanner.sql\: Text dump of the SQLite database for diffable version history.
- \output/suspicious_master.csv\: Legacy export of unexplained mover flags.
- \output/news_driven_master.csv\: Legacy export of news-driven flags.
- \output/unexplained_master.csv\: Unified master export.
