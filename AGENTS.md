# Agent instructions — Razz CNPL Accounts

## After every change

1. Update documentation in **both languages**, as **separate files**:
   - English: `README.md`, `USER-GUIDE.md`
   - বাংলা: `README.bn.md`, `USER-GUIDE.bn.md`
   Do not mix English and Bengali in the same file. Keep the four files in sync (same topics, language-specific wording).
2. **QA validate** the change (`python -m pytest tests -q`, and exercise affected screens in the browser when UI changed).
3. **Commit and push** to `https://github.com/apchowdhury25/razz-cpl.git` on `main`.
   - Git user: `apchowdhury25`
   - Prefer existing `gh` auth. HTTPS password is the stored public-repo PAT (do not commit the token).

## Product rules (do not regress)

- Money display: Bangladeshi grouping, `৳ 1,00,000.00` (not `100,000.00`).
- Date display and input: `DD/MM/YYYY` (`09/03/2026` = 9 March 2026). Store real dates in SQLite.
- Do not wipe `data/razz_accounts.db` on startup.
- Posted accounting documents are reversed, not silently edited.
