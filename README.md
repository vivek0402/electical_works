# SVKML Electrical Works: Spares & Complaints

Web app replacing the store's Excel sheets: multi-location fresh/defective spares, Wipro defective returns, and service complaints.

## Quick start (development)
Requires Docker Desktop and GNU make (Windows: `winget install ezwinports.make`, then run make from Git Bash).

```bash
cp .env.example .env        # set SECRET_KEY and SEED_PASSWORD
make up                     # db + web on http://localhost:8000
make migrate
make seed                   # users: admin, office, ramu, apparao (password = SEED_PASSWORD)
make test
```

See `CLAUDE.md` for all commands, layout and conventions.
