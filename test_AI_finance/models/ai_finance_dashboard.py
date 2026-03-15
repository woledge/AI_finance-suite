# -*- coding: utf-8 -*-
"""
AI Finance Dashboard
====================

Provides a live dashboard with key financial indicators and a
Capital Map showing the distribution of funds across bank accounts,
customer receivables, and vendor prepaid balances.
"""

from odoo import models, fields, api, _
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)


class AIFinanceDashboard(models.Model):
    _name = 'test.ai.finance.dashboard'
    _description = 'AI Finance Dashboard'

    name = fields.Char(default='AI Finance Dashboard', readonly=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one(related='company_id.currency_id')

    # ==================== DATE FILTERS ====================
    date_from = fields.Date(string='From', default=lambda self: date.today().replace(day=1))
    date_to = fields.Date(string='To', default=fields.Date.context_today)

    # ==================== KPI FIELDS ====================
    total_sales = fields.Monetary(string='Total Sales', compute='_compute_kpis', currency_field='currency_id')
    total_purchases = fields.Monetary(string='Total Purchases', compute='_compute_kpis', currency_field='currency_id')
    gross_profit = fields.Monetary(string='Gross Profit', compute='_compute_kpis', currency_field='currency_id')
    profit_margin = fields.Float(string='Profit Margin %', compute='_compute_kpis')

    total_receivable = fields.Monetary(string='Customer Receivables', compute='_compute_kpis', currency_field='currency_id')
    total_payable = fields.Monetary(string='Vendor Payables', compute='_compute_kpis', currency_field='currency_id')

    invoices_to_collect = fields.Integer(string='Invoices to Collect', compute='_compute_kpis')
    bills_to_pay = fields.Integer(string='Bills to Pay', compute='_compute_kpis')

    collection_rate = fields.Float(string='Collection Rate %', compute='_compute_kpis')
    payment_rate = fields.Float(string='Payment Rate %', compute='_compute_kpis')

    total_overdue_receivable = fields.Monetary(string='Overdue Receivables', compute='_compute_kpis', currency_field='currency_id')
    total_overdue_payable = fields.Monetary(string='Overdue Payables', compute='_compute_kpis', currency_field='currency_id')

    # ==================== CAPITAL MAP FIELDS ====================
    total_bank_balance = fields.Monetary(string='Bank & Cash Balance', compute='_compute_capital_map', currency_field='currency_id')
    total_customer_debt = fields.Monetary(string='Customer Debts (Receivables)', compute='_compute_capital_map', currency_field='currency_id')
    total_vendor_prepaid = fields.Monetary(string='Vendor Prepaid (Advances)', compute='_compute_capital_map', currency_field='currency_id')
    total_capital = fields.Monetary(string='Total Liquid Capital', compute='_compute_capital_map', currency_field='currency_id')

    bank_percentage = fields.Float(string='Bank %', compute='_compute_capital_map')
    receivable_percentage = fields.Float(string='Receivable %', compute='_compute_capital_map')
    prepaid_percentage = fields.Float(string='Prepaid %', compute='_compute_capital_map')

    # ==================== TREND FIELDS ====================
    sales_trend = fields.Float(string='Sales Trend %', compute='_compute_trends',
                               help='Compared to same-length previous period')
    purchases_trend = fields.Float(string='Purchases Trend %', compute='_compute_trends')
    receivable_trend = fields.Char(string='Receivable Status', compute='_compute_trends')

    # ==================== OCR / AI MODULE STATS ====================
    total_ocr_processed = fields.Integer(string='Documents Processed (OCR)', compute='_compute_module_stats')
    total_statements_reconciled = fields.Integer(string='Statements Reconciled', compute='_compute_module_stats')
    total_bank_statements = fields.Integer(string='Bank Statements Processed', compute='_compute_module_stats')
    total_refunds_tracked = fields.Integer(string='Refunds Tracked', compute='_compute_module_stats')

    # ==================== NET CASH POSITION ====================
    net_cash_position = fields.Monetary(
        string='Net Cash Position',
        compute='_compute_net_cash',
        currency_field='currency_id',
        help='Bank Balance minus Vendor Payables = Available Cash'
    )

    # ==================== AGING ANALYSIS ====================
    aging_current = fields.Monetary(string='Current (0-30 days)', compute='_compute_aging', currency_field='currency_id')
    aging_30_60 = fields.Monetary(string='31-60 days', compute='_compute_aging', currency_field='currency_id')
    aging_60_90 = fields.Monetary(string='61-90 days', compute='_compute_aging', currency_field='currency_id')
    aging_over_90 = fields.Monetary(string='90+ days', compute='_compute_aging', currency_field='currency_id')
    aging_current_count = fields.Integer(string='Current Count', compute='_compute_aging')
    aging_30_60_count = fields.Integer(string='31-60 Count', compute='_compute_aging')
    aging_60_90_count = fields.Integer(string='61-90 Count', compute='_compute_aging')
    aging_over_90_count = fields.Integer(string='90+ Count', compute='_compute_aging')

    # ==================== SMART ALERTS ====================
    alert_html = fields.Html(string='Alerts', compute='_compute_alerts', sanitize=False)

    # ==================== TOP 5 OVERDUE PARTNERS ====================
    top_overdue_html = fields.Html(string='Top 5 Overdue Partners', compute='_compute_top_overdue', sanitize=False)

    @api.depends('date_from', 'date_to')
    def _compute_kpis(self):
        for rec in self:
            date_from = rec.date_from or date.today().replace(day=1)
            date_to = rec.date_to or date.today()
            company = rec.company_id or self.env.company

            # --- Sales (Customer Invoices) ---
            sales_invoices = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('company_id', '=', company.id),
            ])
            rec.total_sales = sum(sales_invoices.mapped('amount_total_signed'))

            # --- Purchases (Vendor Bills) ---
            purchase_bills = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('company_id', '=', company.id),
            ])
            rec.total_purchases = sum(abs(b.amount_total_signed) for b in purchase_bills)

            # --- Profit ---
            rec.gross_profit = abs(rec.total_sales) - rec.total_purchases
            rec.profit_margin = (rec.gross_profit / abs(rec.total_sales) * 100) if rec.total_sales else 0.0

            # --- Receivables (Open customer invoices) ---
            open_receivables = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('company_id', '=', company.id),
            ])
            rec.total_receivable = sum(open_receivables.mapped('amount_residual'))
            rec.invoices_to_collect = len(open_receivables)

            # --- Payables (Open vendor bills) ---
            open_payables = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('company_id', '=', company.id),
            ])
            rec.total_payable = sum(open_payables.mapped('amount_residual'))
            rec.bills_to_pay = len(open_payables)

            # --- Collection Rate ---
            total_invoiced = self.env['account.move'].search_count([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('company_id', '=', company.id),
            ])
            paid_invoices = self.env['account.move'].search_count([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('paid', 'in_payment')),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('company_id', '=', company.id),
            ])
            rec.collection_rate = (paid_invoices / total_invoiced * 100) if total_invoiced else 0.0

            # --- Payment Rate ---
            total_billed = self.env['account.move'].search_count([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('company_id', '=', company.id),
            ])
            paid_bills = self.env['account.move'].search_count([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('paid', 'in_payment')),
                ('invoice_date', '>=', date_from),
                ('invoice_date', '<=', date_to),
                ('company_id', '=', company.id),
            ])
            rec.payment_rate = (paid_bills / total_billed * 100) if total_billed else 0.0

            # --- Overdue ---
            today = date.today()
            overdue_receivables = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', today),
                ('company_id', '=', company.id),
            ])
            rec.total_overdue_receivable = sum(overdue_receivables.mapped('amount_residual'))

            overdue_payables = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', today),
                ('company_id', '=', company.id),
            ])
            rec.total_overdue_payable = sum(overdue_payables.mapped('amount_residual'))

    @api.depends('date_from', 'date_to')
    def _compute_capital_map(self):
        for rec in self:
            company = rec.company_id or self.env.company

            # --- Bank & Cash Balance ---
            bank_journals = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash')),
            ])
            bank_balance = 0.0
            for journal in bank_journals:
                # Get the default debit account for the journal
                if journal.default_account_id:
                    balance = self.env['account.move.line'].read_group(
                        domain=[
                            ('account_id', '=', journal.default_account_id.id),
                            ('parent_state', '=', 'posted'),
                            ('company_id', '=', company.id),
                        ],
                        fields=['balance:sum'],
                        groupby=[],
                    )
                    if balance:
                        bank_balance += balance[0].get('balance', 0.0)
            rec.total_bank_balance = bank_balance

            # --- Customer Receivables (total open) ---
            receivable_accounts = self.env['account.account'].search([
                ('account_type', '=', 'asset_receivable'),
            ])
            if receivable_accounts:
                recv_balance = self.env['account.move.line'].read_group(
                    domain=[
                        ('account_id', 'in', receivable_accounts.ids),
                        ('parent_state', '=', 'posted'),
                        ('reconciled', '=', False),
                        ('company_id', '=', company.id),
                    ],
                    fields=['balance:sum'],
                    groupby=[],
                )
                rec.total_customer_debt = recv_balance[0].get('balance', 0.0) if recv_balance else 0.0
            else:
                rec.total_customer_debt = 0.0

            # --- Vendor Prepaid / Advances (debit balance on payable accounts) ---
            payable_accounts = self.env['account.account'].search([
                ('account_type', '=', 'liability_payable'),
            ])
            if payable_accounts:
                pay_balance = self.env['account.move.line'].read_group(
                    domain=[
                        ('account_id', 'in', payable_accounts.ids),
                        ('parent_state', '=', 'posted'),
                        ('reconciled', '=', False),
                        ('company_id', '=', company.id),
                    ],
                    fields=['balance:sum'],
                    groupby=[],
                )
                raw_balance = pay_balance[0].get('balance', 0.0) if pay_balance else 0.0
                # Payable typically has negative balance. If positive → vendor has prepaid
                rec.total_vendor_prepaid = max(raw_balance, 0.0)
            else:
                rec.total_vendor_prepaid = 0.0

            # --- Total Capital ---
            rec.total_capital = rec.total_bank_balance + rec.total_customer_debt + rec.total_vendor_prepaid

            # --- Percentages ---
            total = rec.total_capital or 1.0
            rec.bank_percentage = (rec.total_bank_balance / total * 100)
            rec.receivable_percentage = (rec.total_customer_debt / total * 100)
            rec.prepaid_percentage = (rec.total_vendor_prepaid / total * 100)

    @api.depends('date_from', 'date_to')
    def _compute_trends(self):
        for rec in self:
            date_from = rec.date_from or date.today().replace(day=1)
            date_to = rec.date_to or date.today()
            company = rec.company_id or self.env.company
            period_days = (date_to - date_from).days or 1

            # Previous period of same length
            prev_from = date_from - timedelta(days=period_days)
            prev_to = date_from - timedelta(days=1)

            # Previous sales
            prev_sales = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', prev_from),
                ('invoice_date', '<=', prev_to),
                ('company_id', '=', company.id),
            ])
            prev_total_sales = sum(prev_sales.mapped('amount_total_signed'))

            if prev_total_sales:
                rec.sales_trend = ((abs(rec.total_sales) - abs(prev_total_sales)) / abs(prev_total_sales)) * 100
            else:
                rec.sales_trend = 100.0 if rec.total_sales else 0.0

            # Previous purchases
            prev_purchases = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', prev_from),
                ('invoice_date', '<=', prev_to),
                ('company_id', '=', company.id),
            ])
            prev_total_purchases = sum(abs(b.amount_total_signed) for b in prev_purchases)

            if prev_total_purchases:
                rec.purchases_trend = ((rec.total_purchases - prev_total_purchases) / prev_total_purchases) * 100
            else:
                rec.purchases_trend = 100.0 if rec.total_purchases else 0.0

            # Receivable status
            if rec.total_overdue_receivable > 0:
                rec.receivable_trend = _('⚠ Overdue: %s') % f"{rec.total_overdue_receivable:,.2f}"
            else:
                rec.receivable_trend = _('✅ No Overdue')

    def _compute_module_stats(self):
        for rec in self:
            # OCR processed (vendor bills created via wizard)
            rec.total_ocr_processed = self.env['account.move'].search_count([
                ('move_type', 'in', ('in_invoice', 'out_invoice')),
                ('state', '=', 'posted'),
            ])

            # Partner statements reconciled
            try:
                rec.total_statements_reconciled = self.env['test.ai.vendor.statement'].search_count([
                    ('state', 'in', ('processed', 'reconciled')),
                ])
            except Exception:
                rec.total_statements_reconciled = 0

            # Bank statements
            try:
                rec.total_bank_statements = self.env['test.ai.bank.statement'].search_count([])
            except Exception:
                rec.total_bank_statements = 0

            # Refunds tracked
            try:
                rec.total_refunds_tracked = self.env['test.ai.refund.tracking'].search_count([])
            except Exception:
                rec.total_refunds_tracked = 0

    # ==================== ACTIONS ====================
    def action_refresh(self):
        """Refresh dashboard data by triggering recomputation."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'test.ai.finance.dashboard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_receivables(self):
        """Open list of unpaid customer invoices."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Open Receivables'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
            ],
            'target': 'current',
        }

    def action_open_payables(self):
        """Open list of unpaid vendor bills."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Open Payables'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
            ],
            'target': 'current',
        }

    def action_open_overdue(self):
        """Open overdue receivables."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Overdue Receivables'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', fields.Date.today()),
            ],
            'target': 'current',
        }

    def action_open_bank_journals(self):
        """Open bank/cash journals."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bank & Cash'),
            'res_model': 'account.journal',
            'view_mode': 'list,form',
            'domain': [('type', 'in', ('bank', 'cash'))],
            'target': 'current',
        }

    @api.model
    def action_open_dashboard(self):
        """Open or create the singleton dashboard record."""
        dashboard = self.search([('company_id', '=', self.env.company.id)], limit=1)
        if not dashboard:
            dashboard = self.create({
                'name': 'AI Finance Dashboard',
                'company_id': self.env.company.id,
            })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'test.ai.finance.dashboard',
            'res_id': dashboard.id,
            'view_mode': 'form',
            'target': 'current',
            'flags': {'mode': 'readonly'},
        }

    # ==================== NET CASH COMPUTATION ====================
    @api.depends('date_from', 'date_to')
    def _compute_net_cash(self):
        for rec in self:
            rec.net_cash_position = rec.total_bank_balance - rec.total_payable

    # ==================== AGING ANALYSIS ====================
    @api.depends('date_from', 'date_to')
    def _compute_aging(self):
        today = date.today()
        for rec in self:
            company = rec.company_id or self.env.company
            base_domain = [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('company_id', '=', company.id),
            ]

            # Current (0-30 days)
            inv_current = self.env['account.move'].search(base_domain + [
                '|',
                ('invoice_date_due', '>=', today),
                ('invoice_date_due', '>=', today - timedelta(days=30)),
            ])
            # Filter more precisely in Python
            current_invs = inv_current.filtered(lambda i: not i.invoice_date_due or i.invoice_date_due >= today - timedelta(days=30))
            rec.aging_current = sum(current_invs.mapped('amount_residual'))
            rec.aging_current_count = len(current_invs)

            # 31-60 days
            d60 = today - timedelta(days=60)
            d30 = today - timedelta(days=31)
            inv_31_60 = self.env['account.move'].search(base_domain + [
                ('invoice_date_due', '>=', d60),
                ('invoice_date_due', '<=', d30),
            ])
            rec.aging_30_60 = sum(inv_31_60.mapped('amount_residual'))
            rec.aging_30_60_count = len(inv_31_60)

            # 61-90 days
            d90 = today - timedelta(days=90)
            d61 = today - timedelta(days=61)
            inv_61_90 = self.env['account.move'].search(base_domain + [
                ('invoice_date_due', '>=', d90),
                ('invoice_date_due', '<=', d61),
            ])
            rec.aging_60_90 = sum(inv_61_90.mapped('amount_residual'))
            rec.aging_60_90_count = len(inv_61_90)

            # 90+ days
            inv_over_90 = self.env['account.move'].search(base_domain + [
                ('invoice_date_due', '<', d90),
            ])
            rec.aging_over_90 = sum(inv_over_90.mapped('amount_residual'))
            rec.aging_over_90_count = len(inv_over_90)

    # ==================== SMART ALERTS ====================
    @api.depends('date_from', 'date_to')
    def _compute_alerts(self):
        today = date.today()
        for rec in self:
            alerts = []

            # Overdue receivables alert
            if rec.total_overdue_receivable > 0:
                alerts.append(
                    '<div style="padding:10px 14px; margin-bottom:8px; '
                    'background:rgba(220,53,69,0.15); color:#ff6b6b; '
                    'border-left:4px solid #dc3545; border-radius:6px;">'
                    '<b>⚠ Overdue Receivables:</b> %s invoices with total <b>%s</b> overdue'
                    '</div>' % (
                        rec.aging_over_90_count + rec.aging_60_90_count + rec.aging_30_60_count,
                        '{:,.0f}'.format(rec.total_overdue_receivable)
                    )
                )

            # Critical aging alert (90+ days)
            if rec.aging_over_90 > 0:
                alerts.append(
                    '<div style="padding:10px 14px; margin-bottom:8px; '
                    'background:rgba(255,193,7,0.15); color:#ffc107; '
                    'border-left:4px solid #ffc107; border-radius:6px;">'
                    '<b>🔴 Critical Aging:</b> %d invoices are overdue by 90+ days (%s)'
                    '</div>' % (rec.aging_over_90_count, '{:,.0f}'.format(rec.aging_over_90))
                )

            # Overdue payables alert
            if rec.total_overdue_payable > 0:
                alerts.append(
                    '<div style="padding:10px 14px; margin-bottom:8px; '
                    'background:rgba(13,110,253,0.15); color:#6ea8fe; '
                    'border-left:4px solid #0d6efd; border-radius:6px;">'
                    '<b>📋 Overdue Bills:</b> Vendor bills totaling <b>%s</b> are past due'
                    '</div>' % '{:,.0f}'.format(rec.total_overdue_payable)
                )

            # Negative cash position
            if rec.net_cash_position < 0:
                alerts.append(
                    '<div style="padding:10px 14px; margin-bottom:8px; '
                    'background:rgba(220,53,69,0.15); color:#ff6b6b; '
                    'border-left:4px solid #dc3545; border-radius:6px;">'
                    '<b>💰 Negative Cash Position:</b> Bank balance is insufficient to cover payables'
                    '</div>'
                )

            # All good
            if not alerts:
                alerts.append(
                    '<div style="padding:10px 14px; margin-bottom:8px; '
                    'background:rgba(40,167,69,0.15); color:#51cf66; '
                    'border-left:4px solid #28a745; border-radius:6px;">'
                    '<b>✅ All Clear:</b> No critical alerts at this time'
                    '</div>'
                )

            rec.alert_html = ''.join(alerts)

    # ==================== TOP 5 OVERDUE PARTNERS ====================
    @api.depends('date_from', 'date_to')
    def _compute_top_overdue(self):
        today = date.today()
        for rec in self:
            company = rec.company_id or self.env.company
            overdue_invoices = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', today),
                ('company_id', '=', company.id),
            ])

            # Group by partner
            partner_totals = {}
            for inv in overdue_invoices:
                pid = inv.partner_id.id
                if pid not in partner_totals:
                    partner_totals[pid] = {
                        'name': inv.partner_id.name,
                        'amount': 0.0,
                        'count': 0,
                    }
                partner_totals[pid]['amount'] += inv.amount_residual
                partner_totals[pid]['count'] += 1

            # Sort by amount desc, take top 5
            sorted_partners = sorted(partner_totals.values(), key=lambda x: x['amount'], reverse=True)[:5]

            if not sorted_partners:
                rec.top_overdue_html = (
                    '<div style="padding:12px; text-align:center; color:#6c757d;">'
                    '<i>✅ No overdue partners</i></div>'
                )
                continue

            rows = []
            for i, p in enumerate(sorted_partners, 1):
                color = '#dc3545' if p['amount'] > 50000 else '#ffc107' if p['amount'] > 10000 else '#6c757d'
                rows.append(
                    '<tr>'
                    '<td style="padding:6px 8px;">%d</td>'
                    '<td style="padding:6px 8px;"><b>%s</b></td>'
                    '<td style="padding:6px 8px; text-align:center;">%d</td>'
                    '<td style="padding:6px 8px; text-align:right; color:%s; font-weight:bold;">%s</td>'
                    '</tr>' % (i, p['name'], p['count'], color, '{:,.0f}'.format(p['amount']))
                )

            rec.top_overdue_html = (
                '<table style="width:100%%; border-collapse:collapse;">'
                '<thead><tr style="border-bottom:2px solid #dee2e6;">'
                '<th style="padding:6px 8px; width:30px;">#</th>'
                '<th style="padding:6px 8px;">Partner</th>'
                '<th style="padding:6px 8px; text-align:center;">Invoices</th>'
                '<th style="padding:6px 8px; text-align:right;">Overdue Amount</th>'
                '</tr></thead>'
                '<tbody>%s</tbody></table>' % ''.join(rows)
            )

    # ==================== QUICK PERIOD BUTTONS ====================
    def action_period_this_month(self):
        """Set filter to current month."""
        today = date.today()
        self.date_from = today.replace(day=1)
        self.date_to = today
        return self.action_refresh()

    def action_period_last_month(self):
        """Set filter to last month."""
        today = date.today()
        first_of_this = today.replace(day=1)
        last_month_end = first_of_this - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        self.date_from = last_month_start
        self.date_to = last_month_end
        return self.action_refresh()

    def action_period_this_quarter(self):
        """Set filter to current quarter."""
        today = date.today()
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        self.date_from = today.replace(month=quarter_month, day=1)
        self.date_to = today
        return self.action_refresh()

    def action_period_this_year(self):
        """Set filter to current year."""
        today = date.today()
        self.date_from = today.replace(month=1, day=1)
        self.date_to = today
        return self.action_refresh()

    def action_open_aging(self):
        """Open overdue invoices grouped by age."""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Aging Analysis'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ('not_paid', 'partial')),
                ('invoice_date_due', '<', fields.Date.today()),
            ],
            'target': 'current',
        }

    # ==================== OWL DASHBOARD DATA ====================
    @api.model
    def get_dashboard_data(self, **kwargs):
        """Return all data needed by the OWL Analytics Dashboard with optional filters."""
        company = self.env.company
        today = date.today()

        # --- Base Filters ---
        partner_id = kwargs.get('partner_id')
        journal_id = kwargs.get('journal_id')
        period = kwargs.get('period', 'this_year')

        base_domain = [('company_id', '=', company.id)]
        if partner_id:
            base_domain.append(('partner_id', '=', partner_id))
        if journal_id:
            base_domain.append(('journal_id', '=', journal_id))

        if period == 'this_month':
            start_date = today.replace(day=1)
            end_date = today
        elif period == 'last_month':
            end_date = today.replace(day=1) - timedelta(days=1)
            start_date = end_date.replace(day=1)
        elif period == 'this_quarter':
            q_month = ((today.month - 1) // 3) * 3 + 1
            start_date = today.replace(month=q_month, day=1)
            end_date = today
        elif period == 'this_year':
            start_date = today.replace(month=1, day=1)
            end_date = today
        else:
            start_date = False
            end_date = False

        if start_date and end_date:
            date_domain = [('invoice_date', '>=', start_date), ('invoice_date', '<=', end_date)]
            due_date_domain = [('invoice_date_due', '>=', start_date), ('invoice_date_due', '<=', end_date)]
        else:
            date_domain = []
            due_date_domain = []

        dashboard = self.search([('company_id', '=', company.id)], limit=1)
        if not dashboard:
            dashboard = self.create({'name': 'AI Finance Dashboard', 'company_id': company.id})

        # Force recomputation for base dashboard KPIs (Note: these are global, un-filtered KPIs)
        # For a truly filtered KPI experience, we compute them manually below based on the domain.
        
        filtered_out_invs = self.env['account.move'].search(base_domain + date_domain + [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')])
        filtered_in_invs = self.env['account.move'].search(base_domain + date_domain + [('move_type', '=', 'in_invoice'), ('state', '=', 'posted')])
        
        total_sales = sum(filtered_out_invs.mapped('amount_total_signed'))
        total_purchases = sum(abs(v) for v in filtered_in_invs.mapped('amount_total_signed'))
        
        # Receivables & Payables (Filtered)
        unpaid_out = filtered_out_invs.filtered(lambda m: m.payment_state in ('not_paid', 'partial'))
        unpaid_in = filtered_in_invs.filtered(lambda m: m.payment_state in ('not_paid', 'partial'))
        
        total_receivable = sum(unpaid_out.mapped('amount_residual'))
        total_payable = sum(unpaid_in.mapped('amount_residual'))
        total_overdue_receivable = sum(unpaid_out.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today).mapped('amount_residual'))
        total_overdue_payable = sum(unpaid_in.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today).mapped('amount_residual'))

        # --- 6-Month Chart Data (Sales vs Purchases) ---
        months, sales_data, purchases_data, profit_data = [], [], [], []
        for i in range(5, -1, -1):
            month_start = (today.replace(day=1) - timedelta(days=i * 30)).replace(day=1)
            next_m = month_start.replace(day=28) + timedelta(days=4)
            month_end = next_m - timedelta(days=next_m.day)
            months.append(month_start.strftime('%b %Y'))

            m_domain = base_domain + [('invoice_date', '>=', month_start), ('invoice_date', '<=', month_end)]
            sales = self.env['account.move'].search(m_domain + [('move_type', '=', 'out_invoice'), ('state', '=', 'posted')])
            s = sum(sales.mapped('amount_total_signed'))
            sales_data.append(s)

            purchases = self.env['account.move'].search(m_domain + [('move_type', '=', 'in_invoice'), ('state', '=', 'posted')])
            p = sum(abs(b.amount_total_signed) for b in purchases)
            purchases_data.append(p)
            profit_data.append(s - p)

        charts = {'labels': months, 'sales': sales_data, 'purchases': purchases_data, 'profit': profit_data}

        # --- Top 5 Customers by Revenue ---
        cust_totals = {}
        for inv in filtered_out_invs:
            pid = inv.partner_id.id
            if pid not in cust_totals:
                cust_totals[pid] = {'name': inv.partner_id.name or 'Unknown', 'amount': 0.0}
            cust_totals[pid]['amount'] += inv.amount_total_signed
        top_customers = sorted(cust_totals.values(), key=lambda x: x['amount'], reverse=True)[:5]

        # --- Top 5 Overdue Customers ---
        overdue_totals = {}
        for inv in unpaid_out.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today):
            pid = inv.partner_id.id
            if pid not in overdue_totals:
                overdue_totals[pid] = {'name': inv.partner_id.name or 'Unknown', 'amount': 0.0, 'count': 0}
            overdue_totals[pid]['amount'] += inv.amount_residual
            overdue_totals[pid]['count'] += 1
        top_overdue = sorted(overdue_totals.values(), key=lambda x: x['amount'], reverse=True)[:5]

        # --- Top 5 Vendors by Spend ---
        vendor_totals = {}
        for bill in filtered_in_invs:
            pid = bill.partner_id.id
            if pid not in vendor_totals:
                vendor_totals[pid] = {'name': bill.partner_id.name or 'Unknown', 'amount': 0.0}
            vendor_totals[pid]['amount'] += abs(bill.amount_total_signed)
        top_vendors = sorted(vendor_totals.values(), key=lambda x: x['amount'], reverse=True)[:5]

        # --- Cash Flow Forecast ---
        bank_domain = [('company_id', '=', company.id)]
        if journal_id: bank_domain.append(('id', '=', journal_id))
        journals = self.env['account.journal'].search(bank_domain + [('type', 'in', ('bank', 'cash'))])
        bank_bal = sum(journals.mapped('default_account_id.current_balance'))

        get_cash = lambda state, d1, d2: sum(self.env['account.move'].search(base_domain + [
            ('move_type', '=', state), ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial')),
            ('invoice_date_due', '>=', d1), ('invoice_date_due', '<=', d2)
        ]).mapped('amount_residual'))

        e_30 = get_cash('out_invoice', today, today + timedelta(days=30))
        e_60 = e_30 + get_cash('out_invoice', today + timedelta(days=31), today + timedelta(days=60))
        e_90 = e_60 + get_cash('out_invoice', today + timedelta(days=61), today + timedelta(days=90))

        p_30 = abs(get_cash('in_invoice', today, today + timedelta(days=30)))
        p_60 = p_30 + abs(get_cash('in_invoice', today + timedelta(days=31), today + timedelta(days=60)))
        p_90 = p_60 + abs(get_cash('in_invoice', today + timedelta(days=61), today + timedelta(days=90)))

        cash_flow = {
            'current_bank': bank_bal,
            'forecast_30': bank_bal + e_30 - p_30,
            'forecast_60': bank_bal + e_60 - p_60,
            'forecast_90': bank_bal + e_90 - p_90,
            'collections_30': e_30,
            'payments_30': p_30,
        }

        # --- Aging data for stacked bar (Manually Filtered) ---
        a_cur = sum(unpaid_out.filtered(lambda m: not m.invoice_date_due or m.invoice_date_due >= today).mapped('amount_residual'))
        a_30 = sum(unpaid_out.filtered(lambda m: m.invoice_date_due and today - timedelta(days=30) <= m.invoice_date_due < today).mapped('amount_residual'))
        a_60 = sum(unpaid_out.filtered(lambda m: m.invoice_date_due and today - timedelta(days=60) <= m.invoice_date_due < today - timedelta(days=30)).mapped('amount_residual'))
        a_90 = sum(unpaid_out.filtered(lambda m: m.invoice_date_due and m.invoice_date_due < today - timedelta(days=60)).mapped('amount_residual'))
        
        aging = {'receivable': {'current': a_cur, 'days_30_60': a_30, 'days_60_90': a_60, 'over_90': a_90}}

        # --- Alerts ---
        alert_list = []
        if total_overdue_receivable > 0:
            alert_list.append({'type': 'danger', 'icon': '⚠', 'text': 'Overdue invoices totaling %s' % '{:,.0f}'.format(total_overdue_receivable)})
        if bank_bal - total_payable < 0:
            alert_list.append({'type': 'danger', 'icon': '💰', 'text': 'Negative cash position — bank insufficient to cover payables'})
        if not alert_list:
            alert_list.append({'type': 'success', 'icon': '✅', 'text': 'All clear — no critical alerts'})

        return {
            'currency_symbol': company.currency_id.symbol or '$',
            'kpis': {
                'total_sales': total_sales,
                'total_purchases': total_purchases,
                'gross_profit': total_sales - total_purchases,
                'profit_margin': ((total_sales - total_purchases) / total_sales * 100) if total_sales else 0.0,
                'total_receivable': total_receivable,
                'total_payable': total_payable,
                'collection_rate': ((total_sales - total_receivable) / total_sales * 100) if total_sales > 0 else 0,
                'payment_rate': ((total_purchases - total_payable) / total_purchases * 100) if total_purchases > 0 else 0,
                'total_overdue_receivable': total_overdue_receivable,
                'total_overdue_payable': total_overdue_payable,
                'net_cash_position': bank_bal - total_payable,
            },
            'capital_map': {
                'bank': bank_bal,
                'receivable': total_receivable,
                'prepaid': sum(unpaid_in.filtered(lambda m: m.amount_residual < 0).mapped('amount_residual')), # Rough approximation
                'total': bank_bal + total_receivable,
            },
            'trends': { 'sales_trend': dashboard.sales_trend, 'purchases_trend': dashboard.purchases_trend },
            'stats': { 'ocr_processed': dashboard.total_ocr_processed, 'reconciled': dashboard.total_statements_reconciled },
            'charts': charts,
            'aging': aging,
            'top_customers': top_customers,
            'top_overdue': top_overdue,
            'top_vendors': top_vendors,
            'cash_flow': cash_flow,
            'alerts': alert_list,
        }

