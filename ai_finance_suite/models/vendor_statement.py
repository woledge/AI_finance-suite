# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class VendorStatement(models.Model):
    _name = 'af.vendor.statement'
    _description = 'Partner Statement Reconciliation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'statement_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string='Partner', required=True, tracking=True,
                                 help='Partner can be a Vendor, Customer, or both.')
    statement_date = fields.Date(string='Statement Date', required=True, default=fields.Date.context_today)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)

    # ==================== PERIOD FIELDS ====================
    date_from = fields.Date(string='Period From', help='Start date of the statement period. '
                            'If set, only Odoo transactions within this period will be compared.')
    date_to = fields.Date(string='Period To', help='End date of the statement period. '
                          'If set, only Odoo transactions within this period will be compared.')

    # ==================== BALANCE FIELDS ====================
    statement_total_due = fields.Monetary(string='Statement Total Due', currency_field='currency_id', tracking=True)
    odoo_total_due = fields.Monetary(string='Odoo Total Due', currency_field='currency_id',
                                     compute='_compute_odoo_total', store=True)
    difference_amount = fields.Monetary(string='Difference', currency_field='currency_id',
                                        compute='_compute_difference', store=True)

    line_ids = fields.One2many('af.vendor.statement.line', 'statement_id', string='Statement Lines')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('reconciled', 'Reconciled'),
    ], string='Status', default='draft', tracking=True)

    ocr_raw_text = fields.Text(string="OCR Raw Text")

    # ==================== COLUMN MATCHING SETTINGS ====================
    statement_column_ids = fields.One2many(
        'af.vendor.statement.column', 'statement_id',
        string='Extracted Columns'
    )
    selected_column_id = fields.Many2one(
        'af.vendor.statement.column',
        string='Match Using Column',
        domain="[('statement_id', '=', id)]",
        help='Select which column from the statement to use for matching against Odoo references. '
             'Change this and click "Reconcile with Partner Ledger" to re-match with a different column.'
    )
    extracted_columns = fields.Char(
        string='Extracted Columns',
        readonly=True,
        help='Column names detected by AI from the uploaded statement (for reference)'
    )
    match_key_column = fields.Selection([
        ('voucher_number', 'Voucher/Ref Code'),
        ('description', 'Description/Ref'),
    ], string='Match Key Column', default='voucher_number',
       help='Internal matching key derived from the selected column.')

    # ==================== SUMMARY FIELDS ====================
    summary_total_lines = fields.Integer(string='Total Lines', compute='_compute_summary', store=False)
    summary_matched = fields.Integer(string='Matched', compute='_compute_summary', store=False)
    summary_discrepancy = fields.Integer(string='Discrepancies', compute='_compute_summary', store=False)
    summary_missing_odoo = fields.Integer(string='Missing in Odoo', compute='_compute_summary', store=False)
    summary_missing_stmt = fields.Integer(string='Missing in Statement', compute='_compute_summary', store=False)
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
            missing_stmt = len(lines.filtered(lambda l: l.match_status == 'missing_in_statement'))
            unresolved = len(lines.filtered(
                lambda l: l.match_status in ('unmatched', 'duplicate', 'unposted', 'currency_mismatch')
            ))
            rec.summary_total_lines = total
            rec.summary_matched = matched
            rec.summary_discrepancy = discrepancy
            rec.summary_missing_odoo = missing_odoo
            rec.summary_missing_stmt = missing_stmt
            rec.summary_unresolved = unresolved
            rec.summary_match_rate = round((matched / total * 100) if total else 0, 1)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('af.vendor.statement') or 'New'
        return super().create(vals_list)

    @api.depends('line_ids.match_status', 'line_ids.odoo_amount_residual')
    def _compute_odoo_total(self):
        for record in self:
            # Sum of signed residual amounts from ALL Odoo-linked lines
            # Includes matched, discrepancy, and missing_in_statement lines
            total = sum(
                line.odoo_amount_residual
                for line in record.line_ids
                if line.matched_move_line_id
            )
            record.odoo_total_due = total

    @api.depends('statement_total_due', 'odoo_total_due', 'partner_id')
    def _compute_difference(self):
        for record in self:
            # Determine logic based on Partner Account Type
            is_vendor = False
            if record.partner_id:
                payable_account = record.partner_id.property_account_payable_id
                if payable_account and payable_account.account_type == 'liability_payable':
                    is_vendor = True

            if is_vendor:
                # Vendor: Statement (Positive liability) + Odoo (Negative credit balance) = 0
                record.difference_amount = record.statement_total_due + record.odoo_total_due
            else:
                # Customer: Statement (Positive) - Odoo (Positive) = 0
                record.difference_amount = record.statement_total_due - record.odoo_total_due

    # ==================== CORE MATCHING LOGIC ====================

    def action_match_lines(self):
        """
        Core Matching Logic (Phase 5 - Enhanced):
        Matches statement lines against Odoo Journal Items (account.move.line)
        for this partner, searching BOTH Payable AND Receivable accounts.

        Matching strategy (in priority order):
        1. Voucher code match: statement voucher_number vs Odoo move.ref
        2. Reference match: check if Odoo move_name or ref appears in statement description
        3. Reverse check: check if statement description appears in Odoo ref or move_name

        Enhanced detection:
        - Duplicate invoices (same ref matched multiple times)
        - Unposted invoices (exist but not posted)
        - Amount differences (balance mismatch)
        """
        self.ensure_one()
        import re

        # Clean up any synthetic lines generated by previous runs
        synthetic_lines = self.line_ids.filtered(lambda l: l.is_odoo_only)
        if synthetic_lines:
            synthetic_lines.unlink()

        # ==================== 1. FETCH ODOO CANDIDATES ====================
        # Search BOTH payable AND receivable accounts for this partner
        domain = [
            ('partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', 'in', ['liability_payable', 'asset_receivable']),
        ]

        # Apply date period filter if available
        if self.date_from:
            domain.append(('date', '>=', self.date_from))
        if self.date_to:
            domain.append(('date', '<=', self.date_to))

        odoo_lines = self.env['account.move.line'].search(domain)

        # Also check for UNPOSTED moves (for detection only — not matching)
        unposted_domain = [
            ('partner_id', 'child_of', self.partner_id.commercial_partner_id.id),
            ('parent_state', '=', 'draft'),
            ('account_id.account_type', 'in', ['liability_payable', 'asset_receivable']),
        ]
        if self.date_from:
            unposted_domain.append(('date', '>=', self.date_from))
        if self.date_to:
            unposted_domain.append(('date', '<=', self.date_to))
        unposted_lines = self.env['account.move.line'].search(unposted_domain)

        # ==================== 2. BUILD LOOKUP DICTIONARIES ====================
        # Key: normalized reference -> list of odoo lines
        candidates_by_ref = {}
        for l in odoo_lines:
            # Index by move_name (e.g. BILL/2026/02/0007)
            if l.move_name:
                key = l.move_name.strip().upper()
                candidates_by_ref.setdefault(key, []).append(l)
            # Index by ref (e.g. SI100 — the voucher code stored from OCR)
            if l.ref:
                key = l.ref.strip().upper()
                candidates_by_ref.setdefault(key, []).append(l)

        # Build similar dict for unposted lines (for detection)
        unposted_by_ref = {}
        for l in unposted_lines:
            if l.move_name:
                unposted_by_ref.setdefault(l.move_name.strip().upper(), []).append(l)
            if l.ref:
                unposted_by_ref.setdefault(l.ref.strip().upper(), []).append(l)

        matched_odoo_line_ids = set()
        matched_vouchers = {}  # Track voucher codes to detect duplicates
        matches_count = 0

        # ==================== 3. MATCH EACH STATEMENT LINE ====================
        # Determine primary match key based on user selection (dropdown)
        if self.selected_column_id:
            selected_name = self.selected_column_id.column_name.strip().lower()
            description_keywords = ['description', 'desc', 'detail', 'details', 'narration', 'particular', 'particulars']
            if any(kw in selected_name for kw in description_keywords):
                self.match_key_column = 'description'
            else:
                self.match_key_column = 'voucher_number'
        use_description_as_key = (self.match_key_column == 'description')

        for line in self.line_ids:
            stmt_amount = line.amount
            stmt_ref = (line.name or '').strip()
            stmt_ref_upper = stmt_ref.upper()
            stmt_voucher = (line.voucher_number or '').strip().upper()

            # Select primary key based on user's column choice
            if use_description_as_key:
                primary_key = stmt_ref_upper
            else:
                primary_key = stmt_voucher

            match = None
            match_method = ''
            all_candidates = []  # Track all candidates for this line

            # ---- Priority 1: Primary Key Match (user-selected column) ----
            if primary_key and not match:
                if primary_key in candidates_by_ref:
                    available = [c for c in candidates_by_ref[primary_key]
                                 if c.id not in matched_odoo_line_ids]
                    all_candidates.extend(available)
                    if available:
                        match = available[0]
                        match_method = f'primary_key:{primary_key}'

            # ---- Priority 2: Reference Token Match ----
            # Extract potential references from statement description
            if not match:
                potential_refs = []
                tokens = re.split(r'[\s\(\)\[\],;]+', stmt_ref)
                for token in tokens:
                    token = token.strip()
                    if token and len(token) > 3:
                        potential_refs.append(token.upper())
                if stmt_ref_upper:
                    potential_refs.append(stmt_ref_upper)

                # Try exact token match against Odoo candidates
                for ref_token in potential_refs:
                    if ref_token in candidates_by_ref:
                        available = [c for c in candidates_by_ref[ref_token]
                                     if c.id not in matched_odoo_line_ids]
                        all_candidates.extend(available)
                        if available:
                            match = available[0]
                            match_method = f'ref_exact:{ref_token}'
                            break

            # ---- Priority 3: Substring Match (Odoo ref inside statement) ----
            if not match:
                for odoo_line in odoo_lines:
                    if odoo_line.id in matched_odoo_line_ids:
                        continue
                    move_name = (odoo_line.move_name or '').strip().upper()
                    ref = (odoo_line.ref or '').strip().upper()

                    if move_name and move_name in stmt_ref_upper:
                        match = odoo_line
                        match_method = f'move_name_in_stmt:{move_name}'
                        break
                    if ref and len(ref) > 3 and ref in stmt_ref_upper:
                        match = odoo_line
                        match_method = f'ref_in_stmt:{ref}'
                        break

            # ---- Priority 4: Reverse Substring (statement ref inside Odoo) ----
            if not match and stmt_ref_upper:
                potential_refs_2 = []
                tokens2 = re.split(r'[\s\(\)\[\],;]+', stmt_ref)
                for token in tokens2:
                    token = token.strip()
                    if token and len(token) >= 5:
                        potential_refs_2.append(token.upper())

                for ref_token in potential_refs_2:
                    for odoo_line in odoo_lines:
                        if odoo_line.id in matched_odoo_line_ids:
                            continue
                        move_name = (odoo_line.move_name or '').strip().upper()
                        ref = (odoo_line.ref or '').strip().upper()
                        if ref_token in move_name or ref_token in ref:
                            match = odoo_line
                            match_method = f'stmt_token_in_odoo:{ref_token}'
                            break
                    if match:
                        break

            # ==================== 4. WRITE MATCH RESULT ====================
            if match:
                matched_odoo_line_ids.add(match.id)

                # Track voucher for duplicate detection
                voucher_key = stmt_voucher or stmt_ref_upper
                if voucher_key:
                    matched_vouchers.setdefault(voucher_key, []).append(line.id)

                # Compare original transaction amount, NOT open balance, for line items
                amount_diff = abs(match.amount_currency) - abs(stmt_amount)

                status = 'matched'
                notes = f"Matched via {match_method}"

                # Check amount mismatch
                if abs(amount_diff) > 0.01:
                    status = 'discrepancy'
                    notes = (f"Amount Mismatch ({match_method}): "
                             f"Odoo transaction is {abs(match.amount_currency)}, "
                             f"Statement says {abs(stmt_amount)}")


                # Deduplicate candidates and include the match itself
                seen_ids = set()
                unique_candidate_ids = []
                for c in all_candidates + [match]:
                    if c.id not in seen_ids:
                        seen_ids.add(c.id)
                        unique_candidate_ids.append(c.id)

                line.write({
                    'matched_move_line_id': match.id,
                    'candidate_move_line_ids': [(6, 0, unique_candidate_ids)],
                    'odoo_amount_residual': match.amount_residual_currency,
                    'match_status': status,
                    'match_notes': notes,
                })
                matches_count += 1

            else:
                # Check if there's an UNPOSTED version of this transaction
                unposted_match = None
                check_keys = [stmt_voucher] if stmt_voucher else []
                check_keys.append(stmt_ref_upper)
                for key in check_keys:
                    if key and key in unposted_by_ref:
                        unposted_match = unposted_by_ref[key][0]
                        break

                if unposted_match:
                    line.write({
                        'match_status': 'unposted',
                        'match_notes': (f"Found UNPOSTED invoice in Odoo: "
                                        f"{unposted_match.move_name or unposted_match.ref}. "
                                        f"Post it first to reconcile."),
                    })
                else:
                    line.write({
                        'match_status': 'missing_in_odoo',
                        'match_notes': 'No matching transaction found in Odoo Partner Ledger',
                    })

        # ==================== 5. DETECT DUPLICATES ====================
        for voucher_key, line_ids in matched_vouchers.items():
            if len(line_ids) > 1:
                for lid in line_ids:
                    dup_line = self.env['af.vendor.statement.line'].browse(lid)
                    if dup_line.exists():
                        dup_line.write({
                            'match_status': 'duplicate',
                            'match_notes': f"DUPLICATE: Voucher '{voucher_key}' appears {len(line_ids)} times in statement",
                        })

        # ==================== 6. MISSING IN STATEMENT ====================
        # Lines in Odoo that match criteria but weren't matched to any statement line
        unmatched_odoo_lines = odoo_lines.filtered(lambda l: l.id not in matched_odoo_line_ids)

        for unmatched in unmatched_odoo_lines:
            self.env['af.vendor.statement.line'].create({
                'statement_id': self.id,
                'name': unmatched.move_name or unmatched.ref or 'Unknown',
                'voucher_number': unmatched.ref or '',
                'date': unmatched.date,
                'amount': 0,
                'odoo_amount_residual': unmatched.amount_residual_currency,
                'matched_move_line_id': unmatched.id,
                'match_status': 'missing_in_statement',
                'is_odoo_only': True,
                'match_notes': (f"Found in Odoo ({unmatched.move_name}) but not in Statement. "
                                f"Balance: {unmatched.amount_residual_currency}"),
            })

        self.state = 'processed'
        return True

    def action_confirm_matches(self):
        """Confirm matches - validate no double-matching, relabel unresolved lines."""
        self.ensure_one()

        # ---- Validation: prevent same Odoo line assigned to multiple statement lines ----
        all_matched_lines = self.line_ids.filtered(
            lambda l: l.matched_move_line_id and l.match_status in ('matched', 'discrepancy', 'duplicate')
        )
        seen_odoo_ids = {}  # odoo_line_id -> statement line description
        for line in all_matched_lines:
            odoo_id = line.matched_move_line_id.id
            if odoo_id in seen_odoo_ids:
                raise ValidationError(
                    f'Duplicate match detected!\n\n'
                    f'Odoo entry "{line.matched_move_line_id.display_name}" is assigned to '
                    f'both:\n  - {seen_odoo_ids[odoo_id]}\n  - {line.name}\n\n'
                    f'Please correct before confirming.'
                )
            seen_odoo_ids[odoo_id] = line.name

        # ---- Confirm resolvable lines ----
        for line in self.line_ids:
            if line.match_status == 'duplicate' and line.matched_move_line_id:
                # User resolved the duplicate - confirm as matched
                line.write({
                    'match_status': 'matched',
                    'match_notes': f'Confirmed by user. {line.match_notes}',
                })
            elif line.match_status == 'duplicate' and not line.matched_move_line_id:
                # Duplicate with no match selected -> missing in Odoo
                line.write({
                    'match_status': 'missing_in_odoo',
                    'match_notes': 'No Odoo match selected during confirmation. Missing in Odoo.',
                })

        # Check if all lines are resolved
        all_resolved = all(
            l.match_status in ('matched', 'discrepancy', 'missing_in_odoo',
                               'missing_in_statement', 'unposted', 'currency_mismatch')
            for l in self.line_ids
        )
        if all_resolved:
            self.state = 'reconciled'
        return True

    def action_rematch(self):
        """Clear all matches and re-run matching."""
        self.ensure_one()
        # Delete synthetic lines
        synthetic_lines = self.line_ids.filtered(lambda l: l.is_odoo_only)
        if synthetic_lines:
            synthetic_lines.unlink()
        else:
            # Fallback for old records created before is_odoo_only was introduced
            missing_lines = self.line_ids.filtered(
                lambda l: l.match_status == 'missing_in_statement' or 
                (l.amount == 0 and l.match_status != 'matched')
            )
            missing_lines.unlink()
        # Reset remaining lines
        for line in self.line_ids:
            line.write({
                'matched_move_line_id': False,
                'candidate_move_line_ids': [(5,)],
                'odoo_amount_residual': 0,
                'match_status': 'unmatched',
                'match_notes': False,
            })
        self.state = 'draft'
        return self.action_match_lines()

    def action_print_report(self):
        """Print the reconciliation PDF report."""
        return self.env.ref('ai_finance_suite.action_report_vendor_statement').report_action(self)


class VendorStatementLine(models.Model):
    _name = 'af.vendor.statement.line'
    _description = 'Partner Statement Line Item'
    _order = 'date, id'

    statement_id = fields.Many2one('af.vendor.statement', string='Statement', ondelete='cascade')

    # Statement Data
    date = fields.Date(string='Date')
    name = fields.Char(string='Description/Ref')
    voucher_number = fields.Char(string='Voucher/Ref Code',
                                 help='Reference code extracted from statement (e.g. SI100, BR200). '
                                      'Used as primary matching key against Odoo move.ref.')
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', related='statement_id.currency_id')

    # Match Data
    matched_move_line_id = fields.Many2one('account.move.line', string='Matched Odoo Item')
    candidate_move_line_ids = fields.Many2many('account.move.line',
                                               'af_vendor_stmt_candidate_rel',
                                               'stmt_line_id', 'move_line_id',
                                               string='Candidate Matches')
    matched_partner_id = fields.Many2one('res.partner', related='matched_move_line_id.partner_id',
                                         string='Odoo Partner', readonly=True)
    odoo_amount_residual = fields.Monetary(string='Odoo Open Balance', currency_field='currency_id')

    match_status = fields.Selection([
        ('unmatched', 'Unmatched'),
        ('matched', 'Fully Matched'),
        ('discrepancy', 'Balance Mismatch'),
        ('missing_in_odoo', 'Missing in Odoo'),
        ('missing_in_statement', 'Missing in Statement'),
        ('duplicate', 'Duplicate Invoice'),
        ('unposted', 'Unposted in Odoo'),
        ('currency_mismatch', 'Currency Mismatch'),
    ], string='Match Status', default='unmatched')

    match_notes = fields.Char(string='Notes')
    is_odoo_only = fields.Boolean(string='Is Odoo Only', default=False)


class VendorStatementColumn(models.Model):
    _name = 'af.vendor.statement.column'
    _description = 'Extracted Column for Statement Matching'
    _rec_name = 'display_label'

    statement_id = fields.Many2one(
        'af.vendor.statement',
        string='Statement',
        required=True,
        ondelete='cascade'
    )
    column_name = fields.Char(string='Column Name', required=True)
    is_recommended = fields.Boolean(string='AI Recommended', default=False)
    display_label = fields.Char(
        string='Display Label',
        compute='_compute_display_label',
        store=True
    )

    @api.depends('column_name', 'is_recommended')
    def _compute_display_label(self):
        for rec in self:
            if rec.is_recommended:
                rec.display_label = f"{rec.column_name} (AI Recommended)"
            else:
                rec.display_label = rec.column_name
