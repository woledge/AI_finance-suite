/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState, useRef } from "@odoo/owl";
import { loadJS } from "@web/core/assets";

export class AIFinanceAnalytics extends Component {
    setup() {
        this.action = useService("action");
        this.orm = useService("orm");

        this.state = useState({
            data: null,
            loading: true,
            // Filters
            partner_id: false,
            partner_name: "",
            journal_id: false,
            journal_name: "",
            period: "this_year",
            // Filter options
            partners: [],
            journals: [],
        });

        this.salesChartRef = useRef("salesChart");
        this.capitalChartRef = useRef("capitalChart");
        this.agingChartRef = useRef("agingChart");
        this.cashFlowChartRef = useRef("cashFlowChart");
        this._charts = [];

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadFilterOptions();
            await this.fetchData();
        });

        onMounted(() => {
            window.requestAnimationFrame(() => this.renderAllCharts());
        });

        onWillUnmount(() => this.destroyCharts());
    }

    async loadFilterOptions() {
        try {
            // Load partners (customers + vendors with invoices)
            const partners = await this.orm.searchRead("res.partner", [["is_company", "=", true]], ["name"], { limit: 100, order: "name asc" });
            this.state.partners = partners;

            // Load bank/cash journals
            const journals = await this.orm.searchRead("account.journal", [["type", "in", ["bank", "cash"]]], ["name"], { order: "name asc" });
            this.state.journals = journals;
        } catch (e) {
            console.error("Filter options error:", e);
        }
    }

    async fetchData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "test.ai.finance.dashboard", "get_dashboard_data", [],
                { partner_id: this.state.partner_id || false, journal_id: this.state.journal_id || false, period: this.state.period || "this_year" }
            );
        } catch (e) {
            console.error("Dashboard fetch error:", e);
        }
        this.state.loading = false;
    }

    async onRefresh() {
        this.destroyCharts();
        await this.fetchData();
        window.requestAnimationFrame(() => window.requestAnimationFrame(() => this.renderAllCharts()));
    }

    // Filter handlers
    onPartnerChange(ev) {
        const val = parseInt(ev.target.value);
        this.state.partner_id = val || false;
        this.state.partner_name = ev.target.options[ev.target.selectedIndex].text;
        this.onRefresh();
    }

    onJournalChange(ev) {
        const val = parseInt(ev.target.value);
        this.state.journal_id = val || false;
        this.state.journal_name = ev.target.options[ev.target.selectedIndex].text;
        this.onRefresh();
    }

    onPeriodChange(period) {
        this.state.period = period;
        this.onRefresh();
    }

    clearFilters() {
        this.state.partner_id = false;
        this.state.journal_id = false;
        this.state.period = "this_year";
        this.onRefresh();
    }

    destroyCharts() {
        this._charts.forEach(c => c.destroy());
        this._charts = [];
    }

    fmt(v) {
        if (v == null) return "0";
        return Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
    }

    renderAllCharts() {
        const C = window.Chart;
        if (!C || !this.state.data) return;
        this.renderSalesChart(C);
        this.renderCapitalChart(C);
        this.renderAgingChart(C);
        this.renderCashFlowChart(C);
    }

    renderSalesChart(C) {
        const el = this.salesChartRef.el;
        if (!el) return;
        const { charts } = this.state.data;
        const chart = new C(el.getContext("2d"), {
            type: "bar",
            data: {
                labels: charts.labels,
                datasets: [
                    { label: "Sales", data: charts.sales, backgroundColor: "rgba(113,75,103,0.8)", borderRadius: 4, barPercentage: 0.5 },
                    { label: "Purchases", data: charts.purchases, backgroundColor: "rgba(1,126,132,0.8)", borderRadius: 4, barPercentage: 0.5 },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: { duration: 900 },
                plugins: { legend: { position: "bottom", labels: { padding: 16, color: "#adb5bd" } } },
                scales: {
                    y: { beginAtZero: true, ticks: { color: "#adb5bd", callback: v => v.toLocaleString() }, grid: { color: "rgba(255,255,255,0.05)" } },
                    x: { ticks: { color: "#adb5bd" }, grid: { display: false } },
                },
            },
        });
        this._charts.push(chart);
    }

    renderCapitalChart(C) {
        const el = this.capitalChartRef.el;
        if (!el) return;
        const { capital_map } = this.state.data;
        const chart = new C(el.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: ["Bank & Cash", "Receivables", "Vendor Prepaid"],
                datasets: [{ data: [Math.abs(capital_map.bank), Math.abs(capital_map.receivable), Math.abs(capital_map.prepaid)], backgroundColor: ["#017E84", "#F4A261", "#E76F51"], borderWidth: 0, hoverOffset: 8 }],
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: "65%", animation: { duration: 900 },
                plugins: { legend: { position: "bottom", labels: { padding: 12, color: "#adb5bd", usePointStyle: true } } },
            },
        });
        this._charts.push(chart);
    }

    renderAgingChart(C) {
        const el = this.agingChartRef.el;
        if (!el) return;
        const { aging } = this.state.data;
        const chart = new C(el.getContext("2d"), {
            type: "bar",
            data: {
                labels: ["Receivable Aging"],
                datasets: [
                    { label: "Current (0-30)", data: [aging.receivable.current], backgroundColor: "#51cf66" },
                    { label: "31-60 days", data: [aging.receivable.days_30_60], backgroundColor: "#ffc107" },
                    { label: "61-90 days", data: [aging.receivable.days_60_90], backgroundColor: "#fd7e14" },
                    { label: "90+ days", data: [aging.receivable.over_90], backgroundColor: "#dc3545" },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false, indexAxis: "y",
                scales: {
                    x: { stacked: true, ticks: { color: "#adb5bd", callback: v => v.toLocaleString() }, grid: { color: "rgba(255,255,255,0.05)" } },
                    y: { stacked: true, ticks: { color: "#adb5bd" }, grid: { display: false } },
                },
                plugins: { legend: { position: "bottom", labels: { padding: 12, color: "#adb5bd" } } },
            },
        });
        this._charts.push(chart);
    }

    renderCashFlowChart(C) {
        const el = this.cashFlowChartRef.el;
        if (!el) return;
        const { cash_flow } = this.state.data;
        const chart = new C(el.getContext("2d"), {
            type: "line",
            data: {
                labels: ["Current", "+30 Days", "+60 Days", "+90 Days"],
                datasets: [{
                    label: "Projected Cash",
                    data: [cash_flow.current_bank, cash_flow.forecast_30, cash_flow.forecast_60, cash_flow.forecast_90],
                    borderColor: "#714B67", backgroundColor: "rgba(113,75,103,0.15)",
                    fill: true, tension: 0.3, pointRadius: 5, pointBackgroundColor: "#714B67",
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { ticks: { color: "#adb5bd", callback: v => v.toLocaleString() }, grid: { color: "rgba(255,255,255,0.05)" } },
                    x: { ticks: { color: "#adb5bd" }, grid: { display: false } },
                },
            },
        });
        this._charts.push(chart);
    }

    // Navigation — Fixed: use `views` array instead of `view_mode` string
    openReceivables() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Open Receivables", res_model: "account.move",
            views: [[false, "list"], [false, "form"]],
            domain: [["move_type", "=", "out_invoice"], ["state", "=", "posted"], ["payment_state", "in", ["not_paid", "partial"]]],
            target: "current",
        });
    }
    openPayables() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Open Payables", res_model: "account.move",
            views: [[false, "list"], [false, "form"]],
            domain: [["move_type", "=", "in_invoice"], ["state", "=", "posted"], ["payment_state", "in", ["not_paid", "partial"]]],
            target: "current",
        });
    }
    openBankJournals() {
        this.action.doAction({
            type: "ir.actions.act_window", name: "Bank & Cash", res_model: "account.journal",
            views: [[false, "list"], [false, "form"]],
            domain: [["type", "in", ["bank", "cash"]]],
            target: "current",
        });
    }
}

AIFinanceAnalytics.template = "test_ai_finance.Analytics";
registry.category("actions").add("test_ai_finance.analytics_action", AIFinanceAnalytics);
