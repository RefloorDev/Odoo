/** @odoo-module **/

import { Component, xml } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";

console.log("Custom Kanban Renderer Loaded---------");
// Extend the KanbanRenderer to inject active_id and sign_directly_without_mail into the context of action buttons
class CustomKanbanRenderer extends KanbanRenderer {
    getRecordContext(record) {
        console.log("CustomKanbanRenderer getRecordContext called");
        const context = super.getRecordContext(record) || {};
        context.active_id = record.resId;
        return context;
    }
}

class CustomKanbanCard extends Component {
    static template = "otl_document_sign.KanbanButtons";
    static props = ["model", "record", "context"];

    get showCustomCard() {
        return this.props.model === 'otl_document_sign.template';
    }

    get buttons() {
        const record = this.props.record;
        const signEditCall = this.props?.context?.sign_edit_call;
        const buttons = [];

        const sendButton = {
            label: "Send",
            class: "btn btn-secondary",
            onClick: () => {
                this.env.services.action.doAction('otl_document_sign.action_sign_send_request', {
                    additional_context: {
                        active_id: record.resId,
                        sign_directly_without_mail: false,
                    },
                });
            },
        };

        const signNowButton = {
            label: "Sign Now",
            class: "btn btn-secondary",
            onClick: () => {
                this.env.services.action.doAction('otl_document_sign.action_sign_send_request', {
                    additional_context: {
                        active_id: record.resId,
                        sign_directly_without_mail: true,
                    },
                });
            },
        };

        const shareButton = {
            label: "Share",
            class: "btn btn-secondary",
            onClick: () => {
                this.env.services.action.doAction('otl_document_sign.action_sign_template_share', {
                    additional_context: {
                        active_id: record.resId,
                    },
                });
            },
        };

        if (!signEditCall || signEditCall === 'sign_template_edit') {
            sendButton.class = "btn btn-primary";
            buttons.push(sendButton, signNowButton, shareButton);
        } else if (signEditCall === 'sign_sign_now') {
            signNowButton.class = "btn btn-primary";
            buttons.push(signNowButton, sendButton, shareButton);
        } else if (signEditCall === 'sign_send_request') {
            sendButton.class = "btn btn-primary";
            buttons.push(sendButton, signNowButton, shareButton);
        } else {
            buttons.push(sendButton, signNowButton, shareButton);
        }

        return buttons;
    }
}

// Register the custom renderer for your kanban view
registry.category("views").add("otl_document_sign_template_kanban", {
    ...registry.category("views").get("kanban"),
    Renderer: KanbanRenderer,
    templates: {
        ...registry.category("views").get("kanban").templates,
        card: xml/* xml */`
            <CustomKanbanCard model="props.model" record="record" context="props.context"/>
        `,
    },
    components: {
        ...registry.category("views").get("kanban").components,
        CustomKanbanCard,
    },
});
