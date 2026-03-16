# -*- coding: utf-8 -*-
"""
OCR Engine Wizard
=================

Unified wizard for OCR-based document processing:
1. Vendor Bills - Create vendor bills from invoice images
2. Refunds - Track refunds/cancelled tickets until Credit Note issued
3. Statements - Match supplier statements with Odoo records

Uses Gemini Vision OCR for intelligent data extraction.
"""

import logging
import base64
import json
import os
import time
from datetime import datetime
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)




class VendorBillWizard(models.TransientModel):
    _name = 'af.vendor.bill.wizard'
    _description = 'OCR Engine Wizard'

    # ==================== DOCUMENT TYPE ====================
    document_type = fields.Selection([
        ('vendor_bill', 'Vendor Bill'),
        ('customer_invoice', 'Customer Invoice'),
        ('refund', 'Refund / Credit Note'),
        ('statement', 'Partner Statement'),
        ('bank_statement', 'Bank Statement'),
    ], string='Document Type', default='vendor_bill')

    # ==================== BANK STATEMENT FIELDS ====================
    bank_account_id = fields.Many2one(
        'account.account', string='Bank Account',
        help='Select the bank account (e.g. 101401 Bank) to compare the statement against.',
    )

    # ==================== OCR EXTRACTED REFERENCE ====================
    reference_code = fields.Char(
        string='Reference/Voucher Code',
        help='Reference code extracted by OCR (e.g. SI100, BR200). '
             'Stored in move.ref for matching with partner statements.'
    )

    # ==================== STATEMENT PERIOD FIELDS ====================
    statement_date_from = fields.Date(
        string='Statement Period From',
        help='Start date of the statement period'
    )
    statement_date_to = fields.Date(
        string='Statement Period To',
        help='End date of the statement period'
    )

    # ==================== STATE ====================
    state = fields.Selection([
        ('select_type', 'Select Document Type'),
        ('upload', 'Upload Document'),
        ('processing', 'Processing...'),
        ('review', 'Review Data'),
        ('done', 'Completed'),
    ], default='select_type', string='State')

    # ==================== UPLOAD FIELDS ====================
    invoice_file = fields.Binary(
        string='Document File',
        help='Upload an image (PNG, JPG), PDF, or Excel file'
    )
    filename = fields.Char(string='Filename')
    
    # ==================== EXTRACTED FIELDS ====================
    vendor_id = fields.Many2one(
        'res.partner',
        string='Partner',
        help='Partner can be a vendor, customer, or both.'
    )
    vendor_name_extracted = fields.Char(
        string='Vendor Name (OCR)',
        help='Vendor name extracted from invoice'
    )
    invoice_number = fields.Char(string='Invoice Number')
    invoice_date = fields.Date(string='Invoice Date')
    due_date = fields.Date(string='Due Date')
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    
    subtotal = fields.Float(string='Subtotal')
    tax_amount = fields.Float(string='Tax Amount')
    total_amount = fields.Float(string='Total Amount')
    
    # ==================== LINE ITEMS ====================
    line_ids = fields.One2many(
        'af.vendor.bill.wizard.line',
        'wizard_id',
        string='Invoice Lines'
    )
    
    # ==================== DEBUG/INFO ====================
    raw_ocr_text = fields.Text(
        string='Raw OCR Text',
        help='Raw text extracted from document (for debugging)'
    )
    confidence_score = fields.Float(string='Confidence Score')
    processing_time = fields.Float(string='Processing Time (s)')
    
    # Created bill reference
    created_bill_id = fields.Many2one('account.move', string='Created Bill')
    
    # ==================== REFUND-SPECIFIC FIELDS ====================
    ticket_number = fields.Char(
        string='Ticket/Reference Number',
        help='Ticket number or reference for cancelled booking'
    )
    refund_status = fields.Selection([
        ('pending', 'Pending'),
        ('requested', 'Requested'),
        ('approved', 'Approved'),
        ('credited', 'Credit Note Received'),
    ], string='Refund Status', default='pending')
    
    original_bill_id = fields.Many2one(
        'account.move',
        string='Original Vendor Bill',
        domain=[('move_type', '=', 'in_invoice')],
        help='Link to the original bill for this refund'
    )
    refund_reason = fields.Text(string='Refund Reason')
    passenger_name = fields.Char(string='Passenger Name')
    flight_details = fields.Char(string='Flight/Booking Details')
    
    # Created refund tracking reference
    created_refund_id = fields.Many2one('af.refund.tracking', string='Created Refund')

    # ==================== COLUMN SELECTION (STATEMENT) ====================
    manual_column_selection = fields.Boolean(
        string='Select Match Column Manually',
        default=False,
        help='If checked, you will be able to choose which column from the statement '
             'to use for matching against Odoo references. If unchecked, the system '
             'will use the Voucher/Ref Code column automatically.'
    )
    extracted_columns_display = fields.Char(
        string='Detected Columns',
        readonly=True,
        help='Column names detected by AI from the uploaded statement'
    )
    column_ids = fields.One2many(
        'af.vendor.bill.wizard.column', 'wizard_id',
        string='Extracted Columns'
    )
    selected_column_id = fields.Many2one(
        'af.vendor.bill.wizard.column',
        string='Match Using Column',
        domain="[('wizard_id', '=', id)]",
        help='Select which column from the statement to use for matching against Odoo references'
    )

    # ==================== ACTIONS ====================
    
    def action_select_type(self):
        """Move from type selection to upload state."""
        self.ensure_one()
        self.state = 'upload'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_back_to_type(self):
        """Go back to document type selection."""
        self.ensure_one()
        self.state = 'select_type'
        self.invoice_file = False
        self.filename = False
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_process_file(self):
        """Process the uploaded file with Gemini Vision OCR and create invoice directly."""
        self.ensure_one()
        
        if not self.invoice_file:
            raise UserError(_('Please upload a document file first.'))
        
        self.state = 'processing'
        
        try:
            # Get file data
            file_data = base64.b64decode(self.invoice_file)
            
            # Determine file type
            file_ext = os.path.splitext(self.filename or '')[1].lower()
            
            _logger.info(f"Processing file: {self.filename} (Ext: {file_ext}) Type: {self.document_type}")
            

            
            if file_ext in ['.xlsx', '.xls']:
                # For Excel, we'll use a different approach
                if self.document_type == 'statement':
                     extracted_data = self._process_statement_excel(file_data)
                elif self.document_type == 'bank_statement':
                     extracted_data = self._process_bank_statement_excel(file_data)
                else:
                     extracted_data = self._process_excel(file_data)
            elif self.document_type == 'refund':
                # For refunds, use refund-specific prompt
                extracted_data = self._process_refund_with_gemini(file_data, file_ext)
            elif self.document_type == 'statement':
                # For partner statements (PDF/Image), use Gemini Vision
                extracted_data = self._process_statement_with_gemini(file_data, file_ext)
            elif self.document_type == 'bank_statement':
                # For bank statements (PDF/Image), use bank-specific Gemini prompt
                extracted_data = self._process_bank_statement_with_gemini(file_data, file_ext)
            else:
                # For vendor bills AND customer invoices, use standard invoice prompt
                extracted_data = self._process_with_gemini_vision(file_data, file_ext)
            
            # ==================== CUSTOMER INVOICE PARTNER SWAP ====================
            # For customer invoices, the partner is the BILL-TO party, not the issuer.
            # OCR extracts both; we swap so vendor_name = bill_to_name for downstream processing.
            if self.document_type == 'customer_invoice' and extracted_data:
                bill_to = extracted_data.get('bill_to_name', '')
                issuer = extracted_data.get('vendor_name', '')
                if bill_to:
                    _logger.info(f"Customer Invoice: swapping partner from issuer '{issuer}' to bill_to '{bill_to}'".encode('utf-8', 'replace').decode('utf-8'))
                    extracted_data['vendor_name'] = bill_to
                    extracted_data['bill_to_name'] = issuer
                else:
                    _logger.warning(f"Customer Invoice: no bill_to_name extracted, keeping issuer '{issuer}'")
            
            # Populate wizard fields with extracted data
            if self.document_type == 'refund':
                self._populate_from_refund_data(extracted_data)
            elif self.document_type == 'statement':
                self._populate_from_statement_data(extracted_data)
            elif self.document_type == 'bank_statement':
                self._populate_from_bank_statement_data(extracted_data)
            else:
                self._populate_from_extracted_data(extracted_data)
            
            # ==================== SKIP REVIEW - CREATE DIRECTLY ====================
            if self.document_type == 'refund':
                return self._create_refund_direct()
            elif self.document_type == 'statement':
                return self._create_statement_direct()
            elif self.document_type == 'bank_statement':
                return self.action_create_bank_statement()
            else:
                return self._create_bill_direct()
            
        except Exception as e:
            _logger.exception("OCR processing failed")
            self.state = 'upload'
            raise UserError(_('OCR Processing Failed:\n%s') % str(e))
    
    def _create_bill_direct(self):
        """Create vendor bill directly from OCR data and open it in Invoicing module."""
        # Ensure vendor is selected/created
        if not self.vendor_id:
            if self.vendor_name_extracted:
                self.vendor_id = self.env['res.partner'].create({
                    'name': self.vendor_name_extracted,
                    'supplier_rank': 1,
                })
            else:
                # Can't create without vendor - fall back to review
                self.state = 'review'
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': self._name,
                    'res_id': self.id,
                    'view_mode': 'form',
                    'target': 'new',
                }
        
        # Check for duplicate
        if self.invoice_number:
            existing_bill = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('partner_id', '=', self.vendor_id.id),
                ('ref', '=', self.invoice_number),
            ], limit=1)
            
            if existing_bill:
                raise UserError(_(
                    'A vendor bill with invoice reference "%s" already exists for vendor "%s".\n'
                    'Existing bill: %s (Status: %s)'
                ) % (self.invoice_number, self.vendor_id.name, existing_bill.name, existing_bill.state))
        
        # Use existing action_create_bill logic but return the invoice view
        bill = self._do_create_bill()
        
        self.created_bill_id = bill.id
        self.state = 'done'
        
        # Open the created bill in Invoicing module
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _create_refund_direct(self):
        """Create credit note directly from OCR data and open it in Invoicing module."""
        # Ensure vendor is selected/created
        if not self.vendor_id:
            if self.vendor_name_extracted:
                self.vendor_id = self.env['res.partner'].create({
                    'name': self.vendor_name_extracted,
                    'supplier_rank': 1,
                })
            else:
                # Can't create without vendor - fall back to review
                self.state = 'review'
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': self._name,
                    'res_id': self.id,
                    'view_mode': 'form',
                    'target': 'new',
                }
        
        # Validate ticket number
        if not self.ticket_number:
            # Fall back to review if missing required field
            self.state = 'review'
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
        
        # Call action_create_refund which already returns the credit note view
        return self.action_create_refund()
    
    def _process_with_gemini_vision(self, file_data: bytes, file_ext: str) -> dict:
        """Process file with Gemini Vision API."""
        start_time = time.time()
        
        # Get configuration
        # Get configuration
        config = self.env['res.config.settings'].get_config()
        
        # Use OCR credential (which maps to VLM/Gemini settings in config)
        api_key = config.gemini_api_key
        if not api_key:
            # Check if an OCR key exists but it's not Gemini (e.g. Groq selected)
            if config.ocr_api_key and not config.vlm_provider:
                 raise UserError(_('The selected provider (e.g. Groq) does not support Image Analysis (OCR). Please select a "Google Gemini" credential for OCR features.'))
            
            raise UserError(_('Please configure OCR/VLM Credential in AI Finance Settings.'))
            
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise UserError(_('Please install google-genai: pip install google-genai'))
        
        # Initialize client
        client = genai.Client(api_key=api_key)
        
        # Use configured model
        model_name = config.gemini_model or 'gemini-2.5-flash'
        _logger.info(f"Using Gemini model: {model_name}")
        
        # Determine MIME type
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.pdf': 'application/pdf',
            '.webp': 'image/webp',
        }
        mime_type = mime_types.get(file_ext, 'image/jpeg')
        
        # Invoice extraction prompt — also extract bill_to for customer invoice routing
        prompt = """
Analyze this invoice/bill and extract the following data as JSON:
{
  "vendor_name": "company or person name who ISSUED/SENT this document",
  "bill_to_name": "company or person name who RECEIVES/is BILLED BY this document (the 'Bill To' party)",
  "invoice_number": "invoice/bill reference number",
  "reference_code": "the voucher number or reference code (e.g. SI100, BR200, CM50). This is usually a short code printed on the document. If not found, use the invoice_number.",
  "document_type": "'invoice' if this is an invoice TO PAY, or 'bill' if this is a bill FOR SERVICES RENDERED",
  "invoice_date": "YYYY-MM-DD format",
  "due_date": "YYYY-MM-DD format or null",
  "currency": "3-letter currency code (USD, EUR, SAR, etc)",
  "line_items": [
    {"description": "item description", "quantity": number, "unit_price": number, "discount": number, "total": number}
  ],
  "subtotal": number,
  "tax_rate": "percentage as string",
  "tax_amount": number,
  "total_amount": number
}

IMPORTANT:
- "vendor_name": The company/person who CREATED and SENT this document (the header/logo company).
- "bill_to_name": The company/person listed under "Bill To" / "Invoice To" / "Customer" — the RECIPIENT of the document.
- "reference_code": Extract the voucher/reference code. This is CRITICAL for matching with partner statements. Examples: SI100, BR200, CM50, INV-001
- "unit_price" is the ORIGINAL price before any discount
- "discount" is the discount PERCENTAGE (e.g., 50 for 50%, 37 for 37%). If no discount, use 0.
- "total" is the final amount after discount for that line

Return ONLY valid JSON, no explanation or markdown.
"""
        
        # Send to Gemini Vision
        response = client.models.generate_content(
            model=model_name,
            contents=[
                prompt,
                types.Part.from_bytes(data=file_data, mime_type=mime_type)
            ]
        )
        
        processing_time = time.time() - start_time
        
        # Parse JSON response - more robust extraction
        json_text = response.text.strip()
        
        # Log raw response for debugging (handle Unicode safely)
        try:
            _logger.info(f"Gemini raw response (first 500 chars): {json_text[:500].encode('ascii', 'replace').decode()}")
        except Exception:
            _logger.info("Gemini raw response received (contains non-ASCII characters)")
        
        # Try multiple extraction methods
        extracted_data = None
        
        # Method 1: Direct JSON parse (if response is clean JSON)
        try:
            extracted_data = json.loads(json_text)
        except json.JSONDecodeError:
            pass
        
        # Method 2: Extract from markdown code block
        if not extracted_data:
            import re
            # Match ```json ... ``` or ``` ... ```
            code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
            if code_block_match:
                try:
                    extracted_data = json.loads(code_block_match.group(1).strip())
                except json.JSONDecodeError:
                    pass
        
        # Method 3: Find JSON object using regex
        if not extracted_data:
            # Find the first { and last } to extract the JSON object
            import re
            json_match = re.search(r'\{[\s\S]*\}', json_text)
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(0))
                except json.JSONDecodeError as e:
                    _logger.error(f"JSON parse error: {e}")
                    _logger.error(f"Attempted to parse: {json_match.group(0)[:500]}...")
                    raise UserError(_('OCR Processing Failed:\nFailed to parse JSON response from AI. Raw response:\n%s') % json_text[:1000])
        
        if not extracted_data:
            raise UserError(_('OCR Processing Failed:\nNo valid JSON found in AI response:\n%s') % json_text[:1000])
        
        extracted_data['processing_time'] = processing_time
        extracted_data['raw_text'] = json_text
        
        _logger.info(f"Gemini Vision extracted invoice data in {processing_time:.2f}s")
        
        return extracted_data
    
    
    
    def _process_statement_with_gemini(self, file_data: bytes, file_ext: str) -> dict:
        """Process Vendaor Statement with Gemini Vision API."""
        start_time = time.time()
        
        # Get configuration
        config = self.env['res.config.settings'].get_config()
        api_key = config.gemini_api_key
        if not api_key:
             raise UserError(_('Please configure OCR/VLM Credential in AI Finance Settings.'))
        
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise UserError(_('Please install google-genai: pip install google-genai'))
        
        # Initialize client
        client = genai.Client(api_key=api_key)
        model_name = config.gemini_model or 'gemini-2.5-flash'
        
        # Determine MIME type
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.pdf': 'application/pdf',
        }
        mime_type = mime_types.get(file_ext, 'image/jpeg')
        
        # Statement prompt — enhanced with period dates and voucher codes
        prompt = """
        Analyze this Partner Statement (Statement of Account) and extract the following data as JSON:
        {
          "vendor_name": "name of the partner/company issuing the statement",
          "statement_date": "statement date in YYYY-MM-DD format",
          "date_from": "start date of the statement period in YYYY-MM-DD format, or null if not specified",
          "date_to": "end date of the statement period in YYYY-MM-DD format, or null if not specified",
          "currency": "3-letter currency code as written on the document (e.g. SAR, USD, EUR, AED, EGP). Read it from the document text.",
          "total_amount": "total ending balance/amount due as number",
          "column_names": ["list of actual column header names found in the document table, e.g. Date, Description, Voucher No, Amount, Balance"],
          "recommended_match_column": "the column name from column_names that is most likely the voucher/reference code for matching (e.g. 'Voucher No' or 'Invoice Number')",
          "items": [
            {
              "date": "transaction date in YYYY-MM-DD format",
              "description": "description or reference text",
              "voucher_number": "the voucher/reference code (e.g. SI100, BR200, INV-001, CM50). This is the short identifier for this transaction.",
              "amount": "amount number (Positive for Invoices/Charges, Negative for Payments/Credits)"
            }
          ]
        }
        
        IMPORTANT:
        - "column_names": List ALL column headers exactly as they appear in the document table (e.g. ["Date", "Description", "Voucher No", "Debit", "Credit", "Balance"]). This helps the user identify which column to use for matching.
        - "recommended_match_column": From the column_names list, pick the ONE column that is most likely a voucher number, invoice reference, or transaction ID used for matching. This is usually called "Voucher No", "Ref", "Invoice Number", "Doc No", etc.
        - "currency": Read the ACTUAL currency code from the document. Look for labels like "Currency: SAR", "Total Due (SAR)", or currency symbols. Do NOT default to USD unless the document explicitly states USD.
        - "voucher_number": Extract the voucher number, reference code, or invoice number for EACH line item. This is CRITICAL for matching. Examples: SI100, BR200, CM50, BANK123, INV-2024-001
        - "date_from" and "date_to": Look for phrases like "Period: 01/01/2026 to 31/01/2026" or "From: ... To: ..."
        - "amount": Ensure correct sign. Invoices are usually positive additions to balance. Payments are negative deductions.
        - "description": Extract the full description text.
        
        Return ONLY valid JSON.
        """
        
        # Send to Gemini Vision
        response = client.models.generate_content(
            model=model_name,
            contents=[
                prompt,
                types.Part.from_bytes(data=file_data, mime_type=mime_type)
            ]
        )
        
        processing_time = time.time() - start_time
        json_text = response.text.strip()
        
        try:
            _logger.info(f"Gemini statement response: {json_text[:500]}")
        except: pass
        
        # Parse JSON
        extracted_data = None
        
        # Method 1: Direct JSON parse
        try:
            extracted_data = json.loads(json_text)
        except json.JSONDecodeError:
            pass
        
        # Method 2: Extract from markdown code block
        if not extracted_data:
            import re
            code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
            if code_block_match:
                try:
                    extracted_data = json.loads(code_block_match.group(1).strip())
                except:
                    pass
                    
        # Method 3: Regex
        if not extracted_data:
            import re
            json_match = re.search(r'\{[\s\S]*\}', json_text)
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(0))
                except:
                    pass

        if not extracted_data:
            raise UserError(_('OCR Failed: Could not parse AI response.'))
            
        extracted_data['processing_time'] = processing_time
        extracted_data['raw_text'] = json_text
        
        return extracted_data

    # ==================== STATEMENT-SPECIFIC METHODS ====================
    
    def _process_statement_excel(self, file_data: bytes) -> dict:
        """Process Excel file for Vendor Statement using Gemini AI.
        
        Reads the Excel file into a text table representation,
        then sends it to Gemini AI for intelligent extraction -
        exactly like the image/PDF statement flow.
        """
        start_time = time.time()
        
        # ---- Step 1: Read Excel into text ----
        try:
            import pandas as pd
            import io
        except ImportError:
            raise UserError(_('Please install pandas and openpyxl:\npip install pandas openpyxl'))
        
        try:
            try:
                df_raw = pd.read_excel(io.BytesIO(file_data), header=None)
            except Exception:
                df_raw = pd.read_excel(io.BytesIO(file_data), engine='openpyxl', header=None)
        except Exception as e:
            raise UserError(_('Failed to read Excel file: %s') % str(e))
        
        # Also try reading all sheets if there are multiple
        try:
            all_sheets = pd.read_excel(io.BytesIO(file_data), header=None, sheet_name=None)
        except Exception:
            all_sheets = {'Sheet1': df_raw}
        
        # Convert all sheets to text representation
        excel_text_parts = []
        for sheet_name, sheet_df in all_sheets.items():
            # Replace NaN with empty string for cleaner output
            sheet_df = sheet_df.fillna('')
            
            sheet_text = f"=== Sheet: {sheet_name} ===\n"
            # Convert to string table (tab-separated for clarity)
            sheet_text += sheet_df.to_string(index=False, header=False)
            excel_text_parts.append(sheet_text)
        
        excel_text = "\n\n".join(excel_text_parts)
        
        # Trim if too large (Gemini has token limits)
        max_chars = 30000
        if len(excel_text) > max_chars:
            excel_text = excel_text[:max_chars] + "\n... (truncated)"
        
        _logger.info(f"Excel converted to text ({len(excel_text)} chars) for AI processing")
        

        
        # ---- Step 2: Send to Gemini AI ----
        config = self.env['res.config.settings'].get_config()
        api_key = config.gemini_api_key
        if not api_key:
            raise UserError(_('Please configure OCR/VLM Credential in AI Finance Settings.'))
        
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise UserError(_('Please install google-genai: pip install google-genai'))
        
        client = genai.Client(api_key=api_key)
        model_name = config.gemini_model or 'gemini-2.5-flash'
        
        # Enhanced prompt with period dates and voucher codes
        prompt = f"""
You are analyzing a Partner Statement (Statement of Account) that was extracted from an Excel file.
Below is the raw content of the Excel file. Analyze it and extract the data as JSON.

EXCEL FILE CONTENT:
{excel_text}

Extract the following as JSON:
{{
  "vendor_name": "name of the partner/company issuing the statement",
  "statement_date": "statement date in YYYY-MM-DD format (use the most recent date if not explicitly stated)",
  "date_from": "start date of the statement period in YYYY-MM-DD format, or null if not specified",
  "date_to": "end date of the statement period in YYYY-MM-DD format, or null if not specified",
  "currency": "3-letter currency code as written in the spreadsheet (e.g. SAR, USD, EUR, AED, EGP). Do NOT default to USD.",
  "total_amount": "total ending balance/amount due as number",
  "column_names": ["list of actual column header names found in the spreadsheet table, e.g. Date, Description, Voucher No, Debit, Credit, Balance"],
  "recommended_match_column": "the column name from column_names that is most likely the voucher/reference code for matching",
  "items": [
    {{
      "date": "transaction date in YYYY-MM-DD format",
      "description": "description text",
      "voucher_number": "the voucher/reference code for this transaction (e.g. SI100, BR200, INV-001, CM50)",
      "amount": "amount number (Positive for Invoices/Charges, Negative for Payments/Credits)"
    }}
  ]
}}

IMPORTANT:
- "column_names": List ALL column headers exactly as they appear in the spreadsheet (e.g. ["Date", "Description", "Voucher No", "Debit", "Credit", "Balance"]). This helps the user identify which column to use for matching.
- "recommended_match_column": From the column_names list, pick the ONE column that is most likely a voucher number, invoice reference, or transaction ID used for matching.
- The Excel may have header rows, title rows, or summary rows before the actual data. Identify the actual transaction rows.
- "voucher_number": Extract the voucher number, reference code, or invoice number for EACH item. This is CRITICAL for matching. Look for columns like "Voucher", "Ref", "Reference", "Doc No", etc.
- "date_from" and "date_to": Look for period info like "Period: 01/01/2026 to 31/01/2026" or "From: ... To: ..."
- "amount": Ensure correct sign. Invoices/Debits are positive (money owed). Payments/Credits are negative (money paid).
- If there are separate Debit and Credit columns, treat Debit as positive and Credit as negative.
- "vendor_name": Look in the first few rows of the spreadsheet for the vendor/company name.
- "total_amount": Look for a balance, total due, or ending balance. If not found, sum the amounts.
- Ignore empty rows and summary/total rows in the items list.

Return ONLY valid JSON, no explanation or markdown.
"""
        
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_text(text=prompt)
                        ]
                    )
                ]
            )
        except Exception as e:
            _logger.error(f"Gemini API call failed for Excel statement: {e}")
            raise UserError(_('AI processing failed: %s') % str(e))
        
        processing_time = time.time() - start_time
        json_text = response.text.strip()
        
        try:
            _logger.info(f"Gemini Excel statement response: {json_text[:500]}")
        except Exception:
            pass
        
        # ---- Step 3: Parse JSON response (same logic as image/PDF) ----
        extracted_data = None
        
        # Method 1: Direct JSON parse
        try:
            extracted_data = json.loads(json_text)
        except json.JSONDecodeError:
            pass
        
        # Method 2: Extract from markdown code block
        if not extracted_data:
            import re
            code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
            if code_block_match:
                try:
                    extracted_data = json.loads(code_block_match.group(1).strip())
                except json.JSONDecodeError:
                    pass
        
        # Method 3: Regex for JSON object
        if not extracted_data:
            import re
            json_match = re.search(r'\{[\s\S]*\}', json_text)
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
        
        if not extracted_data:
            raise UserError(_('AI could not extract statement data from the Excel file.\nRaw response:\n%s') % json_text[:1000])
        
        extracted_data['processing_time'] = processing_time
        extracted_data['raw_text'] = json_text
        
        _logger.info(f"Gemini AI extracted Excel statement data in {processing_time:.2f}s "
                      f"({len(extracted_data.get('items', []))} items)")
        

        
        return extracted_data

    def _populate_from_statement_data(self, data: dict):
        """Populate wizard from statement data."""
        # Find partner (search broadly - could be vendor OR customer)
        vendor_name = data.get('vendor_name', '')
        self.vendor_name_extracted = vendor_name

        if vendor_name:
            # 1. Try exact match with supplier_rank
            vendor = self.env['res.partner'].search([
                ('name', 'ilike', vendor_name),
                ('supplier_rank', '>', 0)
            ], limit=1)

            # 2. Try exact match without supplier_rank (could be customer)
            if not vendor:
                vendor = self.env['res.partner'].search([
                    ('name', 'ilike', vendor_name),
                ], limit=1)

            # 3. Try partial match (first significant words)
            if not vendor:
                name_parts = vendor_name.split()
                if len(name_parts) >= 2:
                    partial = '%'.join(name_parts[:2])
                    vendor = self.env['res.partner'].search([
                        ('name', 'ilike', partial),
                    ], limit=1)

            if vendor:
                self.vendor_id = vendor.id

        self.invoice_date = data.get('statement_date')
        self.total_amount = data.get('total_amount', 0)
        self.raw_ocr_text = data.get('raw_text', '')

        # Set currency from OCR data (THIS WAS MISSING — causing USD default)
        if data.get('currency'):
            currency = self.env['res.currency'].search([
                ('name', '=', data['currency'].upper())
            ], limit=1)
            if currency:
                self.currency_id = currency.id
                _logger.info(f"Statement currency set from OCR: {currency.name}")
        
        # If no currency from OCR, try to use partner's most recent invoice currency
        if not data.get('currency') and self.vendor_id:
            partner_move = self.env['account.move'].search([
                ('partner_id', '=', self.vendor_id.id),
                ('state', '=', 'posted'),
            ], limit=1, order='date desc')
            if partner_move and partner_move.currency_id:
                self.currency_id = partner_move.currency_id.id
                _logger.info(f"Statement currency set from partner invoices: {partner_move.currency_id.name}")

        # Store period dates from OCR extraction
        self.statement_date_from = data.get('date_from') or False
        self.statement_date_to = data.get('date_to') or False

        # Store items temporarily
        self.line_ids.unlink()
        for item in data.get('items', []):
            self.env['af.vendor.bill.wizard.line'].create({
                'wizard_id': self.id,
                'description': item.get('description'),
                'total': item.get('amount'),
            })

        # Store the full items list in raw_ocr_text as JSON for _create_statement_direct
        import json
        self.raw_ocr_text = json.dumps(data, default=str)

    def _create_statement_direct(self):
        """Create the partner statement record with period and voucher support.
        
        ALWAYS goes to review state first so the user can:
        1. See the AI-extracted column names
        2. Choose which column to use for matching against Odoo references
        3. Verify partner and period dates
        """
        import json

        if not self.vendor_id:
            # Auto-create partner if we have an extracted name
            if self.vendor_name_extracted:
                self.vendor_id = self.env['res.partner'].create({
                    'name': self.vendor_name_extracted,
                    'supplier_rank': 1,
                })
            else:
                # Fall back to review state so user can select partner
                self.state = 'review'
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': self._name,
                    'res_id': self.id,
                    'view_mode': 'form',
                    'target': 'new',
                }

        try:
            data = json.loads(self.raw_ocr_text)
            items = data.get('items', [])
        except Exception:
            data = {}
            items = []

        # Extract column names from AI response and display them
        column_names = data.get('column_names', [])
        recommended_col = data.get('recommended_match_column', '')
        extracted_cols_str = ', '.join(column_names) if column_names else ''
        self.extracted_columns_display = extracted_cols_str

        # Populate column list for manual selection
        self.column_ids.unlink()
        recommended_record = None
        for col_name in column_names:
            is_rec = (col_name.strip().lower() == recommended_col.strip().lower()) if recommended_col else False
            rec = self.env['af.vendor.bill.wizard.column'].create({
                'wizard_id': self.id,
                'column_name': col_name.strip(),
                'is_recommended': is_rec,
            })
            if is_rec:
                recommended_record = rec

        # Pre-select the AI-recommended column
        if recommended_record:
            self.selected_column_id = recommended_record.id

        # Store period dates from OCR
        if not self.statement_date_from and data.get('date_from'):
            self.statement_date_from = data.get('date_from')
        if not self.statement_date_to and data.get('date_to'):
            self.statement_date_to = data.get('date_to')

        # Store extracted columns in data for later use
        data['_extracted_columns'] = extracted_cols_str
        data['_recommended_match_column'] = recommended_col
        self.raw_ocr_text = json.dumps(data, default=str)

        # If manual column selection is OFF → create statement and match automatically
        if not self.manual_column_selection:
            return self._create_and_match_statement(data)

        # If manual column selection is ON → go to review so user can pick the column
        self.state = 'review'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _create_and_match_statement(self, data=None):
        """Actually create the statement record and run matching."""
        import json
        if data is None:
            try:
                data = json.loads(self.raw_ocr_text)
            except Exception:
                data = {}

        items = data.get('items', [])
        extracted_cols_str = data.get('_extracted_columns', self.extracted_columns_display or '')

        # Determine match_key_column from user's column selection
        if self.selected_column_id:
            selected_name = self.selected_column_id.column_name.strip().lower()
            # Map the selected column name to internal field
            description_keywords = ['description', 'desc', 'detail', 'details', 'narration', 'particular', 'particulars']
            if any(kw in selected_name for kw in description_keywords):
                match_key = 'description'
            else:
                match_key = 'voucher_number'
        else:
            match_key = 'voucher_number'

        stmt_vals = {
            'partner_id': self.vendor_id.id,
            'statement_date': self.invoice_date or fields.Date.today(),
            'statement_total_due': self.total_amount,
            'currency_id': self.currency_id.id,
            'ocr_raw_text': self.raw_ocr_text,
            'extracted_columns': extracted_cols_str,
            'match_key_column': match_key,
        }

        if self.statement_date_from:
            stmt_vals['date_from'] = self.statement_date_from
        if self.statement_date_to:
            stmt_vals['date_to'] = self.statement_date_to

        statement = self.env['af.vendor.statement'].create(stmt_vals)

        for item in items:
            self.env['af.vendor.statement.line'].create({
                'statement_id': statement.id,
                'date': item.get('date') or fields.Date.today(),
                'name': item.get('description'),
                'voucher_number': item.get('voucher_number', ''),
                'amount': item.get('amount'),
            })

        # Populate the statement's column dropdown from extracted columns
        column_names = data.get('column_names', [])
        recommended_col = data.get('_recommended_match_column', data.get('recommended_match_column', ''))
        recommended_record = None
        for col_name in column_names:
            is_rec = (col_name.strip().lower() == recommended_col.strip().lower()) if recommended_col else False
            col_rec = self.env['af.vendor.statement.column'].create({
                'statement_id': statement.id,
                'column_name': col_name.strip(),
                'is_recommended': is_rec,
            })
            if is_rec:
                recommended_record = col_rec

        # Pre-select the recommended or user-selected column on the statement
        if self.selected_column_id:
            # User selected a column in the wizard — find the matching one on the statement
            wizard_col_name = self.selected_column_id.column_name.strip().lower()
            stmt_col = statement.statement_column_ids.filtered(
                lambda c: c.column_name.strip().lower() == wizard_col_name
            )
            if stmt_col:
                statement.selected_column_id = stmt_col[0].id
        elif recommended_record:
            statement.selected_column_id = recommended_record.id

        statement.action_match_lines()
        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'af.vendor.statement',
            'res_id': statement.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ==================== BANK STATEMENT METHODS ====================

    def _process_bank_statement_with_gemini(self, file_data: bytes, file_ext: str):
        """Process Bank Statement with Gemini Vision API."""
        start_time = time.time()

        config = self.env['res.config.settings'].get_config()
        api_key = config.gemini_api_key
        if not api_key:
            raise UserError(_('Please configure OCR/VLM Credential in AI Finance Settings.'))

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise UserError(_('Please install google-genai: pip install google-genai'))

        client = genai.Client(api_key=api_key)
        model_name = config.gemini_model or 'gemini-2.5-flash'

        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.pdf': 'application/pdf',
        }
        mime_type = mime_types.get(file_ext, 'image/jpeg')

        prompt = """
Analyze this BANK STATEMENT and extract the following data as JSON:
{
  "bank_name": "name of the bank",
  "account_number": "bank account number or IBAN",
  "statement_date": "statement date in YYYY-MM-DD format",
  "date_from": "start date of the statement period in YYYY-MM-DD format",
  "date_to": "end date of the statement period in YYYY-MM-DD format",
  "currency": "3-letter currency code as shown on the document (e.g. SAR, USD, EUR). Do NOT default to USD.",
  "opening_balance": "opening/beginning balance as a number",
  "closing_balance": "closing/ending balance as a number",
  "items": [
    {
      "date": "transaction date in YYYY-MM-DD format",
      "description": "transaction description text",
      "debit": "debit amount (money going OUT of the account) as number, or 0",
      "credit": "credit amount (money coming IN to the account) as number, or 0",
      "balance": "running balance after this transaction as number"
    }
  ]
}

IMPORTANT:
- "currency": Read the ACTUAL currency from the document. Look for currency symbols or codes. Do NOT default to USD.
- "debit": Money leaving the account (payments, withdrawals, transfers out). Always positive or 0.
- "credit": Money entering the account (deposits, transfers in, interest). Always positive or 0.
- "balance": The running balance shown on the statement after each transaction.
- "opening_balance" and "closing_balance": Extract from the statement header/summary.
- "date_from" and "date_to": Look for "Period:", "Statement Period:", "From ... To ..." etc.
- Do NOT include opening balance or closing balance as transaction items.

Return ONLY valid JSON.
"""

        response = client.models.generate_content(
            model=model_name,
            contents=[
                prompt,
                types.Part.from_bytes(data=file_data, mime_type=mime_type)
            ]
        )

        processing_time = time.time() - start_time
        json_text = response.text.strip()

        try:
            _logger.info(f"Bank Statement OCR response (first 500 chars): {json_text[:500].encode('ascii', 'replace').decode()}")
        except Exception:
            _logger.info("Bank Statement OCR response received (contains non-ASCII)")

        extracted_data = None

        try:
            extracted_data = json.loads(json_text)
        except json.JSONDecodeError:
            pass

        if not extracted_data:
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

        if not extracted_data:
            raise UserError(_('Could not parse bank statement data from OCR response.'))

        extracted_data['processing_time'] = processing_time
        extracted_data['raw_text'] = json_text

        _logger.info(f"Bank Statement OCR: extracted {len(extracted_data.get('items', []))} transactions "
                     f"in {processing_time:.2f}s")
        return extracted_data

    def _process_bank_statement_excel(self, file_data: bytes):
        """Process Excel bank statement using Gemini AI for intelligent extraction."""
        start_time = time.time()

        config = self.env['res.config.settings'].get_config()
        api_key = config.gemini_api_key
        if not api_key:
            raise UserError(_('Please configure OCR/VLM Credential in AI Finance Settings.'))

        try:
            from google import genai
        except ImportError:
            raise UserError(_('Please install google-genai: pip install google-genai'))

        import pandas as pd
        import io

        try:
            df = pd.read_excel(io.BytesIO(file_data), header=None)
        except Exception as e:
            raise UserError(_('Failed to read Excel file: %s') % str(e))

        excel_text = df.to_string(index=False, header=False)

        client = genai.Client(api_key=api_key)
        model_name = config.gemini_model or 'gemini-2.5-flash'

        prompt = f"""
You are analyzing a BANK STATEMENT in spreadsheet format.

EXCEL FILE CONTENT:
{excel_text}

Extract the following as JSON:
{{
  "bank_name": "name of the bank",
  "account_number": "bank account number or IBAN",
  "statement_date": "statement date in YYYY-MM-DD format",
  "date_from": "start date of the period in YYYY-MM-DD format",
  "date_to": "end date of the period in YYYY-MM-DD format",
  "currency": "3-letter currency code as found in the spreadsheet (e.g. SAR, USD, EUR). Do NOT default to USD.",
  "opening_balance": "opening/beginning balance as number",
  "closing_balance": "closing/ending balance as number",
  "items": [
    {{
      "date": "transaction date in YYYY-MM-DD format",
      "description": "description text",
      "debit": "debit amount (money OUT) as number, or 0",
      "credit": "credit amount (money IN) as number, or 0",
      "balance": "running balance as number"
    }}
  ]
}}

IMPORTANT:
- Look for header rows to identify column meanings (Date, Description, Debit, Credit, Balance).
- "debit": Money leaving the account. Always positive or 0.
- "credit": Money entering the account. Always positive or 0.
- If there are separate "Withdrawal" and "Deposit" columns, map them to debit and credit.
- Ignore summary/total rows and empty rows.
- Extract bank name and account info from header rows.

Return ONLY valid JSON.
"""

        response = client.models.generate_content(model=model_name, contents=[prompt])

        processing_time = time.time() - start_time
        json_text = response.text.strip()

        extracted_data = None
        try:
            extracted_data = json.loads(json_text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass

        if not extracted_data:
            raise UserError(_('Could not parse bank statement data from Excel OCR response.'))

        extracted_data['processing_time'] = processing_time
        extracted_data['raw_text'] = json_text
        return extracted_data

    def _populate_from_bank_statement_data(self, data: dict):
        """Populate wizard fields from bank statement OCR data."""
        self.vendor_name_extracted = data.get('bank_name', '')
        self.invoice_date = data.get('statement_date')
        self.total_amount = data.get('closing_balance', 0)
        self.raw_ocr_text = data.get('raw_text', '')

        # Set period dates
        self.statement_date_from = data.get('date_from') or False
        self.statement_date_to = data.get('date_to') or False

        # Set currency
        if data.get('currency'):
            currency = self.env['res.currency'].search([
                ('name', '=', data['currency'].upper())
            ], limit=1)
            if currency:
                self.currency_id = currency.id

        # Store items in raw_ocr_text as JSON for _create_bank_statement_direct
        self.raw_ocr_text = json.dumps(data, default=str)

    def action_create_bank_statement(self):
        """Create the bank statement record and open it."""

        if not self.bank_account_id:
            # Fall back to review so user can select bank account
            self.state = 'review'
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }

        try:
            data = json.loads(self.raw_ocr_text)
            items = data.get('items', [])
        except Exception:
            items = []
            data = {}

        stmt_vals = {
            'bank_account_id': self.bank_account_id.id,
            'bank_name': data.get('bank_name', ''),
            'account_number': data.get('account_number', ''),
            'date_from': self.statement_date_from or data.get('date_from'),
            'date_to': self.statement_date_to or data.get('date_to'),
            'opening_balance': data.get('opening_balance', 0),
            'closing_balance': data.get('closing_balance', 0),
            'currency_id': self.currency_id.id,
            'ocr_raw_text': self.raw_ocr_text,
        }

        statement = self.env['af.bank.statement'].create(stmt_vals)

        # Create statement lines
        for item in items:
            self.env['af.bank.statement.line'].create({
                'statement_id': statement.id,
                'date': item.get('date') or fields.Date.today(),
                'description': item.get('description', ''),
                'debit': item.get('debit', 0) or 0,
                'credit': item.get('credit', 0) or 0,
                'balance': item.get('balance', 0) or 0,
            })

        # Auto-match if we have period dates
        if statement.date_from and statement.date_to:
            statement.action_match_lines()

        self.state = 'done'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'af.bank.statement',
            'res_id': statement.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _process_excel(self, file_data: bytes) -> dict:
        """Process Excel file (for pre-formatted invoice data)."""
        try:
            import pandas as pd
            import io
            
            df = pd.read_excel(io.BytesIO(file_data))
            
            # Try to extract invoice data from Excel
            # This assumes a specific format - can be customized
            extracted_data = {
                'vendor_name': df.iloc[0, 1] if len(df) > 0 else None,
                'invoice_number': str(df.iloc[1, 1]) if len(df) > 1 else None,
                'invoice_date': None,
                'total_amount': None,
                'line_items': [],
            }
            
            # Try to find total
            for idx, row in df.iterrows():
                if 'total' in str(row.iloc[0]).lower():
                    try:
                        extracted_data['total_amount'] = float(row.iloc[1])
                    except:
                        pass
            
            return extracted_data
            
        except Exception as e:
            raise UserError(_('Failed to process Excel file: %s') % str(e))
    
    def _populate_from_extracted_data(self, data: dict):
        """Populate wizard fields from extracted data."""
        vals = {}
        
        # Partner (vendor or customer depending on document type)
        vals['vendor_name_extracted'] = data.get('vendor_name', '')
        if data.get('vendor_name'):
            partner_name = data['vendor_name']
            # For customer invoices, search customer_rank first, then any partner
            if self.document_type == 'customer_invoice':
                vendor = self.env['res.partner'].search([
                    ('name', 'ilike', partner_name),
                    ('customer_rank', '>', 0)
                ], limit=1)
                if not vendor:
                    vendor = self.env['res.partner'].search([
                        ('name', 'ilike', partner_name),
                    ], limit=1)
            else:
                vendor = self.env['res.partner'].search([
                    ('name', 'ilike', partner_name),
                    ('supplier_rank', '>', 0)
                ], limit=1)
                if not vendor:
                    vendor = self.env['res.partner'].search([
                        ('name', 'ilike', partner_name),
                    ], limit=1)
            if vendor:
                vals['vendor_id'] = vendor.id
        
        # Invoice details
        vals['invoice_number'] = data.get('invoice_number', '')
        
        # Dates
        if data.get('invoice_date'):
            try:
                if isinstance(data['invoice_date'], str):
                    vals['invoice_date'] = datetime.strptime(
                        data['invoice_date'], '%Y-%m-%d'
                    ).date()
            except:
                pass
        
        if data.get('due_date'):
            try:
                if isinstance(data['due_date'], str):
                    vals['due_date'] = datetime.strptime(
                        data['due_date'], '%Y-%m-%d'
                    ).date()
            except:
                pass
        
        # Currency
        if data.get('currency'):
            currency = self.env['res.currency'].search([
                ('name', '=', data['currency'].upper())
            ], limit=1)
            if currency:
                vals['currency_id'] = currency.id
        
        # Amounts
        vals['subtotal'] = data.get('subtotal', 0) or 0
        vals['tax_amount'] = data.get('tax_amount', 0) or 0
        vals['total_amount'] = data.get('total_amount', 0) or 0

        # Reference/Voucher Code from OCR
        vals['reference_code'] = data.get('reference_code', '') or data.get('invoice_number', '')

        # Debug info
        vals['raw_ocr_text'] = data.get('raw_text', '')
        vals['processing_time'] = data.get('processing_time', 0)
        vals['confidence_score'] = 0.95  # Gemini typically has high confidence

        self.write(vals)
        
        # Create line items
        self.line_ids.unlink()
        for item in data.get('line_items', []):
            self.env['af.vendor.bill.wizard.line'].create({
                'wizard_id': self.id,
                'description': item.get('description', 'Item'),
                'quantity': item.get('quantity', 1),
                'unit_price': item.get('unit_price', 0) or item.get('total', 0),
                'discount': item.get('discount', 0),
                'total': item.get('total', 0),
            })
    
    def action_create_bill(self):
        """Create the vendor bill from reviewed data."""
        self.ensure_one()
        
        # Ensure vendor is selected
        if not self.vendor_id:
            # Create new vendor if not found
            if self.vendor_name_extracted:
                self.vendor_id = self.env['res.partner'].create({
                    'name': self.vendor_name_extracted,
                    'supplier_rank': 1,
                })
            else:
                raise UserError(_('Please select or enter a vendor name.'))
        
        # ==================== DUPLICATE BILL CHECK ====================
        # Check if a bill with the same invoice reference and vendor already exists
        if self.invoice_number:
            existing_bill = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('partner_id', '=', self.vendor_id.id),
                ('ref', '=', self.invoice_number),
            ], limit=1)
            
            if existing_bill:
                raise UserError(_(
                    'A vendor bill with invoice reference "%s" already exists for vendor "%s".\n'
                    'Existing bill: %s (Status: %s)\n\n'
                    'If you need to re-upload this document, please delete the existing bill first.'
                ) % (self.invoice_number, self.vendor_id.name, existing_bill.name, existing_bill.state))
        
        # Create the bill using helper method
        bill = self._do_create_bill()
        
        self.created_bill_id = bill.id
        self.state = 'done'
        
        # Return action to open the created bill
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _do_create_bill(self):
        """Core bill creation logic - returns the created account.move record."""
        # Calculate sum of line items
        line_items_sum = sum(line.quantity * line.unit_price for line in self.line_ids)
        
        # Find or create matching Odoo tax if tax was extracted
        tax_ids = []
        if self.tax_amount > 0.01 and self.subtotal > 0:
            # Calculate exact tax rate from extracted data
            calculated_tax_rate = round((self.tax_amount / self.subtotal) * 100, 2)
            _logger.info(f"Looking for tax rate: {calculated_tax_rate}%")
            
            # Find or create a generic Tax Group for OCR
            tax_group = self.env['account.tax.group'].search([
                ('name', '=', 'OCR Taxes')
            ], limit=1)
            
            if not tax_group:
                tax_group = self.env['account.tax.group'].sudo().create({
                    'name': 'OCR Taxes',
                    'sequence': 10,
                })

            # First try to find an existing matching tax
            existing_tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'purchase'),
                ('amount_type', '=', 'percent'),
                ('amount', '>=', calculated_tax_rate - 0.5),
                ('amount', '<=', calculated_tax_rate + 0.5),
            ], limit=1)
            
            if existing_tax:
                # Force update tax group if it is incorrect
                if existing_tax.tax_group_id.id != tax_group.id:
                    existing_tax.sudo().write({'tax_group_id': tax_group.id})
                    _logger.info(f"Updated tax group for {existing_tax.name} to OCR Taxes")
                
                tax_ids = [(6, 0, [existing_tax.id])]
                _logger.info(f"Found existing tax: {existing_tax.name} ({existing_tax.amount}%)")
            else:
                # Create a new purchase tax with the exact rate
                try:
                    new_tax = self.env['account.tax'].sudo().create({
                        'name': f'Purchase Tax {calculated_tax_rate}%',
                        'type_tax_use': 'purchase',
                        'amount_type': 'percent',
                        'amount': calculated_tax_rate,
                        'description': f'Auto-created from OCR invoice ({calculated_tax_rate}%)',
                        'tax_group_id': tax_group.id,
                    })
                    tax_ids = [(6, 0, [new_tax.id])]
                    _logger.info(f"Created new tax: {new_tax.name} ({new_tax.amount}%) in group {tax_group.name}")
                except Exception as e:
                    _logger.warning(f"Could not create tax: {e}")
                    tax_ids = []
        
        # Prepare invoice lines WITH tax and discount applied
        invoice_lines = []
        for line in self.line_ids:
            line_vals = {
                'name': line.description,
                'quantity': line.quantity,
                'price_unit': line.unit_price,
                'discount': line.discount,
            }
            if tax_ids:
                line_vals['tax_ids'] = tax_ids
            invoice_lines.append((0, 0, line_vals))
        
        # Check for discount or additional charges
        expected_with_tax = self.subtotal + self.tax_amount if self.subtotal > 0 else line_items_sum
        difference = self.total_amount - expected_with_tax
        
        if abs(difference) > 0.1:
            if difference < 0:
                # Discount
                invoice_lines.append((0, 0, {
                    'name': 'Discount',
                    'quantity': 1,
                    'price_unit': difference,
                }))
                _logger.info(f"Added discount: {difference}")
            else:
                # Additional charges
                line_vals = {
                    'name': 'Additional Charges',
                    'quantity': 1,
                    'price_unit': difference,
                }
                if tax_ids:
                    line_vals['tax_ids'] = tax_ids
                invoice_lines.append((0, 0, line_vals))
                _logger.info(f"Added additional charges: {difference}")
        
        # If no lines, create one line with total
        if not invoice_lines:
            invoice_lines.append((0, 0, {
                'name': 'Invoice Total',
                'quantity': 1,
                'price_unit': self.total_amount,
            }))
        
        # Determine move_type based on document_type
        # OCR Import Rules:
        #   Invoice FROM partner → Vendor Bill (in_invoice) in Odoo
        #   Bill FROM partner → Customer Invoice (out_invoice) in Odoo
        if self.document_type == 'customer_invoice':
            move_type = 'out_invoice'
        else:
            move_type = 'in_invoice'

        # Use reference_code as the ref (for voucher matching with statements)
        ref_value = self.reference_code or self.invoice_number

        # Create the invoice/bill
        bill_vals = {
            'move_type': move_type,
            'partner_id': self.vendor_id.id,
            'ref': ref_value,
            'invoice_date': self.invoice_date or fields.Date.today(),
            'invoice_date_due': self.due_date,
            'currency_id': self.currency_id.id,
            'invoice_line_ids': invoice_lines,
        }

        bill = self.env['account.move'].create(bill_vals)
        _logger.info(f"Created {move_type}: {bill.name} (ref={ref_value}) for {bill.amount_total}")

        return bill
    
    def action_create_statement_from_review(self):
        """Create statement from review state with user's column selection.
        
        This is called after the user has:
        1. Seen the AI-extracted column names
        2. Chosen which column to use for matching (match_key_column)
        3. Verified partner and period dates
        """
        self.ensure_one()
        import json

        if not self.vendor_id:
            raise UserError(_('Please select a partner before creating the statement.'))

        try:
            data = json.loads(self.raw_ocr_text)
        except Exception:
            data = {}

        # Check if a statement was already created (old flow compatibility)
        existing_stmt_id = data.get('_statement_id')
        if existing_stmt_id:
            extracted_cols_str = data.get('_extracted_columns', self.extracted_columns_display or '')
            statement = self.env['af.vendor.statement'].browse(existing_stmt_id)
            if statement.exists():
                update_vals = {
                    'match_key_column': self.match_key_column,
                    'extracted_columns': extracted_cols_str,
                }
                if self.statement_date_from:
                    update_vals['date_from'] = self.statement_date_from
                if self.statement_date_to:
                    update_vals['date_to'] = self.statement_date_to
                statement.write(update_vals)
                statement.action_match_lines()
                self.state = 'done'
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'af.vendor.statement',
                    'res_id': statement.id,
                    'view_mode': 'form',
                    'target': 'current',
                }

        # Create NEW statement using the shared helper
        return self._create_and_match_statement(data)

    def action_back_to_upload(self):
        """Go back to upload state."""
        self.state = 'upload'
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    # ==================== REFUND-SPECIFIC METHODS ====================
    
    def _process_refund_with_gemini(self, file_data: bytes, file_ext: str) -> dict:
        """Process refund document with Gemini Vision API."""
        start_time = time.time()
        
        # Get configuration
        config = self.env['res.config.settings'].get_config()
        
        # Use OCR credential
        api_key = config.gemini_api_key
        if not api_key:
             raise UserError(_('Please configure OCR/VLM Credential in AI Finance Settings.'))
        
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise UserError(_('Please install google-genai: pip install google-genai'))
        
        # Initialize client
        client = genai.Client(api_key=api_key)
        model_name = config.gemini_model or 'gemini-2.5-flash'
        
        # Determine MIME type
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.pdf': 'application/pdf',
            '.webp': 'image/webp',
        }
        mime_type = mime_types.get(file_ext, 'image/jpeg')
        
        # Refund extraction prompt
        prompt = """
Analyze this refund/credit memo document and extract the following data as JSON:
{
  "vendor_name": "supplier or vendor name",
  "ticket_number": "credit memo number, ticket number, booking reference, or document reference",
  "passenger_name": "customer or passenger name",
  "flight_details": "flight number, route, or booking/order details",
  "original_invoice": "original invoice number being credited if mentioned",
  "original_date": "original invoice/order date in YYYY-MM-DD format or null",
  "cancellation_date": "credit memo/cancellation date in YYYY-MM-DD format or null",
  "currency": "3-letter currency code (USD, EUR, EGP, SAR, IQD, etc)",
  "line_items": [
    {
      "description": "item description",
      "quantity": quantity as number,
      "unit_price": original unit price before any discount as number,
      "discount": discount percentage as number (e.g., 27 for 27%),
      "total": line total after discount as number
    }
  ],
  "subtotal": "subtotal before tax as number",
  "tax_rate": "tax rate as percentage number (e.g. 14 for 14%) or null",
  "tax_amount": "tax amount as number or 0",
  "refund_amount": "total refund amount including tax as number",
  "penalty_amount": "cancellation penalty/fee as number or 0",
  "refund_reason": "reason for credit/cancellation if mentioned"
}

IMPORTANT for line_items:
- "unit_price" is the ORIGINAL price before any discount
- "discount" is the discount PERCENTAGE (e.g., 50 for 50%, 27 for 27%). If no discount, use 0.
- "total" is the final amount after discount for that line (before tax)

Return ONLY valid JSON, no explanation or markdown.
"""
        
        # Send to Gemini Vision
        response = client.models.generate_content(
            model=model_name,
            contents=[
                prompt,
                types.Part.from_bytes(data=file_data, mime_type=mime_type)
            ]
        )
        
        processing_time = time.time() - start_time
        
        # Parse JSON response - robust extraction
        json_text = response.text.strip()
        
        # Log raw response for debugging (handle Unicode safely)
        try:
            _logger.info(f"Gemini refund raw response (first 500 chars): {json_text[:500].encode('ascii', 'replace').decode()}")
        except Exception:
            _logger.info("Gemini refund raw response received (contains non-ASCII characters)")
        
        # Try multiple extraction methods
        extracted_data = None
        
        # Method 1: Direct JSON parse
        try:
            extracted_data = json.loads(json_text)
        except json.JSONDecodeError:
            pass
        
        # Method 2: Extract from markdown code block
        if not extracted_data:
            import re
            code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', json_text)
            if code_block_match:
                try:
                    extracted_data = json.loads(code_block_match.group(1).strip())
                except json.JSONDecodeError:
                    pass
        
        # Method 3: Find JSON object using regex
        if not extracted_data:
            import re
            json_match = re.search(r'\{[\s\S]*\}', json_text)
            if json_match:
                try:
                    extracted_data = json.loads(json_match.group(0))
                except json.JSONDecodeError as e:
                    _logger.error(f"JSON parse error: {e}")
                    raise UserError(_('OCR Processing Failed:\nFailed to parse refund JSON:\n%s') % json_text[:1000])
        
        if not extracted_data:
            raise UserError(_('OCR Processing Failed:\nNo valid JSON found in refund response:\n%s') % json_text[:1000])
        
        extracted_data['processing_time'] = processing_time
        extracted_data['raw_text'] = json_text
        
        _logger.info(f"Gemini Vision extracted refund data in {processing_time:.2f}s")
        
        return extracted_data
    
    def _populate_from_refund_data(self, data: dict):
        """Populate wizard fields from extracted refund data."""
        vals = {}
        
        # Vendor
        vals['vendor_name_extracted'] = data.get('vendor_name', '')
        if data.get('vendor_name'):
            vendor = self.env['res.partner'].search([
                ('name', 'ilike', data['vendor_name']),
                ('supplier_rank', '>', 0)
            ], limit=1)
            if vendor:
                vals['vendor_id'] = vendor.id
        
        # Refund details
        vals['ticket_number'] = data.get('ticket_number', '')
        vals['passenger_name'] = data.get('passenger_name', '')
        vals['flight_details'] = data.get('flight_details', '')
        vals['refund_reason'] = data.get('refund_reason', '')
        
        # Store original invoice reference
        self.invoice_number = data.get('original_invoice', '')
        
        # Dates
        if data.get('cancellation_date'):
            try:
                if isinstance(data['cancellation_date'], str):
                    vals['invoice_date'] = datetime.strptime(
                        data['cancellation_date'], '%Y-%m-%d'
                    ).date()
            except:
                pass
        
        # Currency
        if data.get('currency'):
            currency = self.env['res.currency'].search([
                ('name', '=', data['currency'].upper())
            ], limit=1)
            if currency:
                vals['currency_id'] = currency.id
        
        # Amounts - properly extract subtotal, tax, and total
        # Credit memos often show negative values, so we use abs() to get positive amounts
        raw_subtotal = data.get('subtotal', 0) or 0
        raw_tax = data.get('tax_amount', 0) or 0
        raw_total = data.get('refund_amount', 0) or 0
        
        # Convert to positive values (Odoo handles the credit/debit direction)
        vals['subtotal'] = abs(raw_subtotal) if isinstance(raw_subtotal, (int, float)) else 0
        vals['tax_amount'] = abs(raw_tax) if isinstance(raw_tax, (int, float)) else 0
        vals['total_amount'] = abs(raw_total) if isinstance(raw_total, (int, float)) else 0
        
        # If subtotal is 0 but we have total and tax, calculate subtotal
        if vals['subtotal'] == 0 and vals['total_amount'] > 0:
            vals['subtotal'] = vals['total_amount'] - vals['tax_amount']
        
        # Log extracted amounts for debugging
        _logger.info(f"Refund amounts: subtotal={vals['subtotal']}, tax={vals['tax_amount']}, total={vals['total_amount']}")
        
        # Debug info
        vals['raw_ocr_text'] = data.get('raw_text', '')
        vals['processing_time'] = data.get('processing_time', 0)
        vals['confidence_score'] = 0.95
        
        self.write(vals)
        
        # Create line items - delete old ones first
        self.line_ids.unlink()
        
        line_items = data.get('line_items', [])
        if line_items:
            for item in line_items:
                # Use abs() for amounts as credit memos show negative values
                qty = item.get('quantity', 1) or 1
                unit_price = item.get('unit_price', 0) or item.get('total', 0)
                total = item.get('total', 0)
                
                self.env['af.vendor.bill.wizard.line'].create({
                    'wizard_id': self.id,
                    'description': item.get('description', 'Item'),
                    'quantity': abs(qty) if isinstance(qty, (int, float)) else 1,
                    'unit_price': abs(unit_price) if isinstance(unit_price, (int, float)) else 0,
                    'discount': item.get('discount', 0),
                })
        else:
            # Fallback: Create a single line with the subtotal if no line items
            if vals['subtotal'] > 0:
                self.env['af.vendor.bill.wizard.line'].create({
                    'wizard_id': self.id,
                    'description': f"Refund: {vals.get('ticket_number', 'Credit Memo')}",
                    'quantity': 1,
                    'unit_price': vals['subtotal'],
                    'total': vals['subtotal'],
                })
        
        _logger.info(f"Populated refund data with {len(line_items)} line items")
    
    def action_create_refund(self):
        """Create Credit Note and refund tracking record from reviewed data."""
        self.ensure_one()
        
        # Validate required fields
        if not self.ticket_number:
            raise UserError(_('Please enter a ticket/reference number.'))
        
        # Ensure vendor is selected
        if not self.vendor_id:
            if self.vendor_name_extracted:
                self.vendor_id = self.env['res.partner'].create({
                    'name': self.vendor_name_extracted,
                    'supplier_rank': 1,
                })
            else:
                raise UserError(_('Please select or enter a vendor name.'))
        
        # Debug: Log current values for tax calculation
        _logger.info(f"Creating refund - subtotal: {self.subtotal}, tax_amount: {self.tax_amount}, total: {self.total_amount}")
        _logger.info(f"Tax check: tax_amount > 0.01 = {self.tax_amount > 0.01}, subtotal > 0 = {self.subtotal > 0}")
        
        # Check for duplicate ticket number
        existing = self.env['af.refund.tracking'].search([
            ('ticket_number', '=', self.ticket_number),
            ('vendor_id', '=', self.vendor_id.id),
        ], limit=1)
        
        if existing:
            # Check if the Credit Note still exists
            if existing.credit_note_id and existing.credit_note_id.exists():
                raise UserError(_(
                    'A refund tracking for ticket "%s" already exists for vendor "%s".\n'
                    'Existing record: %s (Status: %s)'
                ) % (self.ticket_number, self.vendor_id.name, existing.name, existing.state))
            else:
                # Credit Note was deleted, remove old tracking record and allow re-creation
                _logger.info(f"Removing orphan tracking record {existing.name} (Credit Note was deleted)")
                existing.unlink()
        
        # ==================== CREATE CREDIT NOTE (VENDOR REFUND) ====================
        # Find or create matching tax if tax_amount > 0
        tax_ids = []
        if self.tax_amount > 0.01 and self.subtotal > 0:
            # Calculate tax rate from extracted data
            calculated_tax_rate = round((self.tax_amount / self.subtotal) * 100, 2)
            _logger.info(f"Looking for tax rate: {calculated_tax_rate}% for refund")
            
            # Find or create tax group
            tax_group = self.env['account.tax.group'].search([
                ('name', '=', 'OCR Taxes')
            ], limit=1)
            
            if not tax_group:
                tax_group = self.env['account.tax.group'].sudo().create({
                    'name': 'OCR Taxes',
                    'sequence': 10,
                })
            
            # Find existing tax
            existing_tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'purchase'),
                ('amount_type', '=', 'percent'),
                ('amount', '>=', calculated_tax_rate - 0.5),
                ('amount', '<=', calculated_tax_rate + 0.5),
            ], limit=1)
            
            if existing_tax:
                tax_ids = [(6, 0, [existing_tax.id])]
                _logger.info(f"Found existing tax: {existing_tax.name} ({existing_tax.amount}%)")
            else:
                # Create new tax
                try:
                    new_tax = self.env['account.tax'].sudo().create({
                        'name': f'Purchase Tax {calculated_tax_rate}%',
                        'type_tax_use': 'purchase',
                        'amount_type': 'percent',
                        'amount': calculated_tax_rate,
                        'description': f'Auto-created from OCR refund ({calculated_tax_rate}%)',
                        'tax_group_id': tax_group.id,
                    })
                    tax_ids = [(6, 0, [new_tax.id])]
                    _logger.info(f"Created new tax: {new_tax.name}")
                except Exception as e:
                    _logger.warning(f"Could not create tax: {e}")
        
        # Build Credit Note lines from wizard line items
        credit_note_lines = []
        
        if self.line_ids:
            # Use the extracted line items
            for line in self.line_ids:
                line_vals = {
                    'name': line.description,
                    'quantity': line.quantity,
                    'price_unit': line.unit_price,
                    'discount': line.discount,
                }
                if tax_ids:
                    line_vals['tax_ids'] = tax_ids
                credit_note_lines.append((0, 0, line_vals))
        else:
            # Fallback: single line with total
            description = f"Refund: {self.ticket_number}"
            if self.passenger_name:
                description += f" - {self.passenger_name}"
            if self.flight_details:
                description += f" ({self.flight_details})"
            
            line_vals = {
                'name': description,
                'quantity': 1,
                'price_unit': self.subtotal if self.subtotal > 0 else self.total_amount,
            }
            if tax_ids:
                line_vals['tax_ids'] = tax_ids
            credit_note_lines.append((0, 0, line_vals))
        
        # Create Credit Note (in_refund = Vendor Credit Note)
        credit_note_vals = {
            'move_type': 'in_refund',
            'partner_id': self.vendor_id.id,
            'ref': self.ticket_number,
            'invoice_date': self.invoice_date or fields.Date.today(),
            'currency_id': self.currency_id.id,
            'invoice_line_ids': credit_note_lines,
            'narration': self.refund_reason,
        }
        
        credit_note = self.env['account.move'].create(credit_note_vals)
        _logger.info(f"Created Credit Note: {credit_note.name} with {len(credit_note_lines)} lines, total: {credit_note.amount_total}")
        
        # ==================== CREATE REFUND TRACKING RECORD ====================
        refund_vals = {
            'ticket_number': self.ticket_number,
            'vendor_id': self.vendor_id.id,
            'passenger_name': self.passenger_name,
            'flight_details': self.flight_details,
            'refund_reason': self.refund_reason,
            'refund_amount': self.total_amount,
            'currency_id': self.currency_id.id,
            'original_bill_id': self.original_bill_id.id if self.original_bill_id else False,
            'credit_note_id': credit_note.id,  # Link to created Credit Note
            'request_date': self.invoice_date or fields.Date.today(),
            'state': 'credited',  # Since we created Credit Note, mark as credited
            'credit_received_date': fields.Date.today(),
            'ocr_document': self.invoice_file,
            'ocr_filename': self.filename,
            'raw_ocr_data': self.raw_ocr_text,
        }
        
        refund = self.env['af.refund.tracking'].create(refund_vals)
        
        self.created_refund_id = refund.id
        self.state = 'done'
        
        # Return action to open the created Credit Note
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': credit_note.id,
            'view_mode': 'form',
            'target': 'current',
        }


class VendorBillWizardLine(models.TransientModel):
    _name = 'af.vendor.bill.wizard.line'
    _description = 'Vendor Bill Wizard Line'
    
    wizard_id = fields.Many2one(
        'af.vendor.bill.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    description = fields.Char(string='Description', required=True)
    quantity = fields.Float(string='Quantity', default=1)
    unit_price = fields.Float(string='Unit Price')
    discount = fields.Float(string='Discount (%)', default=0.0,
                            help='Discount percentage (0-100)')
    total = fields.Float(string='Total', compute='_compute_total', store=True)
    
    @api.depends('quantity', 'unit_price', 'discount')
    def _compute_total(self):
        for line in self:
            subtotal = line.quantity * line.unit_price
            line.total = subtotal * (1 - line.discount / 100) if line.discount else subtotal


class VendorBillWizardColumn(models.TransientModel):
    _name = 'af.vendor.bill.wizard.column'
    _description = 'Extracted Column for Match Selection'
    _rec_name = 'display_label'

    wizard_id = fields.Many2one(
        'af.vendor.bill.wizard',
        string='Wizard',
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
