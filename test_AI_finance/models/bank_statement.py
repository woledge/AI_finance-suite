# -*- coding: utf-8 -*-
"""
Bank Statement Reconciliation
==============================

Compare uploaded bank statements against Odoo's bank journal entries.
Matching uses amount + date (no reference codes).
Ambiguous matches (same amount+date) are flagged for manual user correction.
"""

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class BankStatement(models.Model):
    _name = 'test.ai.bank.statement'
    _description = 'Bank Statement Reconciliation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    bank_account_id = fields.Many2one(
        'account.account', string='Bank Account', required=True,
        help='Select the Odoo bank account (e.g. 101401 Bank) to compare this statement against.',
        tracking=True,
    )
    bank_name = fields.Char(string='Bank Name', help='OCR-extracted bank name')
    account_number = fields.Char(string='Account Number', help='OCR-extracted account number')

    # Period
    date_from = fields.Date(string='Period From', required=True)
    date_to = fields.Date(string='Period To', required=True)

    # Balances
    opening_balance = fields.Monetary(string='Opening Balance', currency_field='currency_id')
    closing_balance = fields.Monetary(string='Closing Balance', currency_field='currency_id')
    odoo_balance = fields.Monetary(
        string='Odoo Balance', currency_field='currency_id',
        compute='_compute_odoo_balance', store=True,
    )
    difference = fields.Monetary(
        string='Difference', currency_field='currency_id',
        compute='_compute_difference', store=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
    )

    # Lines
    line_ids = fields.One2many('test.ai.bank.statement.line', 'statement_id', string='Statement Lines')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('reconciled', 'Reconciled'),
    ], string='Status', default='draft', tracking=True)

    ocr_raw_text = fields.Text(string='OCR Raw Data')

    # ==================== SUMMARY FIELDS ====================
    summary_total_lines = fields.Integer(string='Total Lines', compute='_compute_summary', store=False)
    summary_matched = fields.Integer(string='Matched', compute='_compute_summary', store=False)
    summary_discrepancy = fields.Integer(string='Discrepancies', compute='_compute_summary', store=False)
    summary_missing_odoo = fields.Integer(string='Missing in Odoo', compute='_compute_summary', store=False)
    summary_missing_bank = fields.Integer(string='Missing in Bank', compute='_compute_summary', store=False)
    summary_unresolved = fields.Integer(string='Unresolved', compute='_compute_summary', store=False)
    summary_match_rate = fields.Float(string='Match Rate (%)', compute='_compute_summary', store=False)

    @api.depends('line_ids.match_status')
    def _compute_summary(self):
        for rec in self:
            lines = rec.line_ids
            total = len(lines)
            matched = len(lines.filtered(lambda l: l.match_status == 'matched'))
            discrepancy = len(lines.filtered(lambda l: l.match_status == 'discrepancy'))
            missing_odoo = len(lines.filtered(lambda l: l.match_status == 'missing_in_odoo'))
            missing_bank = len(lines.filtered(lambda l: l.match_status == 'missing_in_bank'))
            unresolved = len(lines.filtered(
                lambda l: l.match_status in ('unmatched', 'ambiguous')
            ))
            rec.summary_total_lines = total
            rec.summary_matched = matched
            rec.summary_discrepancy = discrepancy
            rec.summary_missing_odoo = missing_odoo
            rec.summary_missing_bank = missing_bank
            rec.summary_unresolved = unresolved
            rec.summary_match_rate = round((matched / total * 100) if total else 0, 1)

    # ==================== SEQUENCE ====================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('test.ai.bank.statement') or 'New'
        return super().create(vals_list)

    # ==================== COMPUTED FIELDS ====================

    @api.depends('line_ids.matched_move_line_id', 'line_ids.match_status')
    def _compute_odoo_balance(self):
        for rec in self:
            # Sum debit - credit of all matched Odoo journal items
            total = 0.0
            for line in rec.line_ids:
                if line.matched_move_line_id:
                    total += line.matched_move_line_id.debit - line.matched_move_line_id.credit
            rec.odoo_balance = rec.opening_balance + total

    @api.depends('closing_balance', 'odoo_balance')
    def _compute_difference(self):
        for rec in self:
            rec.difference = rec.closing_balance - rec.odoo_balance

    # ==================== CORE MATCHING LOGIC ====================

    def action_match_lines(self):
        """
        Match bank statement lines against Odoo journal items.

        Strategy (no reference codes — amount + date based):
          Priority 1: EXACT amount + EXACT date
          Priority 2: EXACT amount + date within ±3 days
          Priority 3: EXACT amount only (if single candidate)

        Ambiguous matches (multiple same amount+date) are flagged for manual correction.
        """
        self.ensure_one()
        DATE_TOLERANCE = 3  # days

        # ==================== 1. RESET EXISTING MATCHES ====================
        self.line_ids.write({
            'matched_move_line_id': False,
            'candidate_move_line_ids': [(5, 0, 0)],
            'match_status': 'unmatched',
            'match_notes': '',
        })
        # Remove auto-created "missing in bank" lines from previous runs
        self.line_ids.filtered(lambda l: l.is_odoo_only).unlink()

        # ==================== 2. FETCH ODOO BANK ACCOUNT ENTRIES ====================
        domain = [
            ('account_id', '=', self.bank_account_id.id),
            ('parent_state', '=', 'posted'),
        ]
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))

        odoo_lines = self.env['account.move.line'].search(domain)
        _logger.info(f"Bank Statement {self.name}: Found {len(odoo_lines)} Odoo entries "
                     f"for account {self.bank_account_id.name} ({self.date_from} to {self.date_to})")

        matched_odoo_ids = set()
        matched_bank_ids = set()

        # Helper: get net amount for an Odoo line (debit - credit)
        def odoo_net(line):
            return line.debit - line.credit

        # ==================== 3. PRE-SCAN: Identify duplicate bank lines ====================
        # If 2+ bank lines have the same (amount, date), ALL must be flagged ambiguous
        from collections import defaultdict
        bank_amount_date_groups = defaultdict(list)
        for bline in self.line_ids:
            bank_amount = (bline.credit or 0) - (bline.debit or 0)
            key = (round(bank_amount, 2), bline.date)
            bank_amount_date_groups[key].append(bline)

        # Set of bank line IDs that have duplicates (same amount+date)
        duplicate_bank_ids = set()
        for key, blines in bank_amount_date_groups.items():
            if len(blines) >= 2:
                for bl in blines:
                    duplicate_bank_ids.add(bl.id)

        # ==================== 4. PRIORITY 1: EXACT AMOUNT + EXACT DATE (unique only) ====================
        for bline in self.line_ids:
            if bline.id in matched_bank_ids:
                continue
            # Skip bank lines that have duplicates — they go to the ambiguous handler
            if bline.id in duplicate_bank_ids:
                continue

            bank_amount = (bline.credit or 0) - (bline.debit or 0)  # net from bank's perspective
            bank_date = bline.date

            candidates = []
            for ol in odoo_lines:
                if ol.id in matched_odoo_ids:
                    continue
                if abs(odoo_net(ol) - bank_amount) < 0.01 and ol.date == bank_date:
                    candidates.append(ol)

            if len(candidates) == 1:
                # Clear unique match
                bline.write({
                    'matched_move_line_id': candidates[0].id,
                    'candidate_move_line_ids': [(6, 0, [candidates[0].id])],
                    'match_status': 'matched',
                    'match_notes': f'Exact match: amount + date ({bank_date})',
                })
                matched_odoo_ids.add(candidates[0].id)
                matched_bank_ids.add(bline.id)

        # ==================== 5. AMBIGUOUS: Duplicate bank lines (same amount + date) ====================
        for (amt, dt), blines in bank_amount_date_groups.items():
            if len(blines) < 2:
                continue
            # Skip if already matched
            blines = [bl for bl in blines if bl.id not in matched_bank_ids]
            if not blines:
                continue

            # Find all unmatched Odoo lines with same amount (exact date OR ±3 days)
            candidates = [
                ol for ol in odoo_lines
                if ol.id not in matched_odoo_ids
                and abs(odoo_net(ol) - amt) < 0.01
                and (ol.date == dt or (dt and abs((ol.date - dt).days) <= DATE_TOLERANCE))
            ]

            # ALL duplicate bank lines are marked ambiguous — user decides which to match
            all_candidate_ids = [c.id for c in candidates]
            for i, bline in enumerate(blines):
                vals = {
                    'candidate_move_line_ids': [(6, 0, all_candidate_ids)] if all_candidate_ids else [(5,)],
                    'match_status': 'ambiguous',
                    'match_notes': (f'Ambiguous: {len(blines)} bank lines with same amount '
                                    f'({amt}) on {dt}. {len(candidates)} Odoo candidate(s). '
                                    f'Please select the correct match and confirm.'),
                }
                # Tentatively assign Odoo candidates round-robin, but user can change
                if i < len(candidates):
                    vals['matched_move_line_id'] = candidates[i].id
                    matched_odoo_ids.add(candidates[i].id)
                bline.write(vals)
                matched_bank_ids.add(bline.id)

        # ==================== 4. PRIORITY 2: EXACT AMOUNT + DATE ±3 DAYS ====================
        for bline in self.line_ids:
            if bline.id in matched_bank_ids:
                continue
            bank_amount = (bline.credit or 0) - (bline.debit or 0)
            bank_date = bline.date
            if not bank_date:
                continue

            candidates = []
            for ol in odoo_lines:
                if ol.id in matched_odoo_ids:
                    continue
                if abs(odoo_net(ol) - bank_amount) < 0.01:
                    date_diff = abs((ol.date - bank_date).days)
                    if date_diff <= DATE_TOLERANCE:
                        candidates.append((ol, date_diff))

            if candidates:
                # Sort by closest date
                candidates.sort(key=lambda x: x[1])
                best = candidates[0][0]
                all_candidate_ids = [c[0].id for c in candidates]

                if len(candidates) == 1:
                    status = 'matched'
                    note = f'Matched: amount + date offset ({candidates[0][1]} days)'
                else:
                    status = 'ambiguous'
                    note = (f'Ambiguous: {len(candidates)} candidates within ±{DATE_TOLERANCE} days. '
                            f'Assigned closest date. Verify manually.')

                bline.write({
                    'matched_move_line_id': best.id,
                    'candidate_move_line_ids': [(6, 0, all_candidate_ids)],
                    'match_status': status,
                    'match_notes': note,
                })
                matched_odoo_ids.add(best.id)
                matched_bank_ids.add(bline.id)

        # ==================== 5. PRIORITY 3: EXACT AMOUNT ONLY ====================
        for bline in self.line_ids:
            if bline.id in matched_bank_ids:
                continue
            bank_amount = (bline.credit or 0) - (bline.debit or 0)

            candidates = [
                ol for ol in odoo_lines
                if ol.id not in matched_odoo_ids
                and abs(odoo_net(ol) - bank_amount) < 0.01
            ]

            if len(candidates) == 1:
                bline.write({
                    'matched_move_line_id': candidates[0].id,
                    'candidate_move_line_ids': [(6, 0, [candidates[0].id])],
                    'match_status': 'matched',
                    'match_notes': 'Matched: amount only (dates differ)',
                })
                matched_odoo_ids.add(candidates[0].id)
                matched_bank_ids.add(bline.id)
            elif len(candidates) > 1:
                # Multiple candidates — assign first but flag as ambiguous
                bline.write({
                    'matched_move_line_id': candidates[0].id,
                    'candidate_move_line_ids': [(6, 0, [c.id for c in candidates])],
                    'match_status': 'ambiguous',
                    'match_notes': (f'Ambiguous: {len(candidates)} Odoo entries with same amount '
                                    f'({bank_amount}). Verify manually.'),
                })
                matched_odoo_ids.add(candidates[0].id)
                matched_bank_ids.add(bline.id)

        # ==================== 6. MARK UNMATCHED BANK LINES ====================
        for bline in self.line_ids:
            if bline.id not in matched_bank_ids and not bline.is_odoo_only:
                bline.write({
                    'match_status': 'missing_in_odoo',
                    'match_notes': 'No matching entry found in Odoo bank journal.',
                })

        # ==================== 7. MISSING IN BANK (Odoo lines not matched) ====================
        unmatched_odoo = odoo_lines.filtered(lambda l: l.id not in matched_odoo_ids)
        for ol in unmatched_odoo:
            self.env['test.ai.bank.statement.line'].create({
                'statement_id': self.id,
                'date': ol.date,
                'description': ol.name or ol.ref or ol.move_name or 'Unknown',
                'debit': ol.credit,  # Reverse: Odoo credit = bank debit
                'credit': ol.debit,  # Reverse: Odoo debit = bank credit
                'balance': 0,
                'is_odoo_only': True,
                'matched_move_line_id': ol.id,
                'match_status': 'missing_in_bank',
                'match_notes': f'Found in Odoo ({ol.move_name}) but not in bank statement.',
            })

        self.state = 'processed'

        # Summary
        total = len(self.line_ids)
        matched = len(self.line_ids.filtered(lambda l: l.match_status == 'matched'))
        ambiguous = len(self.line_ids.filtered(lambda l: l.match_status == 'ambiguous'))
        missing_odoo = len(self.line_ids.filtered(lambda l: l.match_status == 'missing_in_odoo'))
        missing_bank = len(self.line_ids.filtered(lambda l: l.match_status == 'missing_in_bank'))
        _logger.info(f"Bank Statement {self.name}: {matched} matched, {ambiguous} ambiguous, "
                     f"{missing_odoo} missing in Odoo, {missing_bank} missing in bank")
        return True

    def action_confirm_matches(self):
        """Confirm matches — validate no double-matching, relabel unmatched ambiguous lines."""
        self.ensure_one()
        ambiguous_lines = self.line_ids.filtered(lambda l: l.match_status == 'ambiguous')

        # ---- Validation: prevent same Odoo line assigned to multiple bank lines ----
        all_matched_lines = self.line_ids.filtered(
            lambda l: l.matched_move_line_id and l.match_status in ('matched', 'ambiguous')
        )
        seen_odoo_ids = {}  # odoo_line_id -> bank_line description
        for line in all_matched_lines:
            odoo_id = line.matched_move_line_id.id
            if odoo_id in seen_odoo_ids:
                raise ValidationError(
                    f'Duplicate match detected!\n\n'
                    f'Odoo entry "{line.matched_move_line_id.display_name}" is assigned to '
                    f'both:\n  • {seen_odoo_ids[odoo_id]}\n  • {line.description}\n\n'
                    f'Please correct before confirming.'
                )
            seen_odoo_ids[odoo_id] = line.description

        # ---- Confirm ambiguous lines with a match ----
        for line in ambiguous_lines:
            if line.matched_move_line_id:
                line.write({
                    'match_status': 'matched',
                    'match_notes': f'Confirmed by user. {line.match_notes}',
                })
            else:
                # No Odoo match selected → mark as missing in Odoo
                line.write({
                    'match_status': 'missing_in_odoo',
                    'match_notes': 'No Odoo match selected during confirmation. Missing in Odoo.',
                })

        # Check if all lines are now resolved
        all_resolved = all(
            l.match_status in ('matched', 'missing_in_odoo', 'missing_in_bank')
            for l in self.line_ids
        )
        if all_resolved:
            self.state = 'reconciled'
        return True

    def action_rematch(self):
        """Clear all matches and re-run matching."""
        self.ensure_one()
        self.state = 'draft'
        return self.action_match_lines()

    def action_print_report(self):
        """Print the reconciliation PDF report."""
        return self.env.ref('test_AI_finance.action_report_bank_statement').report_action(self)


class BankStatementLine(models.Model):
    _name = 'test.ai.bank.statement.line'
    _description = 'Bank Statement Line'
    _order = 'date, id'

    statement_id = fields.Many2one('test.ai.bank.statement', string='Statement', ondelete='cascade')

    # Statement data (from OCR)
    date = fields.Date(string='Date')
    description = fields.Char(string='Description')
    debit = fields.Float(string='Debit', digits=(16, 2))
    credit = fields.Float(string='Credit', digits=(16, 2))
    balance = fields.Float(string='Balance', digits=(16, 2), help='Running balance from statement')

    # Flag for lines auto-created from unmatched Odoo entries
    is_odoo_only = fields.Boolean(string='Odoo Only', default=False,
                                  help='True if this line was created from an unmatched Odoo entry')

    # Match data
    matched_move_line_id = fields.Many2one(
        'account.move.line', string='Matched Odoo Item',
        help='The Odoo journal entry matched to this bank line. Editable for manual correction.',
    )
    candidate_move_line_ids = fields.Many2many(
        'account.move.line',
        'bank_stmt_line_candidate_rel',
        'bank_stmt_line_id',
        'move_line_id',
        string='Candidate Matches',
        help='All possible Odoo matches for this line (for dropdown selection).',
    )
    matched_partner_id = fields.Many2one(
        'res.partner', related='matched_move_line_id.partner_id',
        string='Partner', readonly=True,
    )
    currency_id = fields.Many2one('res.currency', related='statement_id.currency_id')

    match_status = fields.Selection([
        ('unmatched', 'Unmatched'),
        ('matched', 'Fully Matched'),
        ('ambiguous', 'Ambiguous Match'),
        ('missing_in_odoo', 'Missing in Odoo'),
        ('missing_in_bank', 'Missing in Bank'),
    ], string='Match Status', default='unmatched')

    match_notes = fields.Char(string='Notes')
