# -*- coding: utf-8 -*-
{
    'name': 'AI Finance',
    'version': '19.0.1.8',
    'website': 'woledge.com'
    'category': 'Accounting/Finance',
    'summary': 'Advanced AI Finance Module: Virtual CFO & OCR Engine',
    'description': """
AI Finance V1
=============

Empower your Odoo accounting with Artificial Intelligence.

Key Features:
1. **OCR Engine**: 
   - Extract data from Vendor Bills (PDF/Images).
   - High accuracy with confidence scoring.
   - Review and create bills in one click.

2. **Virtual CFO (Chatbot)**:
   - Chat with your financial data in natural language.
   - Instant answers about Sales, Expenses, and Trends.
   - Smart context injection for accurate financial insights.
   - Supports multiple AI providers (Gemini, OpenAI, Groq, DeepSeek).

3. **Secure AI Credentials**:
   - Centralized API key management.
   - Enterprise-grade security for sensitive keys.
    """,
    'author': 'AI Finance Team',
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
            'test_AI_finance/static/src/scss/cfo_chat.scss',
            'test_AI_finance/static/src/js/cfo_chat_component.js',
            'test_AI_finance/static/src/xml/cfo_chat_template.xml',
            'test_AI_finance/static/src/scss/ai_dashboard.scss',
            'test_AI_finance/static/src/js/ai_dashboard.js',
            'test_AI_finance/static/src/xml/ai_dashboard.xml',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
