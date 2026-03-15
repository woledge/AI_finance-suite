# AI Finance V1 for Odoo 19 🤖💼

**AI Finance V1** is a cutting-edge Odoo module designed to seamlessly merge Artificial Intelligence with your accounting workflow. By integrating world-class Large Language Models (LLMs) and Vision-Language Models (VLMs), this module automates data entry and brings a conversational financial assistant straight to your fingertips.

---

## ⚡ Core Capabilities

### 1. 🔍 Vision-Powered OCR Engine
Say goodbye to manual data entry. Our hybrid OCR+VLM engine intelligently parses financial documents with unmatched accuracy.
- **Supported Documents:** Vendor Bills, Receipts, Partner Statements, Bank Statements, and Refund Tickets.
- **Supported Formats:** PDF, JPG, PNG, and Excel (XLSX).
- **Smart Extraction:** Automatically identifies Vendors, Total Amounts, Currencies, Reference Numbers, and Tax information.
- **Fail-safe Logic:** Intelligently processes document content via powerful VLMs (like Gemini Flash, GPT-4o, or Claude).
- **Automated Workflows:** Extracts line-items from statements and automatically attempts intelligent voucher reconciliation against recorded payments and invoices.

### 2. 💬 Virtual CFO (Chatbot)
Your personal, intelligent financial analyst living right inside Odoo.
- **Natural Language Queries:** Ask questions like "What are my top 5 expenses this month?" or "How much do we owe Vendor X?"
- **Context Injection:** When opened while viewing a specific invoice or statement, the AI automatically reads the page context to offer tailored insights without needing extra prompts.
- **Model Choice:** Use reasoning and conversational models ranging from blazing fast (Groq, Haiku) to deeply analytical (Opus, GPT-4, DeepSeek).

### 3. 📊 OWL Analytics Dashboard
Interactive financial visualization using Odoo's OWL framework and Chart.js.
- **KPI Cards:** Track Sales, Gross Profit, Receivables, and Payables with trend indicators.
- **Dynamic Charts:** View 6-month Sales vs Purchases, Capital Map donuts, and Cash Flow Forecasts.
- **Smart Alerts:** Proactive warnings for negative cash positions and critical aging debts.
- **Top 5 Lists:** Instantly see your top customers by revenue, top overdue clients, and top vendors by spend.

### 4. 🔐 Secure AI Credential Hub
A centralized command center for your AI operations.
- **Plug-and-Play Providers:** Configure multiple API keys independently. Assign one provider for fast OCR tasks, and a different one for deep analytical Virtual CFO chats.
- **Encrypted Storage:** API keys are stored securely using Odoo's internal masking. 

---

## 🧠 Supported AI Providers
The module ships with natively built support for the 2026/2025 landscape of top-tier AI providers, allowing you to choose exactly what fits your budget and privacy needs.

- **Google Gemini** (Gemini 2.5/3.1 Pro/Flash) 
- **OpenAI** (GPT-5.2, GPT-4o, o1/o3-mini)
- **Anthropic Claude** (Opus & Sonnet 4.5/4.6 Series)
- **xAI Grok** (Grok 2.5/3)
- **Mistral AI** (Mistral Large 3/4)
- **Groq** (Llama 3.3/4 Maverick, Mixtral)
- **Cohere** (Command R/R+)
- **DeepSeek** (DeepSeek V3/R1)
- **Custom / Local** (Ollama support for complete data privacy)

---

## 🚀 Setup & Installation

### Requirements
Ensure your Odoo environment has the required Python libraries installed:
```bash
pip install groq openai google-genai pandas rapidfuzz
```

### Installation Steps
1. Place the `test_AI_finance` directory into your Odoo `addons_path`.
2. Restart the Odoo server.
3. Update your Odoo App List.
4. Search for **AI Finance V1** and click **Install**.

### Configuration
1. Navigate to **AI Finance V1 > Configuration > AI Credentials**.
2. Click **New** to add your API Key for your desired provider (e.g., Google or OpenAI) and select your preferred model version.
3. Go to **AI Finance V1 > Configuration > Settings**.
4. Link the saved AI Credentials to **OCR Operations** and **Virtual CFO Operations**.

---

## 🛠️ Module Structure 
- `models/`: Database structures for Credentials, Configurations, Document tracking, and AI Agents.
- `wizards/`: Interactive popups for generating Bills, asking the CFO questions, and uploading batch statements.
- `views/`: User interface definitions (XML) and the Dashboard structures.
- `static/`: Frontend javascript logic and custom styling for the chat interfaces.

---

## 🤝 Support & Contribution
Found an issue or want to request a feature? Please open an issue in the GitHub repository. Contributions are always welcome through Pull Requests!
