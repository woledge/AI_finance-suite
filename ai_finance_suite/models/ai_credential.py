# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class AICredential(models.Model):
    _name = 'af.credential'
    _description = 'AI Service Credential'
    _order = 'name'

    name = fields.Char(string='Credential Name', required=True, copy=False)
    provider = fields.Selection([
        ('gemini', 'Google Gemini'),
        ('openai', 'OpenAI'),
        ('claude', 'Anthropic Claude'),
        ('xai', 'xAI Grok'),
        ('mistral', 'Mistral AI'),
        ('cohere', 'Cohere'),
        ('groq', 'Groq'),
        ('deepseek', 'DeepSeek'),
        ('custom', 'Custom / Self-Hosted'),
    ], string='AI Provider', required=True, default='gemini')
    
    api_key = fields.Char(string='API Key', groups='account.group_account_manager,base.group_system')
    
    api_base_url = fields.Char(
        string='API Base URL',
        help='Your hosted LLM server API endpoint URL '
             '(e.g., https://your-server.com/v1 or https://your-domain:8000/v1). '
             'Must be an OpenAI-compatible API. Only used for Custom provider.'
    )
    
    anonymize_data = fields.Boolean(
        string='Anonymize Financial Data',
        default=False,
        help='When enabled, real company/customer/vendor names are replaced with codes '
             'before sending to the AI provider. Protects sensitive business data.'
    )
    
    # ---- Per-provider model selection ----
    gemini_model = fields.Selection([
        # Gemini 3 Series (Latest)
        ('gemini-3.1-pro', 'Gemini 3.1 Pro — Most Intelligent'),
        ('gemini-3-flash', 'Gemini 3 Flash — Fast + Powerful'),
        ('gemini-3-pro', 'Gemini 3 Pro — Advanced Reasoning'),
        # Gemini 2.5 Series (Stable)
        ('gemini-2.5-flash', 'Gemini 2.5 Flash (Recommended)'),
        ('gemini-2.5-pro', 'Gemini 2.5 Pro'),
        ('gemini-2.5-flash-lite', 'Gemini 2.5 Flash-Lite — Low Cost'),
        # Gemini 2.0 Series
        ('gemini-2.0-flash', 'Gemini 2.0 Flash'),
        ('gemini-2.0-flash-lite', 'Gemini 2.0 Flash-Lite'),
    ], string='Gemini Model')
    
    openai_model = fields.Selection([
        # GPT-5 Series (Latest)
        ('gpt-5.2', 'GPT-5.2 — Leading Reasoning'),
        ('gpt-5', 'GPT-5 — Multimodal'),
        # o-Series (Reasoning)
        ('o3', 'o3 — Advanced Reasoning'),
        ('o3-mini', 'o3 Mini — Fast Reasoning'),
        ('o4-mini', 'o4 Mini'),
        ('o1', 'o1'),
        # GPT-4 Series (Stable)
        ('gpt-4.1', 'GPT-4.1 — Best for Code'),
        ('gpt-4.1-mini', 'GPT-4.1 Mini — Fast + Affordable'),
        ('gpt-4o', 'GPT-4o (Recommended)'),
        ('gpt-4o-mini', 'GPT-4o Mini'),
        ('gpt-4-turbo', 'GPT-4 Turbo'),
    ], string='OpenAI Model')
    
    groq_model = fields.Selection([
        # OpenAI GPT-OSS (Latest on Groq)
        ('openai/gpt-oss-120b', 'GPT-OSS 120B — Flagship Open-Weight'),
        ('openai/gpt-oss-20b', 'GPT-OSS 20B'),
        # Meta Llama 4 Series
        ('llama-4-maverick-17b-128e-instruct', 'Llama 4 Maverick 17B'),
        ('llama-4-scout-17b-16e-instruct', 'Llama 4 Scout 17B'),
        # Meta Llama 3 Series (Stable)
        ('llama-3.3-70b-versatile', 'Llama 3.3 70B (Recommended)'),
        ('llama-3.1-8b-instant', 'Llama 3.1 8B Instant — Fastest'),
        # Qwen Series
        ('qwen/qwen3-32b', 'Qwen 3 32B'),
        # Moonshot
        ('moonshotai/kimi-k2-0905', 'Kimi K2'),
    ], string='Groq Model')
    
    deepseek_model = fields.Selection([
        # V3 Series (Latest)
        ('deepseek-chat', 'DeepSeek V3 (Recommended)'),
        # R1 Reasoning Series
        ('deepseek-reasoner', 'DeepSeek R1 — Advanced Reasoning'),
    ], string='DeepSeek Model')
    
    claude_model = fields.Selection([
        # Claude 4.6 Series (Latest - Feb 2026)
        ('claude-sonnet-4-6-20260217', 'Claude Sonnet 4.6 — Latest (Recommended)'),
        ('claude-opus-4-6-20260205', 'Claude Opus 4.6 — Best Reasoning'),
        # Claude 4.5 Series
        ('claude-opus-4-5-20251124', 'Claude Opus 4.5 — Powerful'),
        ('claude-sonnet-4-5-20250929', 'Claude Sonnet 4.5 — Fast + Capable'),
        ('claude-haiku-4-5-20251015', 'Claude Haiku 4.5 — Fastest'),
        # Claude 4 Series
        ('claude-opus-4-20250522', 'Claude Opus 4 — Stable'),
        ('claude-sonnet-4-20250514', 'Claude Sonnet 4'),
    ], string='Claude Model')
    
    xai_model = fields.Selection([
        # Grok 4 Series (Latest)
        ('grok-4', 'Grok 4 — Most Capable'),
        ('grok-4-0709', 'Grok 4 (0709)'),
        ('grok-3', 'Grok 3'),
        ('grok-3-fast', 'Grok 3 Fast (Recommended)'),
        ('grok-3-mini', 'Grok 3 Mini — Budget'),
        ('grok-3-mini-fast', 'Grok 3 Mini Fast — Fastest'),
    ], string='xAI Model')
    
    mistral_model = fields.Selection([
        # Latest Models
        ('mistral-medium-latest', 'Mistral Medium 3 (Recommended)'),
        ('mistral-large-latest', 'Mistral Large — Most Capable'),
        ('mistral-small-latest', 'Mistral Small — Fast + Affordable'),
        ('codestral-latest', 'Codestral — Best for Code'),
        ('open-mistral-nemo', 'Mistral Nemo — Open Weight'),
        ('ministral-8b-latest', 'Ministral 8B — Lightweight'),
    ], string='Mistral Model')
    
    cohere_model = fields.Selection([
        # Command Series (Latest)
        ('command-a-08-2025', 'Command A (Recommended)'),
        ('command-r-plus-08-2024', 'Command R+ — Advanced RAG'),
        ('command-r-08-2024', 'Command R — Fast'),
        ('command-r7b-12-2024', 'Command R7B — Lightweight'),
        ('command-light', 'Command Light — Budget'),
    ], string='Cohere Model')
    
    custom_model_name = fields.Char(
        string='Custom Model Name',
        help='Model name for custom provider (e.g., llama3, mixtral, mistral, '
             'qwen2.5, codellama, phi3). Only used when provider is Custom / Self-Hosted.'
    )
    
    # Keep model_version for backward compatibility (old records)
    model_version = fields.Selection(
        selection='_get_model_selection',
        string='Model Version (Legacy)',
    )
    
    last_tested_date = fields.Datetime(string='Last Tested On', readonly=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('valid', 'Valid'),
        ('invalid', 'Invalid'),
    ], string='Status', default='draft', readonly=True)
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Credential name must be unique!')
    ]
    
    @api.model
    def _get_model_selection(self):
        """Legacy method - kept for backward compatibility with old records."""
        return [
            # Gemini
            ('gemini-3.1-pro', 'Gemini 3.1 Pro'),
            ('gemini-3-flash', 'Gemini 3 Flash'),
            ('gemini-3-pro', 'Gemini 3 Pro'),
            ('gemini-2.5-flash', 'Gemini 2.5 Flash'),
            ('gemini-2.5-pro', 'Gemini 2.5 Pro'),
            ('gemini-2.5-flash-lite', 'Gemini 2.5 Flash-Lite'),
            ('gemini-2.0-flash', 'Gemini 2.0 Flash'),
            ('gemini-2.0-flash-lite', 'Gemini 2.0 Flash-Lite'),
            ('gemini-1.5-flash', 'Gemini 1.5 Flash'),
            ('gemini-1.5-pro', 'Gemini 1.5 Pro'),
            # OpenAI
            ('gpt-5.2', 'GPT-5.2'),
            ('gpt-5', 'GPT-5'),
            ('o3', 'o3'),
            ('o3-mini', 'o3 Mini'),
            ('o4-mini', 'o4 Mini'),
            ('o1', 'o1'),
            ('gpt-4.1', 'GPT-4.1'),
            ('gpt-4.1-mini', 'GPT-4.1 Mini'),
            ('gpt-4o', 'GPT-4o'),
            ('gpt-4o-mini', 'GPT-4o Mini'),
            ('gpt-4-turbo', 'GPT-4 Turbo'),
            ('gpt-4', 'GPT-4'),
            ('gpt-3.5-turbo', 'GPT-3.5 Turbo'),
            ('o1-mini', 'o1 Mini'),
            # Groq
            ('openai/gpt-oss-120b', 'GPT-OSS 120B'),
            ('openai/gpt-oss-20b', 'GPT-OSS 20B'),
            ('llama-4-maverick-17b-128e-instruct', 'Llama 4 Maverick'),
            ('llama-4-scout-17b-16e-instruct', 'Llama 4 Scout'),
            ('llama-3.3-70b-versatile', 'Llama 3.3 70B'),
            ('llama-3.1-8b-instant', 'Llama 3.1 8B'),
            ('llama-3.1-70b-versatile', 'Llama 3.1 70B'),
            ('mixtral-8x7b-32768', 'Mixtral 8x7B'),
            ('gemma2-9b-it', 'Gemma 2 9B'),
            ('llama-guard-3-8b', 'Llama Guard 3 8B'),
            ('qwen/qwen3-32b', 'Qwen 3 32B'),
            ('moonshotai/kimi-k2-0905', 'Kimi K2'),
            # DeepSeek
            ('deepseek-chat', 'DeepSeek V3'),
            ('deepseek-reasoner', 'DeepSeek R1'),
            # Claude
            ('claude-sonnet-4-6-20260217', 'Claude Sonnet 4.6'),
            ('claude-opus-4-6-20260205', 'Claude Opus 4.6'),
            ('claude-opus-4-5-20251124', 'Claude Opus 4.5'),
            ('claude-sonnet-4-5-20250929', 'Claude Sonnet 4.5'),
            ('claude-haiku-4-5-20251015', 'Claude Haiku 4.5'),
            ('claude-opus-4-20250522', 'Claude Opus 4'),
            ('claude-sonnet-4-20250514', 'Claude Sonnet 4'),
            # xAI Grok
            ('grok-4', 'Grok 4'),
            ('grok-4-0709', 'Grok 4 (0709)'),
            ('grok-3', 'Grok 3'),
            ('grok-3-fast', 'Grok 3 Fast'),
            ('grok-3-mini', 'Grok 3 Mini'),
            ('grok-3-mini-fast', 'Grok 3 Mini Fast'),
            # Mistral
            ('mistral-medium-latest', 'Mistral Medium 3'),
            ('mistral-large-latest', 'Mistral Large'),
            ('mistral-small-latest', 'Mistral Small'),
            ('codestral-latest', 'Codestral'),
            ('open-mistral-nemo', 'Mistral Nemo'),
            ('ministral-8b-latest', 'Ministral 8B'),
            # Cohere
            ('command-a-08-2025', 'Command A'),
            ('command-r-plus-08-2024', 'Command R+'),
            ('command-r-08-2024', 'Command R'),
            ('command-r7b-12-2024', 'Command R7B'),
            ('command-light', 'Command Light'),
        ]
    
    def get_effective_model(self):
        """Return the active model name based on the selected provider."""
        self.ensure_one()
        if self.provider == 'gemini':
            return self.gemini_model or self.model_version
        elif self.provider == 'openai':
            return self.openai_model or self.model_version
        elif self.provider == 'claude':
            return self.claude_model or self.model_version
        elif self.provider == 'xai':
            return self.xai_model or self.model_version
        elif self.provider == 'mistral':
            return self.mistral_model or self.model_version
        elif self.provider == 'cohere':
            return self.cohere_model or self.model_version
        elif self.provider == 'groq':
            return self.groq_model or self.model_version
        elif self.provider == 'deepseek':
            return self.deepseek_model or self.model_version
        elif self.provider == 'custom':
            return self.custom_model_name
        return self.model_version
    
    @api.onchange('provider')
    def _onchange_provider(self):
        """Reset model selections when provider changes."""
        self.gemini_model = False
        self.openai_model = False
        self.claude_model = False
        self.xai_model = False
        self.mistral_model = False
        self.cohere_model = False
        self.groq_model = False
        self.deepseek_model = False
        self.custom_model_name = False
        self.model_version = False
        self.status = 'draft'

    def action_test_connection(self):
        """Test the API connection with a lightweight request."""
        self.ensure_one()
        
        effective_model = self.get_effective_model()
        
        try:
            success = False
            error_msg = ""
            
            if self.provider == 'gemini':
                success, error_msg = self._test_gemini(effective_model)
            elif self.provider == 'openai':
                success, error_msg = self._test_openai(effective_model)
            elif self.provider == 'groq':
                success, error_msg = self._test_groq(effective_model)
            elif self.provider == 'claude':
                success, error_msg = self._test_claude(effective_model)
            elif self.provider == 'xai':
                success, error_msg = self._test_xai(effective_model)
            elif self.provider == 'mistral':
                success, error_msg = self._test_mistral(effective_model)
            elif self.provider == 'cohere':
                success, error_msg = self._test_cohere(effective_model)
            elif self.provider == 'deepseek':
                success, error_msg = self._test_deepseek(effective_model)
            elif self.provider == 'custom':
                success, error_msg = self._test_custom(effective_model)
            else:
                error_msg = "Provider testing not implemented."
            
            if success:
                self.write({
                    'status': 'valid',
                    'last_tested_date': fields.Datetime.now()
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Successfully connected to %s using model %s') % (self.provider, effective_model),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                self.status = 'invalid'
                raise UserError(_('Connection Failed: %s') % error_msg)
                
        except Exception as e:
            self.status = 'invalid'
            raise UserError(_('Test Error: %s') % str(e))

    def _test_gemini(self, model):
        """Test Google Gemini API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
        headers = {'Content-Type': 'application/json'}
        data = {
            "contents": [{"parts": [{"text": "Hello"}]}]
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    def _test_openai(self, model):
        """Test OpenAI API."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    def _test_groq(self, model):
        """Test Groq API."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    def _test_deepseek(self, model):
        """Test DeepSeek API."""
        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "Hello!"}],
            "stream": False
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    def _test_claude(self, model):
        """Test Anthropic Claude API."""
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "max_tokens": 10,
            "messages": [{"role": "user", "content": "Hello"}]
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    def _test_xai(self, model):
        """Test xAI Grok API (OpenAI-compatible)."""
        url = "https://api.x.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    def _test_mistral(self, model):
        """Test Mistral AI API."""
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    def _test_cohere(self, model):
        """Test Cohere API."""
        url = "https://api.cohere.com/v2/chat"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": model,
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except Exception as e:
            return False, str(e)

    def _test_custom(self, model):
        """Test Custom / Self-Hosted LLM API (OpenAI-compatible)."""
        if not self.api_base_url:
            return False, "Please enter your API Base URL (e.g., https://your-server.com/v1)"
        base_url = self.api_base_url
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data = {
            "model": model or 'llama3',
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 5
        }
        try:
            response = requests.post(url, headers=headers, json=data, timeout=15)
            if response.status_code == 200:
                return True, ""
            else:
                return False, f"Status {response.status_code}: {response.text}"
        except requests.exceptions.ConnectionError:
            return False, f"Cannot connect to {base_url}. Make sure your LLM server is running."
        except Exception as e:
            return False, str(e)
