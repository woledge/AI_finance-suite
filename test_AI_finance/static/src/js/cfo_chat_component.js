/** @odoo-module **/

import { Component, useState, useRef, onMounted, markup } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";

/**
 * Virtual CFO Chat Component
 * ChatGPT-style interface with history sidebar
 */
export class VirtualCFOChat extends Component {
    static template = "test_AI_finance.VirtualCFOChat";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            messages: [],
            inputText: "",
            isLoading: false,
            cfoAgentId: null,
            showSuggestions: true,
            showSidebar: true,
            chatSessions: [],
            currentSessionName: "New Chat",
        });

        this.chatContainerRef = useRef("chatContainer");
        this.inputRef = useRef("chatInput");

        // Bind methods to preserve 'this' context
        this.askSales = this.askSales.bind(this);
        this.askExpenses = this.askExpenses.bind(this);
        this.askCashPosition = this.askCashPosition.bind(this);
        this.askOverdue = this.askOverdue.bind(this);
        this.askProfit = this.askProfit.bind(this);
        this.newChat = this.newChat.bind(this);
        this.toggleSidebar = this.toggleSidebar.bind(this);
        this.copyMessage = this.copyMessage.bind(this);
        this.retryLastMessage = this.retryLastMessage.bind(this);

        // Load data on mount
        onMounted(() => {
            this.loadChatSessions();
        });
    }

    async loadChatSessions() {
        try {
            // Get all CFO agent sessions
            const sessions = await this.orm.searchRead(
                "test.ai.virtual.cfo.agent",
                [],
                ["id", "name", "create_date", "query_count"],
                { order: "create_date desc", limit: 20 }
            );

            this.state.chatSessions = sessions.map(s => ({
                id: s.id,
                name: s.name || `Session ${s.id}`,
                date: new Date(s.create_date).toLocaleDateString(),
                queryCount: s.query_count || 0,
            }));

            // Load most recent session or create new
            if (sessions.length > 0) {
                await this.loadSession(sessions[0].id);
            } else {
                await this.createNewSession();
            }
        } catch (error) {
            console.error("Failed to load chat sessions:", error);
            await this.createNewSession();
        }
    }

    async createNewSession() {
        try {
            const newId = await this.orm.create("test.ai.virtual.cfo.agent", [{}]);
            this.state.cfoAgentId = newId[0];
            this.state.messages = [];
            this.state.showSuggestions = true;
            this.state.currentSessionName = "New Chat";

            // Reload sessions
            await this.loadChatSessions();

            // Add welcome message - REMOVED to show Empty State
            // this.addSystemMessage(
            //     "👋 مرحباً! أنا المدير المالي الافتراضي.\n\n" +
            //     "Hello! I'm your Virtual CFO. Ask me anything about:\n\n" +
            //     "• Sales & Revenue\n• Expenses & Costs\n• Cash Flow\n" +
            //     "• Customer Payments\n• Profit Analysis"
            // );
        } catch (error) {
            console.error("Failed to create new session:", error);
        }
    }

    async loadSession(sessionId) {
        if (!sessionId) return;

        this.state.cfoAgentId = sessionId;
        this.state.messages = [];
        this.state.showSuggestions = false;

        try {
            // Get session name
            const session = this.state.chatSessions.find(s => s.id === sessionId);
            this.state.currentSessionName = session ? session.name : `Session ${sessionId}`;

            // Load conversation history
            const conversations = await this.orm.searchRead(
                "test.ai.cfo.conversation",
                [["cfo_agent_id", "=", sessionId]],
                ["question", "answer", "state", "create_date"],
                { order: "create_date asc", limit: 50 }
            );

            for (const conv of conversations) {
                if (conv.question) {
                    this.state.messages.push({
                        type: "user",
                        content: conv.question,
                        timestamp: conv.create_date,
                    });
                }
                if (conv.answer && conv.state === "completed") {
                    this.state.messages.push({
                        type: "assistant",
                        content: conv.answer,
                        timestamp: conv.create_date,
                    });
                }
            }

            // Show suggestions if no messages
            if (this.state.messages.length === 0) {
                this.state.showSuggestions = true;
            }

            this.scrollToBottom();
        } catch (error) {
            console.error("Failed to load session:", error);
        }
    }

    async deleteSession(sessionId, event) {
        // Stop propagation to prevent selecting the session
        if (event) {
            event.stopPropagation();
        }

        try {
            // Don't delete if only one session
            if (this.state.chatSessions.length <= 1) {
                this.notification.add("Cannot delete the last chat session", { type: "warning" });
                return;
            }

            // Delete the session
            await this.orm.unlink("test.ai.virtual.cfo.agent", [sessionId]);

            // If we deleted the current session, switch to another
            if (sessionId === this.state.cfoAgentId) {
                const remaining = this.state.chatSessions.filter(s => s.id !== sessionId);
                if (remaining.length > 0) {
                    await this.loadSession(remaining[0].id);
                }
            }

            // Reload sessions list
            await this.loadChatSessions();

            this.notification.add("Chat deleted", { type: "success" });
        } catch (error) {
            console.error("Failed to delete session:", error);
            this.notification.add("Failed to delete chat", { type: "danger" });
        }
    }

    async newChat() {
        await this.createNewSession();
    }

    async selectSession(sessionId) {
        await this.loadSession(sessionId);
    }

    toggleSidebar() {
        this.state.showSidebar = !this.state.showSidebar;
    }

    addSystemMessage(content) {
        this.state.messages.push({
            type: "system",
            content: content,
            timestamp: new Date().toISOString(),
        });
        this.scrollToBottom();
    }

    async sendMessage() {
        const text = this.state.inputText.trim();
        if (!text || this.state.isLoading) return;

        // Hide suggestions after first message
        this.state.showSuggestions = false;

        // Add user message
        this.state.messages.push({
            type: "user",
            content: text,
            timestamp: new Date().toISOString(),
        });

        this.state.inputText = "";
        this.state.isLoading = true;
        this.scrollToBottom();

        try {
            // Call the Virtual CFO
            const result = await this.orm.call(
                "test.ai.virtual.cfo.agent",
                "ask_question",
                [[this.state.cfoAgentId], text]
            );

            if (result.success) {
                this.state.messages.push({
                    type: "assistant",
                    content: result.answer,
                    timestamp: new Date().toISOString(),
                });
            } else {
                this.state.messages.push({
                    type: "error",
                    content: "❌ " + (result.error || "Failed to get response"),
                    timestamp: new Date().toISOString(),
                });
            }

            // Update session in sidebar
            await this.loadChatSessions();
        } catch (error) {
            console.error("CFO query failed:", error);
            this.state.messages.push({
                type: "error",
                content: "❌ Network error. Please try again.",
                timestamp: new Date().toISOString(),
            });
        } finally {
            this.state.isLoading = false;
            this.scrollToBottom();
        }
    }

    // Individual suggestion handlers
    askSales() {
        this.state.inputText = "What are our total sales this month?";
        this.sendMessage();
    }

    askExpenses() {
        this.state.inputText = "What are our major expenses?";
        this.sendMessage();
    }

    askCashPosition() {
        this.state.inputText = "What is our current cash position?";
        this.sendMessage();
    }

    askOverdue() {
        this.state.inputText = "Which customers have overdue payments?";
        this.sendMessage();
    }

    askProfit() {
        this.state.inputText = "What is our profit margin?";
        this.sendMessage();
    }

    onKeyDown(event) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            this.sendMessage();
        }
    }

    scrollToBottom() {
        setTimeout(() => {
            const container = this.chatContainerRef.el;
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        }, 100);
    }

    clearHistory() {
        this.state.messages = [];
        this.state.showSuggestions = true;
    }

    async copyMessage(messageIndex) {
        const message = this.state.messages[messageIndex];
        if (!message) return;

        // Get plain text from content (strip HTML tags if any)
        let text = message.content || '';
        if (text.includes('<') && text.includes('>')) {
            text = text.replace(/<[^>]+>/g, '');
        }

        try {
            await navigator.clipboard.writeText(text);
            this.notification.add("Response copied to clipboard", { type: "success" });
        } catch (err) {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            this.notification.add("Response copied to clipboard", { type: "success" });
        }
    }

    async retryLastMessage() {
        // Find the last user message before the error
        let lastUserMsg = null;
        for (let i = this.state.messages.length - 1; i >= 0; i--) {
            if (this.state.messages[i].type === 'user') {
                lastUserMsg = this.state.messages[i].content;
                break;
            }
        }

        if (!lastUserMsg) return;

        // Remove the error message(s)
        while (this.state.messages.length > 0 &&
            this.state.messages[this.state.messages.length - 1].type === 'error') {
            this.state.messages.pop();
        }
        // Remove the last user message too (we'll resend it)
        if (this.state.messages.length > 0 &&
            this.state.messages[this.state.messages.length - 1].type === 'user') {
            this.state.messages.pop();
        }

        // Resend
        this.state.inputText = lastUserMsg;
        await this.sendMessage();
    }

    formatMessage(content) {
        if (!content) return "";

        let text = content;

        // If it contains HTML, convert to plain text
        if (text.includes("<") && text.includes(">")) {
            text = text
                .replace(/<br\s*\/?>/gi, "\n")
                .replace(/<\/p>/gi, "\n\n")
                .replace(/<\/li>/gi, "\n")
                .replace(/<\/h[1-6]>/gi, "\n\n")
                .replace(/<strong>(.*?)<\/strong>/gi, "**$1**")
                .replace(/<b>(.*?)<\/b>/gi, "**$1**")
                .replace(/<em>(.*?)<\/em>/gi, "_$1_")
                .replace(/<i>(.*?)<\/i>/gi, "_$1_")
                .replace(/<li>/gi, "• ")
                .replace(/<[^>]+>/g, "");
        }

        // Convert markdown to HTML
        let html = text
            .replace(/^### (.*$)/gm, '<h5 class="msg-header">$1</h5>')
            .replace(/^## (.*$)/gm, '<h4 class="msg-header">$1</h4>')
            .replace(/^# (.*$)/gm, '<h3 class="msg-header">$1</h3>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/_(.*?)_/g, '<em>$1</em>')
            .replace(/^• (.*)$/gm, '<div class="msg-bullet">• $1</div>')
            .replace(/^- (.*)$/gm, '<div class="msg-bullet">• $1</div>')
            .replace(/^(\d+)\. (.*)$/gm, '<div class="msg-bullet"><strong>$1.</strong> $2</div>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br/>');

        html = '<p>' + html + '</p>';

        return markup(html);
    }
}

// Register the component as an action
registry.category("actions").add("test_virtual_cfo_chat", VirtualCFOChat);
