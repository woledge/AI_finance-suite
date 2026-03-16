# -*- coding: utf-8 -*-
"""
CFO Query Wizard
================

Wizard for asking questions to the Virtual CFO.
"""

from odoo import models, fields, api


class CFOQueryWizard(models.TransientModel):
    _name = 'af.cfo.query.wizard'
    _description = 'Virtual CFO Query Wizard'

    cfo_agent_id = fields.Many2one('af.virtual.cfo.agent', string='CFO Session')
    
    question = fields.Text(string='Your Question', required=True,
                           help='Ask any financial question in English or Arabic')
    
    # Suggested questions
    suggested_question = fields.Selection([
        ('revenue', 'What are our total sales this month?'),
        ('expenses', 'What are our major expenses?'),
        ('cashflow', 'What is our current cash position?'),
        ('overdue', 'Which customers have overdue payments?'),
        ('profit', 'What is our profit margin?'),
        ('custom', 'Custom Question'),
    ], string='Quick Questions', default='custom')
    
    answer = fields.Html(string='Answer', readonly=True)
    show_answer = fields.Boolean(string='Show Answer', default=False)

    @api.onchange('suggested_question')
    def _onchange_suggested_question(self):
        if self.suggested_question and self.suggested_question != 'custom':
            questions = {
                'revenue': 'What are our total sales this month compared to last month?',
                'expenses': 'What are our top 5 expense categories this month?',
                'cashflow': 'What is our current cash position and working capital?',
                'overdue': 'Which customers have overdue payments and how much do they owe?',
                'profit': 'What is our overall profit margin and how does it compare to previous periods?',
            }
            self.question = questions.get(self.suggested_question, '')

    def action_ask(self):
        """Send question to Virtual CFO."""
        self.ensure_one()
        
        # Get or create CFO agent
        if not self.cfo_agent_id:
            self.cfo_agent_id = self.env['af.virtual.cfo.agent'].create({})
        
        # Ask the question
        result = self.cfo_agent_id.ask_question(self.question)
        
        if result.get('success'):
            self.answer = result.get('answer', '')
            self.show_answer = True
            
            return {
                'type': 'ir.actions.act_window',
                'name': 'Virtual CFO Response',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': result.get('error', 'Unknown error'),
                    'type': 'danger',
                }
            }

    def action_new_question(self):
        """Reset for a new question."""
        self.ensure_one()
        self.write({
            'question': '',
            'answer': '',
            'show_answer': False,
            'suggested_question': 'custom',
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Ask Virtual CFO',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
