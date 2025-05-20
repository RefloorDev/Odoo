/** @odoo-module */

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

// 🧠 The OWL Component
class DynamicReferenceField extends Component {
    setup() {
        this.orm = useService("orm");
        if (typeof this.props.update !== "function") {
            this.props.update = () => {
                console.warn("props.update was not provided. Skipping update.");
            };
        }
        this.state = useState({
            models: [],
            records: [],
            selectedModel: null,
            selectedId: null,
        });
        // Load dynamic models from context
        const context = this.props.record?.context || {};
        const selection = context.resource_reference_selection || [];

        this.state.models = selection;

        // If value already exists, split it and fetch records
        const value = this.props.value;
        if (value) {
            const [model, id] = value.split(",");
            this.state.selectedModel = model;
            this.state.selectedId = parseInt(id);
            this.fetchRecords(model);
        }
    }

    async fetchRecords(model) {
        const result = await this.orm.searchRead(model, [], ["id", "name"]);
        this.state.records = result;
    }

    async onModelChange(ev) {
        const model = ev.target.value;
        this.state.selectedModel = model;
        this.state.selectedId = null;
        this.state.records = [];
        if (model) {
            await this.fetchRecords(model);
        }
        this.updateValue();
    }

    onRecordChange(ev) {
        this.state.selectedId = parseInt(ev.target.value);
        this.updateValue();
    }

    updateValue() {
        if (this.state.selectedModel && this.state.selectedId) {
            const value = `${this.state.selectedModel},${this.state.selectedId}`;
            this.props.update(value);
        } else {
            this.props.update(false);
        }
    }
}
DynamicReferenceField.template = "otl_document_sign.DynamicReferenceField";

// ✅ Register the field properly in Odoo
registry.category("fields").add("dynamic_reference", {
    component: DynamicReferenceField,
});
