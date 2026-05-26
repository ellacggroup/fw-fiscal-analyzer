# Fort Worth Fiscal Impact Analyzer

A self-contained, no-account-required tool for analyzing Fort Worth City Council
agenda items for fiscal impact. Runs entirely on your own computer.

## Quick Start

### Prerequisites
Install these two free tools — no account or API key needed.

- [Python 3.11+](https://www.python.org/downloads/) — check **"Add Python to PATH"** during install
- [Node.js 20 LTS](https://nodejs.org/)

### First-time setup
Double-click **`setup.bat`** — it installs all dependencies automatically.

### Running the app
Double-click **`start.bat`** — your browser opens to `http://localhost:5173`.

---

## How It Works

1. **Upload** a Fort Worth City Council agenda PDF
2. The tool **extracts** each agenda item using pattern matching
3. **Rule-based fiscal analysis** runs instantly on each item — no internet required
4. **Color-coded results** show Positive / Neutral / Negative items at a glance
5. **History** is saved locally — past agendas appear in the sidebar

### Analysis Methodology

Based on three documented frameworks:

| Framework | Source | What it contributes |
|-----------|--------|---------------------|
| Fort Worth Annexation FIA | Comp Plan Appendix F | Property tax rate, departmental cost structure |
| Fate TX (Forward Fate 2021) | Per-zoning-case spreadsheet | 40-year R/C ratio, break-even year, road liabilities |
| Charlotte NC 2040 Plan (EPS) | Scenario-based FIA | Land-use prototype revenue/cost per acre by use type |

### Key Fiscal Parameters (Fort Worth)

| Parameter | Value |
|-----------|-------|
| Property tax rate | $0.7125 per $100 assessed value |
| City sales tax share | 1% |
| Police cost per capita | $350/yr |
| Fire/EMS cost per capita | $180/yr |
| Projection horizon | 40 years (Fate TX methodology) |
| R/C ratio target | ≥ 1.0 (fiscally self-sustaining) |
| Annual growth escalator | 2.5% |
| Discount rate (NPV) | 3% |

### Land-Use R/C Ratios Used

| Land Use | R/C Ratio | Fiscal Character |
|----------|-----------|-----------------|
| Commercial Retail | 2.70 | Strongly positive |
| Industrial / Warehouse | 2.32 | Positive |
| Office / Business Park | 2.26 | Positive |
| Mixed-Use | 1.74 | Positive |
| Multifamily Residential | 0.97 | Roughly neutral |
| Single-Family Residential | 0.72 | Net cost to city |
| Public / Institutional | 0.07 | Significant net cost |

*Source: Fate TX Forward Fate Comp Plan; Charlotte NC 2040 EPS study; Fort Worth annexation analyses*

---

## Limitations

- **PDF format matters.** The parser works best with text-based PDFs. Scanned/image PDFs won't extract.
- **Item extraction is pattern-based.** Unusual formatting may cause items to be missed or merged.
- **Per-acre estimates are prototypes.** Actual fiscal impact depends on final development program, market values, and adopted service levels.
- **This is informational only.** For official Fort Worth fiscal analysis, consult Planning & Data Analytics or Budget & Finance.

## File Structure

```
fw-fiscal-analyzer/
├── backend/
│   ├── main.py              # FastAPI server
│   ├── database.py          # SQLite storage
│   ├── routers/agendas.py   # API endpoints
│   └── services/
│       ├── pdf_parser.py    # PDF text extraction + item parsing
│       └── fiscal_analyzer.py  # Rule-based fiscal analysis engine
├── frontend/
│   └── src/
│       ├── App.jsx
│       └── components/
├── setup.bat    # One-time setup
└── start.bat    # Launch the app
```
