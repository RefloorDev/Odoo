import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { KanbanColumn, KanbanRecord } from "@web/views/kanban/kanban_record";
import { _t } from "@web/core/l10n/translation";

export class OtlDocumentSignKanbanColumn extends KanbanColumn {
    setup() {
        super.setup();
        if (this.props.modelName === "otl_document_sign.request") {
            this.props.draggable = false;
        }
    }
}

export class OtlDocumentSignKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        this.action = useService("action");
        this.orm = useService("orm");
    }

    async openRecord(ev) {
        // Custom open logic for templates and requests
        if (
            this.props.modelName === "otl_document_sign.template" &&
            this.el.closest('.o_kanban_dashboard')
        ) {
            const action = await this.orm.call(
                "otl_document_sign.template",
                "go_to_custom_template",
                [this.props.record.data.id]
            );
            this.action.doAction(action);
        } else if (
            this.props.modelName === "otl_document_sign.request" &&
            this.el.closest('.o_sign_request_kanban')
        ) {
            const action = await this.orm.call(
                "otl_document_sign.request",
                "go_to_document",
                [this.props.record.data.id]
            );
            this.action.doAction(action);
        } else {
            // Default behavior
            super.openRecord(ev);
        }
    }
}

// Register the custom KanbanColumn and KanbanRecord for the relevant models
registry.category("views").add("otl_document_sign.request_kanban_column", {
    ...registry.category("views").get("kanban"),
    KanbanColumn: OtlDocumentSignKanbanColumn,
});
registry.category("views").add("otl_document_sign.kanban_record", {
    ...registry.category("views").get("kanban"),
    KanbanRecord: OtlDocumentSignKanbanRecord,
});
