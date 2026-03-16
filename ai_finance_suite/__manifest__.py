# -*- coding: utf-8 -*-
{
    'name': 'AI Finance',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Finance',
    'summary': 'AI-Powered Finance Suite: Virtual CFO, OCR Engine & Smart Reconciliation for Odoo 19',
    'description': """
AI Finance Suite — by Woledge Team
=====================================

Empower your finance team with the full power of Artificial Intelligence.
Developed by Woledge — Administrative & Financial Consulting | www.woledge.com

Transform your Odoo 19 accounting into a fully intelligent financial command center.
AI Finance Suite bundles six production-ready AI tools in a single install:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. AI OCR ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Extract structured data from financial documents using Vision AI:
• Vendor Bills, Customer Invoices, Credit Notes/Refunds — PDF or Images
• Partner (Vendor/Customer) Statements — PDF & Excel formats
• Bank Statements — PDF & Excel formats
• 3-step guided wizard: Upload → AI Review → Post with one click
• High-accuracy extraction with auto-created taxes, products, and journal entries
• Smart duplicate detection prevents double posting
• Supports all major currencies and multi-line invoices

2. VIRTUAL CFO CHATBOT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Your AI-powered financial advisor, available 24/7 inside Odoo:
• Ask questions in plain Arabic or English about your financial data
• Instant, context-aware answers on Sales, Expenses, Cash Flow, AR/AP
• Smart financial context injection: queries Odoo live data before answering
• Persistent session memory — continues conversations coherently
• Covers 13 financial domains: GL, budget, taxes, inventory, trends and more
• ChatGPT-style chat interface with full session history sidebar
• Supports 9 AI providers:
  Google Gemini · OpenAI · Anthropic Claude · xAI Grok · Mistral AI
  Cohere · Groq · DeepSeek · Custom / Self-Hosted LLMs (Ollama, LM Studio)

3. AI FINANCE DASHBOARD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Live financial intelligence at a glance:
• 8 real-time KPI cards: Total Sales, Gross Profit, Margin %, Receivables,
  Payables, Net Cash Position, Collection Rate, Payment Rate
• 4 interactive Chart.js visualizations:
  - Sales vs Purchases (6-month bar chart)
  - Capital Map: Bank / Receivables / Vendor Prepaid (doughnut)
  - AR Aging Analysis — 4 time buckets (stacked bar)
  - Cash Flow Forecast — 30 / 60 / 90 day projection (line chart)
• Top 5 overdue customers, pending invoices, and outstanding vendors
• Smart AI alerts: overdue thresholds, margin drops, cash warnings
• Period filters: This Month · Last Month · Quarter · Year
• Partner & Journal drill-down filters

4. SMART RECONCILIATION ENGINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Automated matching between your records and external documents:

Partner Statement Reconciliation:
• Match vendor or customer statements against Odoo open items
• 4-priority matching algorithm: exact ref → token → substring → reverse
• Detects unposted invoices, true duplicates, and missing-in-Odoo entries
• Configurable match key column (voucher number, reference, description)

Bank Statement Reconciliation:
• Match bank transactions against Odoo journal entries and payments
• Amount + date matching with configurable ±3 day tolerance
• Identifies unmatched bank lines and missing Odoo entries

Both engines produce:
• QWeb PDF reconciliation reports suitable for external auditors
• Full chatter history with timestamps and user attribution

5. SECURE AI CREDENTIALS MANAGER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Enterprise-grade API key management for all your AI providers:
• Centralized storage — configure all providers in one place
• Role-based access: only Accounting Managers can view or edit credentials
• One-click Test Connection button per provider before going live
• Per-provider model selection (e.g. gemini-2.5-flash, gpt-4o, claude-3-5-sonnet)
• Optional data anonymization: replaces partner names before sending to AI

6. REFUND TRACKER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Track vendor credit notes from request through to receipt:
• Full refund lifecycle: Request → Pending → Received
• OCR-powered credit memo scanning
• Automatic days-pending computation with deadline awareness
• Linked to original vendor bills and matching credit notes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REQUIREMENTS
• Odoo 19.0 Community or Enterprise
• Python: groq, openai, google-genai, pandas, openpyxl, rapidfuzz
  Install with: pip install -r requirements.txt
• At least one AI provider API key
  (Google Gemini free tier is the recommended starting point)

SUPPORTED AI PROVIDERS
Google Gemini · OpenAI GPT-4o · Anthropic Claude · xAI Grok
Mistral AI · Cohere · Groq · DeepSeek · Custom / Self-Hosted LLMs

ABOUT WOLEDGE
Woledge is an administrative and financial consulting company specializing
in ERP implementation, financial systems, and training.
Website: https://www.woledge.com

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """,
    'author': 'Woledge Team',
    'website': 'https://www.woledge.com',
    'support': 'info@woledge.com',
    'depends': [
        'base',
        'mail',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/ai_config_views.xml',
        'views/ai_credential_views.xml',
        'views/ai_finance_dashboard_views.xml',
        'views/ai_finance_dashboard_action.xml',
        'views/vendor_statement_views.xml',
        'views/bank_statement_views.xml',
        'reports/reconciliation_report.xml',
        'wizards/vendor_bill_wizard_views.xml',
        'views/virtual_cfo_views.xml',
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'ai_finance_suite/static/src/scss/cfo_chat.scss',
            'ai_finance_suite/static/src/js/cfo_chat_component.js',
            'ai_finance_suite/static/src/xml/cfo_chat_template.xml',
            'ai_finance_suite/static/src/scss/ai_dashboard.scss',
            'ai_finance_suite/static/src/js/ai_dashboard.js',
            'ai_finance_suite/static/src/xml/ai_dashboard.xml',
        ],
    },
    'images': ['static/description/banner.png', 'static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'price': 399.00,
    'currency': 'USD',
}
