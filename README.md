# AI Finance Suite

**Advanced AI-Powered Finance Module for Odoo 19**
*Virtual CFO · OCR Engine · Smart Reconciliation · Finance Dashboard*

---

## Overview

AI Finance Suite transforms your Odoo 19 accounting into an intelligent financial command center. It combines six AI-powered tools in a single module — from extracting invoices with vision AI to chatting with your CFO in plain English.

---

## Features

### 1. AI OCR Engine
- Extract structured data from **Vendor Bills, Customer Invoices, Refunds, Partner Statements, and Bank Statements** — supports PDF, images, and Excel
- 3-step wizard: **Upload → Review → Post**
- Auto-creates taxes, products, partner records, and journal entries
- Duplicate detection before posting
- Processes Excel-based bank statements automatically

### 2. Virtual CFO Chatbot
- Chat with your financial data in **plain English**
- Answers questions about Sales, Expenses, Receivables, Payables, Cash Flow, Trends, Budget vs Actual, GL balances, and more
- **Session memory** — continues conversations coherently
- Covers **13 financial data domains** via smart Odoo ORM queries
- ChatGPT-style OWL interface with session history sidebar

### 3. AI Finance Dashboard
- Real-time **KPI cards**: Total Sales, Gross Profit, To Collect, To Pay, Net Cash Position, Collection Rate, Payment Rate
- **4 interactive Chart.js charts**: Sales vs Purchases (6-month bar), Capital Map (doughnut), AR Aging (stacked bar), Cash Flow Forecast (line)
- **Top 5** overdue customers, pending invoices, and outstanding vendors
- Period filters: This Month, Last Month, Quarter, Year
- AI-generated **smart alerts** for overdue thresholds and margin drops

### 4. Smart Reconciliation Engine
- **Partner Statement Reconciliation**: 4-priority matching (exact ref → token → substring → reverse match)
- **Bank Statement Reconciliation**: amount + date matching with configurable ±3-day tolerance
- Detects duplicates, unposted invoices, and missing-in-Odoo transactions
- QWeb PDF **reconciliation reports** for auditors

### 5. AI Credentials Manager
- Centralized, role-protected API key storage
- **9 AI Providers**: Google Gemini, OpenAI, Claude, xAI Grok, Mistral AI, Cohere, Groq, DeepSeek, Custom/Self-Hosted
- Test Connection button per provider
- Per-provider model selection (e.g. `gemini-2.5-flash`, `gpt-4o`, `claude-3-5-sonnet`)
- Optional **data anonymization** before sending to external APIs

### 6. Refund Tracker
- Full refund lifecycle: Request → Pending → Received
- OCR-powered credit memo scanning
- Days-pending tracking with deadline awareness
- Linked to original vendor bills and credit notes

---

## Requirements

| Requirement | Details |
|---|---|
| **Odoo Version** | 19.0 Community or Enterprise |
| **Python** | 3.10+ |
| **AI Provider** | At least one API key (Google Gemini free tier recommended for start) |

### Python Dependencies
Install before or after module installation:

```bash
pip install groq>=0.4.0 openai>=1.0.0 google-genai>=1.0.0 pandas>=2.0.0 openpyxl>=3.1.0 rapidfuzz>=3.0.0
```

Or use the provided `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## Installation

### Option A — Odoo.sh / Production Server
1. Upload the `ai_finance_suite` folder to your **custom addons** directory
2. Install Python dependencies via SSH: `pip install -r requirements.txt`
3. Restart the Odoo service
4. Go to **Apps**, search for **AI Finance Suite**, and click **Install**

### Option B — GitHub + Odoo.sh
1. Add this repository as a **private GitHub repository**
2. In Odoo.sh, go to **Settings → Branches → Connected Repository**
3. Add the repo and set the branch
4. Install dependencies in `requirements.txt` via Odoo.sh shell
5. Install the module from Apps

### Option C — Local Development
```bash
# Clone or copy to your addons path
cp -r ai_finance_suite /path/to/odoo/custom_addons/

# Install dependencies
pip install -r ai_finance_suite/requirements.txt

# Start Odoo with the addons path
python odoo-bin -d your_database -u ai_finance_suite --addons-path=...
```

---

## Configuration

### Step 1: Add AI Credentials
Go to **AI Finance Suite → Configuration → AI Credentials** and create a credential:

1. **Provider**: Select your AI provider (e.g. Google Gemini)
2. **API Key**: Enter your provider's API key
3. **Model**: Select the model (e.g. `gemini-2.5-flash`)
4. Click **Test Connection** to verify

### Step 2: Assign Credentials
Go to **AI Finance Suite → Configuration → Settings**:
- Set **OCR Credential** for the OCR Engine
- Set **Virtual CFO Credential** for the Chatbot

### Step 3: Start Using
- **OCR Engine**: AI Finance Suite → OCR Engine → New
- **Virtual CFO**: AI Finance Suite → Virtual CFO (Chatbot)
- **Dashboard**: AI Finance Suite → Dashboard
- **Reconciliation**: AI Finance Suite → Reconciliation → Partner Statements or Bank Statements

---

## Supported AI Providers

| Provider | Models | Notes |
|---|---|---|
| Google Gemini | gemini-2.5-flash, gemini-1.5-pro | Best for OCR (Vision API) |
| OpenAI | gpt-4o, gpt-4o-mini, o1 | Strong reasoning |
| Anthropic Claude | claude-3-5-sonnet, claude-3-haiku | Great for long context |
| xAI Grok | grok-2, grok-beta | Fast responses |
| Mistral AI | mistral-large, mistral-small | EU-based provider |
| Cohere | command-r-plus, command-r | Strong retrieval |
| Groq | llama-3.3-70b, deepseek-r1 | Fastest inference |
| DeepSeek | deepseek-chat, deepseek-r1 | Cost-effective |
| Custom/Self-Hosted | Any OpenAI-compatible | Ollama, LM Studio, etc. |

---

## Security Notes

- **API keys** are stored encrypted in the Odoo database and only visible to Accounting Managers (`account.group_account_manager`) and System Administrators
- The optional **data anonymization** feature replaces partner names and company names before sending context to external AI APIs
- All reconciliation operations are logged in the chatter with user attribution
- Credentials use Odoo's built-in `password` field masking in the UI

---

## File Structure

```
ai_finance_suite/
├── __manifest__.py          # Module definition & metadata
├── __init__.py
├── requirements.txt         # Python dependencies
├── README.md
├── models/
│   ├── ai_credential.py     # AI provider credential manager
│   ├── ai_config.py         # Settings page extension
│   ├── virtual_cfo_agent.py # Virtual CFO chatbot engine
│   ├── ai_finance_dashboard.py  # Dashboard KPI engine
│   ├── vendor_statement.py  # Partner statement reconciliation
│   ├── bank_statement.py    # Bank statement reconciliation
│   ├── ai_refund_tracking.py    # Refund lifecycle tracking
│   └── account_bank_statement.py  # Core model extension
├── wizards/
│   ├── vendor_bill_wizard.py    # OCR multi-document wizard
│   └── cfo_query_wizard.py      # CFO quick-query dialog
├── views/                   # Odoo XML views & menus
├── reports/                 # QWeb PDF reconciliation reports
├── security/
│   └── ir.model.access.csv  # Access control rules
└── static/src/
    ├── js/                  # OWL components (Dashboard + Chat)
    ├── xml/                 # OWL templates
    └── scss/                # Component styles
```

---

## Changelog

### v19.0.1.0.0 (2025-03-16)
- Initial production release
- OCR Engine supporting 5 document types (vendor bills, customer invoices, refunds, partner statements, bank statements)
- Virtual CFO with 9 AI provider support and 13 financial data domains
- OWL Analytics Dashboard with 4 Chart.js visualizations
- 4-priority Partner Statement Reconciliation
- Amount+date Bank Statement Reconciliation
- AI Credentials Manager with role-based access
- QWeb PDF reconciliation reports

---

## License

This module is licensed under [LGPL-3](https://www.gnu.org/licenses/lgpl-3.0.en.html).

---

## Support

For issues, feature requests, or questions:
- Open an issue on GitHub
- Email: support@ai-finance-suite.com

---

*Built with ❤️ for the Odoo community. Powered by Google Gemini, OpenAI, Claude, Groq, and more.*
