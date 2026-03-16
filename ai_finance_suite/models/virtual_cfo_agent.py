"""
Virtual CFO Agent - المدير المالي الافتراضي
==========================================

AI-powered agent for financial insights and recommendations.
REQUIRES AI: LLM with RAG (Smart Context Injection + Groq/Gemini API)

Features:
- Natural language financial queries
- AI-powered recommendations based on company data
- Live dashboard insights
- Budget variance analysis
- Performance analytics
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging
import json
import time

_logger = logging.getLogger(__name__)


class VirtualCFOAgent(models.Model):
    _name = 'af.virtual.cfo.agent'
    _description = 'Virtual CFO Agent - AI Financial Advisor'
    _inherit = ['mail.thread']

    name = fields.Char(string='Session Name', required=True, copy=False,
                       readonly=True, default='New')
    user_id = fields.Many2one('res.users', string='User',
                               default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company',
                                  default=lambda self: self.env.company)
    
    # Conversation History
    conversation_ids = fields.One2many('af.cfo.conversation', 'cfo_agent_id',
                                        string='Conversations')
    
    # Statistics
    query_count = fields.Integer(string='Total Queries',
                                  compute='_compute_stats')
    recommendation_count = fields.Integer(string='Recommendations Generated',
                                           default=0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                # Chat ID based on creation time
                vals['name'] = fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return super().create(vals_list)

    def _compute_stats(self):
        for record in self:
            record.query_count = len(record.conversation_ids)

    # ==================== QUERY METHODS ====================

    def ask_question(self, question):
        """
        Ask a financial question to the Virtual CFO.
        
        Args:
            question: Natural language question
            
        Returns:
            dict with answer and metadata
        """
        self.ensure_one()
        
        # Create conversation record
        conversation = self.env['af.cfo.conversation'].create({
            'cfo_agent_id': self.id,
            'question': question,
            'state': 'processing',
        })
        
        try:
            # Get context from Odoo data
            context = self._gather_financial_context(question)
            
            # Build conversation history for memory
            history = self._get_conversation_history()
            
            # Query LLM with RAG + memory
            start_time = time.time()
            answer = self._query_llm(question, context, history)
            processing_time = time.time() - start_time
            
            # Get credential info for tracking
            ICP = self.env['ir.config_parameter'].sudo()
            cfo_cred_id = int(ICP.get_param('ai_finance_suite.virtual_cfo_credential_id', 0))
            ai_model_name = ''
            if cfo_cred_id:
                cfo_cred = self.env['af.credential'].sudo().browse(cfo_cred_id)
                if cfo_cred.exists():
                    ai_model_name = f"{cfo_cred.provider}/{cfo_cred.get_effective_model()}"
            
            conversation.write({
                'answer': answer,
                'context_used': json.dumps(context, default=str),
                'state': 'completed',
                'ai_model': ai_model_name,
                'processing_time': round(processing_time, 2),
            })
            
            return {
                'success': True,
                'answer': answer,
                'conversation_id': conversation.id,
            }
            
        except Exception as e:
            conversation.write({
                'state': 'failed',
                'error_message': str(e),
            })
            _logger.error(f"Virtual CFO query failed: {e}")
            return {
                'success': False,
                'error': str(e),
            }

    def _get_conversation_history(self, limit=6):
        """Get recent conversation history for LLM memory."""
        conversations = self.env['af.cfo.conversation'].search(
            [('cfo_agent_id', '=', self.id), ('state', '=', 'completed')],
            order='create_date desc', limit=limit
        )
        history = []
        for conv in reversed(conversations):
            history.append({'role': 'user', 'content': conv.question})
            # Strip HTML from stored answer
            answer_text = conv.answer or ''
            if '<' in answer_text and '>' in answer_text:
                import re
                answer_text = re.sub(r'<[^>]+>', '', answer_text)
            history.append({'role': 'assistant', 'content': answer_text})
        return history

    def _get_month_boundaries(self):
        """Get current and previous month start/end dates."""
        today = fields.Date.today()
        month_start = today.replace(day=1)
        if today.month == 1:
            prev_month_start = today.replace(year=today.year - 1, month=12, day=1)
        else:
            prev_month_start = today.replace(month=today.month - 1, day=1)
        from datetime import timedelta
        prev_month_end = month_start - timedelta(days=1)
        return today, month_start, prev_month_start, prev_month_end

    def _gather_financial_context(self, question):
        """Gather relevant financial data as context for LLM."""
        company = self.company_id or self.env.company
        today = fields.Date.today()
        
        context = {
            'company_name': company.name,
            'currency': company.currency_id.name,
            'today': str(today),
        }
        
        # ALWAYS include financial overview
        context['financial_overview'] = self._get_financial_overview()
        
        # Add relevant financial summaries based on question keywords
        question_lower = question.lower()
        
        # Revenue/Sales context
        if any(word in question_lower for word in [
            'revenue', 'sales', 'income', 'invoice', 'invoiced', 'sold', 'selling',
            'turnover', 'earnings', 'billing', 'billed', 'receivable income',
            'money coming in', 'money received', 'collection',
            'مبيعات', 'إيرادات', 'فواتير', 'دخل', 'بيع', 'محصل',
        ]):
            context['sales_data'] = self._get_sales_summary()
            context['top_customers'] = self._get_top_customers()
        
        # Expenses context
        if any(word in question_lower for word in [
            'expense', 'cost', 'spending', 'spend', 'spent', 'bill', 'bills',
            'purchase', 'bought', 'buying', 'overhead', 'outgoing', 'outflow',
            'money going out', 'money paid', 'disbursement', 'expenditure',
            'مصروفات', 'تكاليف', 'فاتورة', 'مشتريات', 'إنفاق', 'صرف', 'نفقات',
        ]):
            context['expense_data'] = self._get_expense_summary()
            context['expense_by_vendor'] = self._get_expense_by_vendor()
        
        # Cash flow context
        if any(word in question_lower for word in [
            'cash', 'liquidity', 'flow', 'bank', 'payment', 'pay', 'paid',
            'money', 'fund', 'funds', 'balance', 'deposit', 'withdrawal',
            'wire', 'transfer', 'treasury', 'liquid',
            'نقدي', 'سيولة', 'بنك', 'دفع', 'رصيد', 'أموال', 'تحويل', 'خزينة',
        ]):
            context['cashflow_data'] = self._get_cashflow_summary()
            context['payments_data'] = self._get_payments_summary()
        
        # Receivables context
        if any(word in question_lower for word in [
            'receivable', 'owe', 'owed', 'debt', 'unpaid', 'overdue',
            'outstanding', 'collection', 'collect', 'due from', 'aging',
            'late payment', 'delayed', 'pending payment', 'not paid',
            'ديون', 'مستحقات', 'متأخر', 'غير مدفوع', 'تحصيل', 'مديونية',
        ]):
            context['receivables_data'] = self._get_receivables_summary()
        
        # Payables context
        if any(word in question_lower for word in [
            'payable', 'we owe', 'amount due', 'creditor',
            'pay vendor', 'pay supplier', 'due to', 'bills to pay',
            'obligation', 'liability', 'liabilities',
            'مستحقات علينا', 'التزامات', 'مطلوبات', 'دائنين',
        ]):
            context['payables_data'] = self._get_payables_summary()
        
        # Profit/margin context
        if any(word in question_lower for word in [
            'profit', 'margin', 'loss', 'profitable', 'profitability',
            'net income', 'gross', 'bottom line', 'breakeven', 'break even',
            'roi', 'return', 'gain', 'earning',
            'ربح', 'خسارة', 'هامش', 'صافي', 'عائد', 'ربحية',
        ]):
            context['profit_analysis'] = self._get_profit_analysis()
        
        # Product context
        if any(word in question_lower for word in [
            'product', 'item', 'best sell', 'top sell', 'worst',
            'goods', 'service', 'sku', 'catalog', 'best performing',
            'slow moving', 'fast moving', 'popular',
            'منتج', 'أفضل', 'سلعة', 'منتجات', 'خدمات', 'بضاعة',
        ]):
            context['product_performance'] = self._get_product_performance()
        
        # Trend/comparison context
        if any(word in question_lower for word in [
            'trend', 'compare', 'comparison', 'previous', 'growth',
            'increase', 'decrease', 'change', 'improve', 'decline',
            'up', 'down', 'better', 'worse', 'performance over',
            'مقارنة', 'سابق', 'نمو', 'زيادة', 'انخفاض', 'تحسن', 'تراجع',
        ]):
            context['trend_analysis'] = self._get_trend_analysis()
        
        # Inventory / Stock context
        if any(word in question_lower for word in [
            'inventory', 'stock', 'warehouse', 'quantity', 'valuation',
            'storage', 'stored', 'on hand', 'available', 'out of stock',
            'low stock', 'reorder', 'supply chain',
            'مخزون', 'مستودع', 'كمية', 'تخزين', 'متوفر', 'نفاد',
        ]):
            context['inventory_data'] = self._get_inventory_summary()
        
        # General Ledger / Account balances context
        if any(word in question_lower for word in [
            'ledger', 'journal', 'trial balance', 'chart of account',
            'entry', 'entries', 'posting', 'debit', 'credit',
            'account balance', 'account code', 'coa',
            'قيود', 'حساب', 'ميزان', 'دفتر', 'مدين', 'دائن', 'أستاذ',
        ]):
            context['general_ledger'] = self._get_general_ledger_summary()
        
        # Budget vs Actual context
        if any(word in question_lower for word in [
            'budget', 'actual', 'variance', 'forecast', 'projection',
            'planned', 'target', 'goal', 'utilization', 'overspend',
            'underspend', 'on track',
            'ميزانية', 'موازنة', 'فعلي', 'مخطط', 'هدف', 'تقديري',
        ]):
            context['budget_data'] = self._get_budget_vs_actual()
        
        # Bank Statement Reconciliation context
        if any(word in question_lower for word in [
            'reconcil', 'statement', 'match', 'discrepan', 'unmatched',
            'mismatch', 'bank match', 'bank statement',
            'تسوية', 'كشف', 'مطابقة', 'كشف حساب', 'كشف بنك',
        ]):
            context['reconciliation_data'] = self._get_reconciliation_summary()
        
        # Tax context
        if any(word in question_lower for word in [
            'tax', 'vat', 'gst', 'withholding', 'tax return',
            'tax liability', 'tax refund', 'input tax', 'output tax',
            'ضريبة', 'ضرائب', 'قيمة مضافة', 'استقطاع',
        ]):
            context['tax_data'] = self._get_tax_summary()
        
        # Multi-year / Historical context
        if any(word in question_lower for word in [
            'year', 'annual', 'history', 'historical', 'yearly', 'quarter',
            'quarterly', 'q1', 'q2', 'q3', 'q4', '2024', '2025', '2026',
            'last year', 'this year', 'multi-year', 'long term',
            'سنوي', 'سنة', 'تاريخ', 'ربع', 'ربعي', 'العام الماضي',
        ]):
            context['historical_data'] = self._get_historical_analysis()
        
        # Partners / Customers / Vendors directory
        if any(word in question_lower for word in [
            'customer', 'vendor', 'supplier', 'partner', 'contact', 'client',
            'who', 'how many', 'count', 'names', 'list all', 'directory',
            'buyer', 'inactive', 'new customer', 'new vendor',
            'عميل', 'عملاء', 'مورد', 'موردين', 'شركاء', 'اسماء', 'عدد',
        ]):
            context['partners_data'] = self._get_partners_summary()
        
        # === CATCH-ALL: General financial health / vague questions ===
        # If no specific context was triggered beyond the overview, load broad data
        if len(context) <= 4:  # only has company_name, currency, today, financial_overview
            if any(word in question_lower for word in [
                'health', 'status', 'overview', 'summary', 'report', 'situation',
                'how are we', 'how is the', 'tell me about', 'give me', 'show me',
                'financial', 'finance', 'overall', 'general', 'everything',
                'dashboard', 'kpi', 'insight', 'recommend', 'advice', 'suggest',
                'وضع', 'ملخص', 'تقرير', 'عام', 'كيف', 'مالي', 'نصيحة', 'توصية',
            ]):
                context['sales_data'] = self._get_sales_summary()
                context['expense_data'] = self._get_expense_summary()
                context['cashflow_data'] = self._get_cashflow_summary()
                context['receivables_data'] = self._get_receivables_summary()
                context['payables_data'] = self._get_payables_summary()
                context['profit_analysis'] = self._get_profit_analysis()
        
        return context

    def _get_financial_overview(self):
        """Get comprehensive financial overview - always included."""
        today, month_start, _, _ = self._get_month_boundaries()
        company_id = self.company_id.id or self.env.company.id
        
        # Sales this month
        sales_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        
        # Expenses this month
        vendor_bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        
        # Unpaid invoices (receivables)
        unpaid_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('company_id', '=', company_id),
        ])
        
        # Unpaid bills (payables)
        unpaid_bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('company_id', '=', company_id),
        ])
        
        total_sales = sum(sales_invoices.mapped('amount_total'))
        total_expenses = sum(vendor_bills.mapped('amount_total'))
        
        return {
            'period': f"{month_start} to {today}",
            'sales_this_month': total_sales,
            'expenses_this_month': total_expenses,
            'gross_profit_this_month': total_sales - total_expenses,
            'sales_invoice_count': len(sales_invoices),
            'bills_count': len(vendor_bills),
            'total_receivables': sum(unpaid_invoices.mapped('amount_residual')),
            'total_payables': sum(unpaid_bills.mapped('amount_residual')),
            'unpaid_invoices_count': len(unpaid_invoices),
            'unpaid_bills_count': len(unpaid_bills),
        }

    def _get_sales_summary(self):
        """Get sales summary for current calendar month."""
        today, month_start, _, _ = self._get_month_boundaries()
        
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', self.company_id.id or self.env.company.id),
        ])
        
        return {
            'period': f"{month_start} to {today}",
            'month_total': sum(invoices.mapped('amount_total')),
            'invoice_count': len(invoices),
            'average_invoice': sum(invoices.mapped('amount_total')) / len(invoices) if invoices else 0,
        }

    def _get_expense_summary(self):
        """Get expense summary for current calendar month."""
        today, month_start, _, _ = self._get_month_boundaries()
        
        bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', self.company_id.id or self.env.company.id),
        ])
        
        return {
            'period': f"{month_start} to {today}",
            'month_total': sum(bills.mapped('amount_total')),
            'bill_count': len(bills),
        }

    def _get_cashflow_summary(self):
        """Get cash flow summary — bank/cash account balances."""
        company_id = self.company_id.id or self.env.company.id
        
        # Get bank and cash journal balances
        bank_journals = self.env['account.journal'].search([
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', company_id),
        ])
        
        accounts = []
        total_balance = 0.0
        for journal in bank_journals:
            # Sum the balance from the default debit account
            account = journal.default_account_id
            if account:
                balance = 0.0
                move_lines = self.env['account.move.line'].search([
                    ('account_id', '=', account.id),
                    ('parent_state', '=', 'posted'),
                    ('company_id', '=', company_id),
                ])
                balance = sum(move_lines.mapped('debit')) - sum(move_lines.mapped('credit'))
                accounts.append({
                    'journal': journal.name,
                    'type': journal.type,
                    'balance': balance,
                })
                total_balance += balance
        
        return {
            'total_cash_and_bank': total_balance,
            'accounts': accounts,
        }

    def _get_receivables_summary(self):
        """Get receivables summary with aging breakdown."""
        from datetime import timedelta
        company_id = self.company_id.id or self.env.company.id
        today = fields.Date.today()
        
        unpaid_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('company_id', '=', company_id),
        ])
        
        # Aging buckets
        current = 0.0  # 0-30 days
        days_31_60 = 0.0
        days_61_90 = 0.0
        over_90 = 0.0
        overdue_customers = []
        
        for inv in unpaid_invoices:
            due_date = inv.invoice_date_due or inv.invoice_date or today
            days_overdue = (today - due_date).days
            residual = inv.amount_residual
            
            if days_overdue <= 0:
                current += residual
            elif days_overdue <= 30:
                current += residual
            elif days_overdue <= 60:
                days_31_60 += residual
            elif days_overdue <= 90:
                days_61_90 += residual
            else:
                over_90 += residual
            
            if days_overdue > 0:
                overdue_customers.append({
                    'customer': inv.partner_id.name,
                    'invoice': inv.name,
                    'amount': residual,
                    'days_overdue': days_overdue,
                })
        
        # Sort by most overdue
        overdue_customers.sort(key=lambda x: x['days_overdue'], reverse=True)
        
        return {
            'total_receivables': sum(unpaid_invoices.mapped('amount_residual')),
            'unpaid_count': len(unpaid_invoices),
            'aging': {
                'current_0_30': current,
                '31_60_days': days_31_60,
                '61_90_days': days_61_90,
                'over_90_days': over_90,
            },
            'top_overdue': overdue_customers[:5],
        }

    def _get_payables_summary(self):
        """Get payables summary with aging breakdown."""
        from datetime import timedelta
        company_id = self.company_id.id or self.env.company.id
        today = fields.Date.today()
        
        unpaid_bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ['not_paid', 'partial']),
            ('company_id', '=', company_id),
        ])
        
        # Aging buckets
        current = 0.0
        days_31_60 = 0.0
        days_61_90 = 0.0
        over_90 = 0.0
        overdue_vendors = []
        
        for bill in unpaid_bills:
            due_date = bill.invoice_date_due or bill.invoice_date or today
            days_overdue = (today - due_date).days
            residual = bill.amount_residual
            
            if days_overdue <= 0:
                current += residual
            elif days_overdue <= 30:
                current += residual
            elif days_overdue <= 60:
                days_31_60 += residual
            elif days_overdue <= 90:
                days_61_90 += residual
            else:
                over_90 += residual
            
            if days_overdue > 0:
                overdue_vendors.append({
                    'vendor': bill.partner_id.name,
                    'bill': bill.name,
                    'amount': residual,
                    'days_overdue': days_overdue,
                })
        
        overdue_vendors.sort(key=lambda x: x['days_overdue'], reverse=True)
        
        return {
            'total_payables': sum(unpaid_bills.mapped('amount_residual')),
            'unpaid_count': len(unpaid_bills),
            'aging': {
                'current_0_30': current,
                '31_60_days': days_31_60,
                '61_90_days': days_61_90,
                'over_90_days': over_90,
            },
            'top_overdue': overdue_vendors[:5],
        }

    def _get_top_customers(self, limit=5):
        """Get top customers by sales amount this month."""
        today, month_start, _, _ = self._get_month_boundaries()
        company_id = self.company_id.id or self.env.company.id
        
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        
        # Group by customer
        customer_totals = {}
        for inv in invoices:
            name = inv.partner_id.name
            customer_totals[name] = customer_totals.get(name, 0) + inv.amount_total
        
        # Sort and get top N
        sorted_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{'customer': name, 'amount': amt} for name, amt in sorted_customers]

    def _get_expense_by_vendor(self, limit=5):
        """Get expenses by vendor this month."""
        today, month_start, _, _ = self._get_month_boundaries()
        company_id = self.company_id.id or self.env.company.id
        
        bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        
        # Group by vendor
        vendor_totals = {}
        for bill in bills:
            name = bill.partner_id.name
            vendor_totals[name] = vendor_totals.get(name, 0) + bill.amount_total
        
        # Sort and get top N
        sorted_vendors = sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{'vendor': name, 'amount': amt} for name, amt in sorted_vendors]

    def _get_payments_summary(self):
        """Get payments summary for cash flow analysis this month."""
        today, month_start, _, _ = self._get_month_boundaries()
        company_id = self.company_id.id or self.env.company.id
        
        # Customer payments received
        customer_payments = self.env['account.payment'].search([
            ('payment_type', '=', 'inbound'),
            ('state', '=', 'posted'),
            ('date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        
        # Vendor payments made
        vendor_payments = self.env['account.payment'].search([
            ('payment_type', '=', 'outbound'),
            ('state', '=', 'posted'),
            ('date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        
        return {
            'payments_received': sum(customer_payments.mapped('amount')),
            'payments_received_count': len(customer_payments),
            'payments_made': sum(vendor_payments.mapped('amount')),
            'payments_made_count': len(vendor_payments),
            'net_cash_flow': sum(customer_payments.mapped('amount')) - sum(vendor_payments.mapped('amount')),
        }

    def _get_profit_analysis(self):
        """Get profit analysis for the current period."""
        overview = self._get_financial_overview()
        
        total_sales = overview.get('sales_this_month', 0)
        total_expenses = overview.get('expenses_this_month', 0)
        gross_profit = total_sales - total_expenses
        margin = (gross_profit / total_sales * 100) if total_sales > 0 else 0
        
        return {
            'total_revenue': total_sales,
            'total_expenses': total_expenses,
            'gross_profit': gross_profit,
            'profit_margin_percent': round(margin, 2),
        }

    def _get_product_performance(self, limit=10):
        """Get product performance by sales this month."""
        today, month_start, _, _ = self._get_month_boundaries()
        company_id = self.company_id.id or self.env.company.id
        
        invoice_lines = self.env['account.move.line'].search([
            ('move_id.move_type', '=', 'out_invoice'),
            ('move_id.state', '=', 'posted'),
            ('move_id.invoice_date', '>=', month_start),
            ('product_id', '!=', False),
            ('company_id', '=', company_id),
        ])
        
        # Group by product
        product_sales = {}
        for line in invoice_lines:
            name = line.product_id.name
            product_sales[name] = product_sales.get(name, 0) + line.price_subtotal
        
        # Sort and get top N
        sorted_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{'product': name, 'sales': amt} for name, amt in sorted_products]

    def _get_trend_analysis(self):
        """Compare this month vs previous month."""
        today, month_start, prev_month_start, prev_month_end = self._get_month_boundaries()
        company_id = self.company_id.id or self.env.company.id
        
        # This month sales
        this_month_sales = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        this_month_total = sum(this_month_sales.mapped('amount_total'))
        
        # Previous month sales
        prev_month_sales = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', prev_month_start),
            ('invoice_date', '<=', prev_month_end),
            ('company_id', '=', company_id),
        ])
        prev_month_total = sum(prev_month_sales.mapped('amount_total'))
        
        # This month expenses
        this_month_expenses = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        this_expenses_total = sum(this_month_expenses.mapped('amount_total'))
        
        # Previous month expenses
        prev_month_expenses = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', prev_month_start),
            ('invoice_date', '<=', prev_month_end),
            ('company_id', '=', company_id),
        ])
        prev_expenses_total = sum(prev_month_expenses.mapped('amount_total'))
        
        # Calculate changes
        sales_change = this_month_total - prev_month_total
        sales_change_pct = (sales_change / prev_month_total * 100) if prev_month_total > 0 else 0
        expenses_change = this_expenses_total - prev_expenses_total
        expenses_change_pct = (expenses_change / prev_expenses_total * 100) if prev_expenses_total > 0 else 0
        
        return {
            'this_month_sales': this_month_total,
            'previous_month_sales': prev_month_total,
            'sales_change_amount': sales_change,
            'sales_change_percent': round(sales_change_pct, 2),
            'sales_trend': 'up' if sales_change > 0 else 'down' if sales_change < 0 else 'stable',
            'this_month_expenses': this_expenses_total,
            'previous_month_expenses': prev_expenses_total,
            'expenses_change_amount': expenses_change,
            'expenses_change_percent': round(expenses_change_pct, 2),
        }

    # ========== NEW EXPANDED CONTEXT METHODS ==========

    def _get_inventory_summary(self):
        """Get inventory/stock levels and valuations."""
        company_id = self.company_id.id or self.env.company.id
        
        try:
            quants = self.env['stock.quant'].search([
                ('company_id', '=', company_id),
                ('location_id.usage', '=', 'internal'),
            ])
        except Exception:
            return {'error': 'Inventory module not installed or no stock data available.'}
        
        if not quants:
            return {'message': 'No inventory data found.'}
        
        # Total inventory value
        total_value = sum(quants.mapped('value'))
        total_qty = sum(quants.mapped('quantity'))
        
        # Group by product for top items
        product_stock = {}
        for quant in quants:
            name = quant.product_id.display_name
            if name not in product_stock:
                product_stock[name] = {'qty': 0, 'value': 0}
            product_stock[name]['qty'] += quant.quantity
            product_stock[name]['value'] += quant.value
        
        # Top products by value
        sorted_products = sorted(product_stock.items(), key=lambda x: x[1]['value'], reverse=True)[:10]
        
        # Low stock items (qty <= 5 and > 0)
        low_stock = [
            {'product': name, 'qty': data['qty'], 'value': data['value']}
            for name, data in product_stock.items()
            if 0 < data['qty'] <= 5
        ][:5]
        
        # Out of stock items
        out_of_stock = [name for name, data in product_stock.items() if data['qty'] <= 0]
        
        return {
            'total_inventory_value': total_value,
            'total_quantity': total_qty,
            'unique_products': len(product_stock),
            'top_by_value': [{'product': name, 'qty': data['qty'], 'value': data['value']} for name, data in sorted_products],
            'low_stock_items': low_stock,
            'out_of_stock_count': len(out_of_stock),
            'out_of_stock_products': out_of_stock[:10],
        }

    def _get_general_ledger_summary(self):
        """Get general ledger / trial balance summary."""
        company_id = self.company_id.id or self.env.company.id
        
        # In Odoo 19, account.account is shared (no company_id field)
        # Get all accounts, then filter by company at the move line level
        accounts = self.env['account.account'].search([])
        
        account_balances = []
        total_debit = 0.0
        total_credit = 0.0
        
        for account in accounts:
            move_lines = self.env['account.move.line'].search([
                ('account_id', '=', account.id),
                ('parent_state', '=', 'posted'),
                ('company_id', '=', company_id),
            ])
            if not move_lines:
                continue
            
            debit = sum(move_lines.mapped('debit'))
            credit = sum(move_lines.mapped('credit'))
            balance = debit - credit
            total_debit += debit
            total_credit += credit
            
            if abs(balance) > 0.01:  # Only include accounts with balance
                account_balances.append({
                    'code': account.code,
                    'name': account.name,
                    'debit': round(debit, 2),
                    'credit': round(credit, 2),
                    'balance': round(balance, 2),
                })
        
        # Sort by absolute balance (largest first)
        account_balances.sort(key=lambda x: abs(x['balance']), reverse=True)
        
        return {
            'total_debit': round(total_debit, 2),
            'total_credit': round(total_credit, 2),
            'accounts_with_balance': len(account_balances),
            'top_accounts': account_balances[:15],
        }

    def _get_budget_vs_actual(self):
        """Get budget vs actual comparison."""
        company_id = self.company_id.id or self.env.company.id
        today = fields.Date.today()
        
        try:
            budget_lines = self.env['crossovered.budget.lines'].search([
                ('crossovered_budget_id.company_id', '=', company_id),
                ('crossovered_budget_id.state', 'in', ['confirm', 'validate']),
                ('date_from', '<=', today),
                ('date_to', '>=', today),
            ])
        except Exception:
            return {'message': 'Budget module not installed or no budget data configured.'}
        
        if not budget_lines:
            return {'message': 'No active budgets found for the current period.'}
        
        budget_summary = []
        total_planned = 0.0
        total_actual = 0.0
        
        for line in budget_lines:
            planned = line.planned_amount
            actual = line.practical_amount
            variance = planned - actual
            pct = (actual / planned * 100) if planned else 0
            
            total_planned += planned
            total_actual += actual
            
            budget_summary.append({
                'budget': line.crossovered_budget_id.name,
                'account': line.general_budget_id.name if line.general_budget_id else 'N/A',
                'planned': round(planned, 2),
                'actual': round(actual, 2),
                'variance': round(variance, 2),
                'utilization_pct': round(pct, 2),
            })
        
        return {
            'total_planned': round(total_planned, 2),
            'total_actual': round(total_actual, 2),
            'total_variance': round(total_planned - total_actual, 2),
            'budget_lines': budget_summary[:10],
        }

    def _get_reconciliation_summary(self):
        """Get bank statement reconciliation summary from our module."""
        company_id = self.company_id.id or self.env.company.id
        
        try:
            bank_statements = self.env['af.bank.statement'].search([
                ('company_id', '=', company_id),
            ], order='create_date desc', limit=10)
        except Exception:
            return {'message': 'Bank statement reconciliation model not available.'}
        
        if not bank_statements:
            return {'message': 'No bank statements found.'}
        
        summaries = []
        for stmt in bank_statements:
            lines = stmt.line_ids if hasattr(stmt, 'line_ids') else []
            total_lines = len(lines)
            matched = len([l for l in lines if l.match_status == 'matched']) if lines else 0
            discrepancies = len([l for l in lines if l.match_status in ('ambiguous', 'missing_in_odoo', 'missing_in_bank')]) if lines else 0
            
            summaries.append({
                'name': stmt.name or f'Statement #{stmt.id}',
                'state': stmt.state,
                'total_lines': total_lines,
                'matched': matched,
                'discrepancies': discrepancies,
                'match_rate': f"{(matched / total_lines * 100):.1f}%" if total_lines else '0%',
            })
        
        return {
            'recent_statements': summaries,
            'total_statements': len(bank_statements),
        }

    def _get_tax_summary(self):
        """Get tax/VAT summary for current month."""
        today, month_start, _, _ = self._get_month_boundaries()
        company_id = self.company_id.id or self.env.company.id
        
        # Sales tax collected (output tax)
        sales_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        
        sales_tax = sum(sales_invoices.mapped('amount_tax'))
        sales_untaxed = sum(sales_invoices.mapped('amount_untaxed'))
        
        # Purchase tax paid (input tax)
        purchase_bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', month_start),
            ('company_id', '=', company_id),
        ])
        
        purchase_tax = sum(purchase_bills.mapped('amount_tax'))
        purchase_untaxed = sum(purchase_bills.mapped('amount_untaxed'))
        
        # Net tax liability
        net_tax = sales_tax - purchase_tax
        
        # Tax breakdown by rate
        tax_breakdown = {}
        for inv in sales_invoices:
            for line in inv.invoice_line_ids:
                for tax in line.tax_ids:
                    tax_name = tax.name
                    if tax_name not in tax_breakdown:
                        tax_breakdown[tax_name] = {'base': 0, 'tax_amount': 0}
                    tax_breakdown[tax_name]['base'] += line.price_subtotal
        
        return {
            'period': f"{month_start} to {today}",
            'sales_tax_collected': round(sales_tax, 2),
            'sales_untaxed_base': round(sales_untaxed, 2),
            'purchase_tax_paid': round(purchase_tax, 2),
            'purchase_untaxed_base': round(purchase_untaxed, 2),
            'net_tax_liability': round(net_tax, 2),
            'tax_position': 'owe tax' if net_tax > 0 else 'refund due' if net_tax < 0 else 'neutral',
        }

    def _get_historical_analysis(self):
        """Get multi-year historical analysis (up to 3 years)."""
        from datetime import timedelta
        company_id = self.company_id.id or self.env.company.id
        today = fields.Date.today()
        
        yearly_data = []
        
        for years_back in range(0, 3):
            year = today.year - years_back
            year_start = today.replace(year=year, month=1, day=1)
            year_end = today.replace(year=year, month=12, day=31)
            
            # If this year, only up to today
            if years_back == 0:
                year_end = today
            
            # Sales
            sales = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', year_start),
                ('invoice_date', '<=', year_end),
                ('company_id', '=', company_id),
            ])
            total_sales = sum(sales.mapped('amount_total'))
            
            # Expenses
            expenses = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', year_start),
                ('invoice_date', '<=', year_end),
                ('company_id', '=', company_id),
            ])
            total_expenses = sum(expenses.mapped('amount_total'))
            
            yearly_data.append({
                'year': year,
                'period': f"{year_start} to {year_end}",
                'total_sales': round(total_sales, 2),
                'total_expenses': round(total_expenses, 2),
                'gross_profit': round(total_sales - total_expenses, 2),
                'sales_count': len(sales),
                'bills_count': len(expenses),
            })
        
        # Quarterly breakdown for current year
        quarterly = []
        for q in range(1, 5):
            q_start_month = (q - 1) * 3 + 1
            q_end_month = q * 3
            q_start = today.replace(month=q_start_month, day=1)
            if q_end_month == 12:
                q_end = today.replace(month=12, day=31)
            else:
                q_end = today.replace(month=q_end_month + 1, day=1) - timedelta(days=1)
            
            if q_start > today:
                break
            if q_end > today:
                q_end = today
            
            q_sales = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', q_start),
                ('invoice_date', '<=', q_end),
                ('company_id', '=', company_id),
            ])
            q_expenses = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', q_start),
                ('invoice_date', '<=', q_end),
                ('company_id', '=', company_id),
            ])
            
            quarterly.append({
                'quarter': f"Q{q} {today.year}",
                'sales': round(sum(q_sales.mapped('amount_total')), 2),
                'expenses': round(sum(q_expenses.mapped('amount_total')), 2),
            })
        
        return {
            'yearly_summary': yearly_data,
            'quarterly_current_year': quarterly,
        }

    def _get_partners_summary(self):
        """Get customer and vendor directory summary."""
        from datetime import timedelta
        company_id = self.company_id.id or self.env.company.id
        today = fields.Date.today()
        today_month_start = today.replace(day=1)
        days_90_ago = today - timedelta(days=90)
        
        # All customers (have customer invoices)
        all_customers = self.env['res.partner'].search([
            ('customer_rank', '>', 0),
        ])
        
        # All vendors (have vendor bills)
        all_vendors = self.env['res.partner'].search([
            ('supplier_rank', '>', 0),
        ])
        
        # New customers this month
        new_customers = self.env['res.partner'].search([
            ('customer_rank', '>', 0),
            ('create_date', '>=', today_month_start),
        ])
        
        # New vendors this month
        new_vendors = self.env['res.partner'].search([
            ('supplier_rank', '>', 0),
            ('create_date', '>=', today_month_start),
        ])
        
        # Top customers by total invoiced amount (all time)
        customer_totals = {}
        invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('company_id', '=', company_id),
        ])
        for inv in invoices:
            name = inv.partner_id.name or 'Unknown'
            customer_totals[name] = customer_totals.get(name, 0) + inv.amount_total
        
        top_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Top vendors by total billed amount (all time)
        vendor_totals = {}
        bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('company_id', '=', company_id),
        ])
        for bill in bills:
            name = bill.partner_id.name or 'Unknown'
            vendor_totals[name] = vendor_totals.get(name, 0) + bill.amount_total
        
        top_vendors = sorted(vendor_totals.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Inactive customers (no invoice in 90+ days)
        recent_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', days_90_ago),
            ('company_id', '=', company_id),
        ])
        active_customer_ids = set(recent_invoices.mapped('partner_id').ids)
        inactive_customers = [c.name for c in all_customers if c.id not in active_customer_ids][:10]
        
        # Customer and vendor name lists
        all_customer_names = [c.name for c in all_customers[:30]]
        all_vendor_names = [v.name for v in all_vendors[:30]]
        
        return {
            'total_customers': len(all_customers),
            'total_vendors': len(all_vendors),
            'new_customers_this_month': len(new_customers),
            'new_vendors_this_month': len(new_vendors),
            'all_customer_names': all_customer_names,
            'all_vendor_names': all_vendor_names,
            'top_customers_by_revenue': [{'name': name, 'total_invoiced': round(amt, 2)} for name, amt in top_customers],
            'top_vendors_by_spending': [{'name': name, 'total_billed': round(amt, 2)} for name, amt in top_vendors],
            'inactive_customers_90_days': inactive_customers,
        }

    def _anonymize_context(self, context):
        """Replace real names with codes to protect data privacy."""
        import re
        context_str = json.dumps(context, default=str, ensure_ascii=False)
        
        # Build mapping of real names to codes
        name_map = {}
        counter = {'customer': 1, 'vendor': 1, 'company': 1}
        
        # Company name
        company_name = context.get('company_name', '')
        if company_name:
            code = f"COMPANY-{counter['company']}"
            name_map[company_name] = code
            counter['company'] += 1
        
        # Find partner/customer/vendor names in the context
        # Scan for known name fields in the JSON
        name_fields = ['customer', 'vendor', 'partner', 'name', 'supplier']
        
        def scan_for_names(obj, field_key=''):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, str) and any(nf in k.lower() for nf in name_fields):
                        if v and v not in name_map and len(v) > 2:
                            if 'customer' in k.lower() or 'client' in k.lower() or 'buyer' in k.lower():
                                code = f"CUSTOMER-{counter['customer']}"
                                counter['customer'] += 1
                            elif 'vendor' in k.lower() or 'supplier' in k.lower():
                                code = f"VENDOR-{counter['vendor']}"
                                counter['vendor'] += 1
                            else:
                                code = f"ENTITY-{counter['customer'] + counter['vendor']}"
                            name_map[v] = code
                    elif isinstance(v, (dict, list)):
                        scan_for_names(v, k)
            elif isinstance(obj, list):
                for item in obj:
                    scan_for_names(item, field_key)
        
        scan_for_names(context)
        
        # Replace names in the context string
        for real_name, code in name_map.items():
            context_str = context_str.replace(real_name, code)
        
        # Return anonymized context and the reverse map
        reverse_map = {v: k for k, v in name_map.items()}
        return context_str, reverse_map

    def _deanonymize_response(self, response, reverse_map):
        """Replace codes back with real names in the LLM response."""
        if not reverse_map:
            return response
        for code, real_name in reverse_map.items():
            response = response.replace(code, real_name)
        return response

    def _query_llm(self, question, context, history=None):
        """
        Query the LLM with financial context and conversation memory.
        Uses the AI provider/model configured via Virtual CFO Credential in Settings.
        """
        
        # Get Virtual CFO credential from configuration
        ICP = self.env['ir.config_parameter'].sudo()
        cfo_cred_id = int(ICP.get_param('ai_finance_suite.virtual_cfo_credential_id', 0))
        
        if not cfo_cred_id:
            return ("⚠️ Virtual CFO is not active. Please go to "
                    "TEST AI Finance → Configuration → Settings and select a "
                    "'Virtual CFO AI Credential'.")
        
        cfo_cred = self.env['af.credential'].sudo().browse(cfo_cred_id)
        if not cfo_cred.exists():
            return ("⚠️ The configured Virtual CFO Credential no longer exists. "
                    "Please update it in TEST AI Finance → Configuration → Settings.")
        
        provider = cfo_cred.provider
        api_key = cfo_cred.api_key
        model = cfo_cred.get_effective_model()
        anonymize = cfo_cred.anonymize_data
        
        if not provider:
            return "⚠️ Virtual CFO Credential has no provider selected."
        
        if not api_key and provider != 'custom':
            return "⚠️ Virtual CFO Credential has no API key. Please add it in AI Credentials."
        
        if not model:
            return "⚠️ No model selected. Please select a model in AI Credentials."
        
        _logger.info("Virtual CFO: Using provider=%s, model=%s, credential='%s'",
                      provider, model, cfo_cred.name)

        try:
            # Build prompt with context
            system_prompt = """You are a Virtual CFO (Chief Financial Officer) AI assistant for Odoo ERP.
You analyze financial data and provide clear, actionable insights.

**LANGUAGE RULES:**
- If question is in Arabic, respond in Arabic
- If question is in English, respond in English
- Always use the company's currency for amounts

**FORMATTING RULES:**
- Use plain text ONLY - absolutely NO HTML tags
- Use **bold** for headings and emphasis
- Use "•" for bullet points
- Use "1." "2." for numbered lists
- Keep responses concise (max 200 words)
- Always include specific numbers from the data

**HOW TO ANSWER COMMON QUESTIONS:**

For "total sales this month":
→ Report sales_this_month from financial_overview
→ Include invoice count
→ Compare to expenses if relevant

For "major expenses":
→ List expense_by_vendor data
→ Show total expenses this month
→ Highlight largest categories

For "current cash position":
→ Report receivables and payables balance
→ Show net position (receivables - payables)
→ Mention any cash flow concerns

For "overdue payments" or "unpaid invoices":
→ Report unpaid_invoices_count
→ Show total_receivables amount
→ Recommend collection action if > 0

For "profit margin":
→ Calculate: (sales - expenses) / sales × 100
→ Show gross profit amount
→ Provide context on whether it's healthy

**RESPONSE FORMAT:**
**[Main Answer]**
Direct answer with specific number

**Key Details**
• Detail 1
• Detail 2

**💡 Recommendation**
One actionable suggestion"""

            context_str = json.dumps(context, indent=2, default=str, ensure_ascii=False)
            
            # Apply anonymization if enabled
            reverse_map = {}
            if anonymize:
                context_str, reverse_map = self._anonymize_context(context)
            
            full_prompt = f"""Company Financial Data:
{context_str}

Question: {question}

Provide a clear, helpful response following the formatting rules."""

            # Build messages with conversation memory
            messages = [{"role": "system", "content": system_prompt}]
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": full_prompt})
            
            # Call LLM based on provider from the credential
            if provider == 'groq':
                from groq import Groq
                client = Groq(api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                )
                answer = response.choices[0].message.content
                
            elif provider == 'gemini':
                from google import genai
                from google.genai import types
                
                client = genai.Client(api_key=api_key)
                
                # Gemini: build multi-turn content with history
                contents = []
                # Add system + history as context in first message
                history_text = ""
                if history:
                    for msg in history:
                        role = 'User' if msg['role'] == 'user' else 'CFO'
                        history_text += f"\n{role}: {msg['content']}\n"
                
                combined = f"{system_prompt}\n"
                if history_text:
                    combined += f"\nPrevious Conversation:\n{history_text}\n"
                combined += f"\n{full_prompt}"
                
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Content(
                            parts=[
                                types.Part.from_text(text=combined)
                            ]
                        )
                    ]
                )
                answer = response.text
                
            elif provider == 'openai':
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                )
                answer = response.choices[0].message.content

            elif provider == 'deepseek':
                from openai import OpenAI
                client = OpenAI(
                    api_key=api_key,
                    base_url="https://api.deepseek.com"
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                )
                answer = response.choices[0].message.content

            elif provider == 'claude':
                # Anthropic Claude API (Messages format)
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }
                # Claude requires system as separate param, not in messages
                claude_messages = []
                if history:
                    claude_messages.extend([
                        {"role": m["role"], "content": m["content"]}
                        for m in history if m["role"] in ("user", "assistant")
                    ])
                claude_messages.append({"role": "user", "content": full_prompt})
                
                payload = {
                    "model": model,
                    "system": system_prompt,
                    "messages": claude_messages,
                    "max_tokens": 2048,
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                result = resp.json()
                answer = result['content'][0]['text']

            elif provider == 'xai':
                # xAI Grok API (OpenAI-compatible)
                from openai import OpenAI
                client = OpenAI(
                    api_key=api_key,
                    base_url="https://api.x.ai/v1"
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                )
                answer = response.choices[0].message.content

            elif provider == 'mistral':
                # Mistral AI API (OpenAI-compatible)
                from openai import OpenAI
                client = OpenAI(
                    api_key=api_key,
                    base_url="https://api.mistral.ai/v1"
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                )
                answer = response.choices[0].message.content

            elif provider == 'cohere':
                # Cohere v2 Chat API
                url = "https://api.cohere.com/v2/chat"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": 2048,
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                result = resp.json()
                answer = result['message']['content'][0]['text']

            elif provider == 'custom':
                # Custom / Self-hosted LLM via OpenAI-compatible API
                base_url = cfo_cred.api_base_url
                if not base_url:
                    return "⚠️ Custom provider requires an API Base URL. Please set it in AI Credentials."
                headers = {"Content-Type": "application/json"}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                
                payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 2048,
                }
                
                url = f"{base_url.rstrip('/')}/chat/completions"
                resp = requests.post(url, headers=headers, json=payload, timeout=120)
                resp.raise_for_status()
                result = resp.json()
                answer = result['choices'][0]['message']['content']

            else:
                answer = f"⚠️ Provider '{provider}' is not supported. Supported: Gemini, OpenAI, Claude, xAI Grok, Mistral, Cohere, Groq, DeepSeek, Custom."
            
            _logger.info(f"Virtual CFO query processed using {provider}/{model}")
            
            # De-anonymize the response if anonymization was used
            if anonymize and reverse_map:
                answer = self._deanonymize_response(answer, reverse_map)
            
            return answer
            
        except ImportError as e:
            _logger.error(f"LLM library not installed: {e}")
            return f"❌ Missing library. Please install: {str(e)}"
        except Exception as e:
            _logger.error(f"LLM query failed: {e}")
            return f"❌ Error querying AI: {str(e)}"

    # ==================== ACTIONS ====================

    def action_new_conversation(self):
        """Open CFO query wizard."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ask Virtual CFO',
            'res_model': 'af.cfo.query.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_cfo_agent_id': self.id},
        }

    def action_view_recommendations(self):
        """View generated recommendations (Future Feature)."""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Coming Soon',
                'message': 'AI Recommendations will be available in the next update.',
                'type': 'info',
            }
        }

    def action_generate_insights(self):
        """Generate proactive financial insights."""
        self.ensure_one()
        
        insight_questions = [
            "What are the top 3 customers with overdue payments?",
            "Are there any vendors with balance discrepancies?",
            "What is the current cash position and trend?",
        ]
        
        for question in insight_questions:
            self.ask_question(question)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Insights Generated',
                'message': f'Generated {len(insight_questions)} financial insights.',
                'type': 'success',
            }
        }


class CFOConversation(models.Model):
    _name = 'af.cfo.conversation'
    _description = 'Virtual CFO Conversation'
    _order = 'create_date desc'

    cfo_agent_id = fields.Many2one('af.virtual.cfo.agent', string='CFO Session',
                                    ondelete='cascade')
    question = fields.Text(string='Question', required=True)
    answer = fields.Html(string='Answer')
    
    state = fields.Selection([
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ], string='Status', default='processing')
    
    context_used = fields.Text(string='Context Used (JSON)')
    ai_model = fields.Char(string='AI Model Used')
    processing_time = fields.Float(string='Processing Time (sec)')
    error_message = fields.Text(string='Error Message')
