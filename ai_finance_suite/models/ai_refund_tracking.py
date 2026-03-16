# -*- coding: utf-8 -*-
"""
AI Refund Tracking Model
========================

Tracks refunds/cancelled tickets from vendors until Credit Note is received.
Ensures no money is lost by monitoring refund status.
"""

import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AIRefundTracking(models.Model):
    _name = 'af.refund.tracking'
    _description = 'Refund Tracking'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'ticket_number'

    # ==================== IDENTIFICATION ====================
    ticket_number = fields.Char(
        string='Ticket/Reference Number',
        required=True,
        tracking=True,
        help='Ticket number or booking reference for the cancelled item'
    )
    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True
    )
    
    # ==================== VENDOR & AMOUNTS ====================
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        tracking=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    refund_amount = fields.Monetary(
        string='Expected Refund Amount',
        currency_field='currency_id',
        tracking=True
    )
    
    # ==================== STATUS ====================
    state = fields.Selection([
        ('pending', 'Pending Cancellation'),
        ('requested', 'Refund Requested'),
        ('approved', 'Approved by Vendor'),
        ('credited', 'Credit Note Received'),
        ('closed', 'Closed'),
    ], string='Status', default='pending', tracking=True)
    
    # ==================== DATES ====================
    request_date = fields.Date(
        string='Request Date',
        default=fields.Date.today,
        tracking=True
    )
    expected_credit_date = fields.Date(
        string='Expected Credit Date',
        help='When we expect to receive the credit note'
    )
    credit_received_date = fields.Date(
        string='Credit Received Date',
        help='Actual date credit note was received'
    )
    
    # ==================== DETAILS ====================
    passenger_name = fields.Char(string='Passenger Name')
    flight_details = fields.Char(string='Flight/Booking Details')
    refund_reason = fields.Text(string='Reason for Refund')
    notes = fields.Text(string='Internal Notes')
    
    # ==================== LINKED RECORDS ====================
    original_bill_id = fields.Many2one(
        'account.move',
        string='Original Vendor Bill',
        domain=[('move_type', '=', 'in_invoice')],
        help='The original vendor bill for this booking'
    )
    credit_note_id = fields.Many2one(
        'account.move',
        string='Credit Note',
        domain=[('move_type', '=', 'in_refund')],
        help='The credit note received from vendor'
    )
    
    # ==================== OCR DATA ====================
    ocr_document = fields.Binary(string='OCR Document')
    ocr_filename = fields.Char(string='OCR Filename')
    raw_ocr_data = fields.Text(string='Raw OCR Data')
    
    # ==================== COMPUTED FIELDS ====================
    days_pending = fields.Integer(
        string='Days Pending',
        compute='_compute_days_pending'
    )
    
    @api.depends('ticket_number', 'vendor_id')
    def _compute_name(self):
        for record in self:
            vendor_name = record.vendor_id.name if record.vendor_id else 'Unknown'
            record.name = f"Refund: {record.ticket_number or 'New'} - {vendor_name}"
    
    @api.depends('request_date', 'state')
    def _compute_days_pending(self):
        today = fields.Date.today()
        for record in self:
            if record.state in ['pending', 'requested', 'approved'] and record.request_date:
                delta = today - record.request_date
                record.days_pending = delta.days
            else:
                record.days_pending = 0
    
    # ==================== ACTIONS ====================
    def action_request_refund(self):
        """Mark refund as requested from vendor."""
        self.ensure_one()
        self.state = 'requested'
        self.message_post(body=_("Refund request sent to vendor."))
    
    def action_mark_approved(self):
        """Mark refund as approved by vendor."""
        self.ensure_one()
        self.state = 'approved'
        self.message_post(body=_("Refund approved by vendor."))
    
    def action_receive_credit_note(self):
        """Open wizard to create/link credit note."""
        self.ensure_one()
        # For now, just mark as credited
        self.state = 'credited'
        self.credit_received_date = fields.Date.today()
        self.message_post(body=_("Credit note received."))
    
    def action_close(self):
        """Close the refund tracking."""
        self.ensure_one()
        self.state = 'closed'
        self.message_post(body=_("Refund tracking closed."))
    
    # ==================== CONSTRAINTS ====================
    _sql_constraints = [
        ('ticket_vendor_unique', 
         'UNIQUE(ticket_number, vendor_id)', 
         'A refund tracking with this ticket number already exists for this vendor!')
    ]
    
    @api.constrains('ticket_number')
    def _check_duplicate_ticket(self):
        """Prevent duplicate ticket numbers."""
        for record in self:
            if record.ticket_number:
                duplicate = self.search([
                    ('ticket_number', '=', record.ticket_number),
                    ('vendor_id', '=', record.vendor_id.id),
                    ('id', '!=', record.id)
                ], limit=1)
                if duplicate:
                    raise UserError(_(
                        'A refund tracking for ticket "%s" already exists for vendor "%s".\n'
                        'Existing record: %s'
                    ) % (record.ticket_number, record.vendor_id.name, duplicate.name))
