# -*- coding: utf-8 -*-
"""
Account Bank Statement Fix
===========================

Adds the missing 'journal_has_invalid_statements' field to account.bank.statement.
This field is referenced in the Enterprise account_accountant module's view
(bank_rec_widget_views.xml) but not defined in the model.

This fix allows the account_accountant (Accounting) module to install correctly.
On Odoo.sh where the field may already exist, this simply overrides with the same logic.
"""

from odoo import models, fields, api


class AccountBankStatementFix(models.Model):
    _inherit = 'account.bank.statement'

    journal_has_invalid_statements = fields.Boolean(
        string='Journal Has Invalid Statements',
        compute='_compute_journal_has_invalid_statements',
    )

    @api.depends('journal_id', 'is_valid')
    def _compute_journal_has_invalid_statements(self):
        for statement in self:
            if statement.journal_id:
                invalid_count = self.search_count([
                    ('journal_id', '=', statement.journal_id.id),
                    ('is_valid', '=', False),
                ], limit=1)
                statement.journal_has_invalid_statements = invalid_count > 0
            else:
                statement.journal_has_invalid_statements = False
