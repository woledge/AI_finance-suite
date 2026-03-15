# -*- coding: utf-8 -*-
"""
AI Finance Configuration
========================

Stores API keys and configuration for AI services.
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import logging
import json
import os

_logger = logging.getLogger(__name__)


class AIFinanceConfig(models.TransientModel):  # Inherit TransientModel for res.config.settings
    _inherit = 'res.config.settings'
    _description = 'AI Finance Configuration (Test)'

    # name = fields.Char(string='Configuration Name', default='Default', required=True)
    # active = fields.Boolean(default=True)
    # company_id = fields.Many2one('res.company', string='Company', 
    #                               default=lambda self: self.env.company)

    # Credential References
    ocr_credential_id = fields.Many2one('test.ai.credential', string='OCR AI Credential',
                                      config_parameter='test_AI_finance.ocr_credential_id',
                                      help='Credential to use for OCR/VLM processing')
                                      
    virtual_cfo_credential_id = fields.Many2one('test.ai.credential', string='Virtual CFO AI Credential',
                                              config_parameter='test_AI_finance.virtual_cfo_credential_id',
                                              help='Credential to use for Virtual CFO Chat')

    # Removed individual API key fields as they are now managed via credentials

    # Alert Settings (Removed legacy unused thresholds)

    @api.model
    def default_get(self, fields_list):
        """Override default_get to ensure correct default model."""
        res = super().default_get(fields_list)
        # Removed default override to respect user selection
        return res

    @api.model
    def get_config(self):
        """Get the active configuration for current company."""
        # For ResConfigSettings, we get values from config parameters
        ICP = self.env['ir.config_parameter'].sudo()
        config = {
            'llm_provider': False,
            'llm_api_key': False,
            'llm_model': False,
            'ocr_provider': False, # No default provider until set by user
            'ocr_api_key': False,
            'vlm_provider': False,
            'gemini_api_key': False,
            'gemini_model': False,
            'groq_api_key': False,
        }
        
        # Get OCR Credential
        ocr_cred_id = int(ICP.get_param('test_AI_finance.ocr_credential_id', 0))
        if ocr_cred_id:
            ocr_cred = self.env['test.ai.credential'].browse(ocr_cred_id)
            if ocr_cred.exists():
                config['ocr_provider'] = ocr_cred.provider
                config['ocr_api_key'] = ocr_cred.api_key
                
                # Check for VLM Capability (Currently only Gemini)
                if ocr_cred.provider == 'gemini':
                    config['vlm_provider'] = 'gemini'
                    config['gemini_api_key'] = ocr_cred.api_key
                    config['gemini_model'] = ocr_cred.get_effective_model()
                else:
                    # Provide a hint that the selected provider is not VLM compatible
                    config['vlm_provider'] = False

        # Get Virtual CFO Credential
        cfo_cred_id = int(ICP.get_param('test_AI_finance.virtual_cfo_credential_id', 0))
        if cfo_cred_id:
            cfo_cred = self.env['test.ai.credential'].browse(cfo_cred_id)
            if cfo_cred.exists():
                config['llm_provider'] = cfo_cred.provider
                config['llm_api_key'] = cfo_cred.api_key
                config['llm_model'] = cfo_cred.get_effective_model()
                
                # Update specific keys for compatibility
                if cfo_cred.provider == 'groq':
                    config['groq_api_key'] = cfo_cred.api_key
        
        # Return as an object for compatibility
        return type('AIConfig', (object,), config)()

    # Removed test methods (test_llm_connection, test_ocr_connection, fields_view_get, action_fix_deprecated_model)
    # as they complicate the simplified module structure and rely on specific view interactions.
    # The config is now handled via standard res.config.settings.
