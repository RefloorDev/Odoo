/** @odoo-module **/

import { Component, onMounted } from "@odoo/owl";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { mount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

// BadgeComponent definition
export class BadgeComponent extends Component {
    static template = "otl_document_sign.BadgeComponentTemplate";
    static props = ["text", "color"]; // <-- FIXED: use array of prop names

    setup() {
        super.setup?.();
        // Example: add a lifecycle hook here if needed
        onMounted(() => {
            // You can put any logic you want to run after mount here
            // For example: console.log("BadgeComponent mounted", this.props);
        });
    }
}

// Custom Renderer
import { useRef } from "@odoo/owl";

export class MyKanbanRenderer extends KanbanRenderer {
    setup() {
        super.setup?.();
        this.rootRef = useRef("root");
        this.orm = useService("orm");
        this.action = useService("action");

        onMounted(() => {
            const root = this.rootRef.el || this.el;
            if (!root || typeof root.querySelectorAll !== "function") {
                console.warn("KanbanRenderer: root element is not available or not an Element in onMounted()");
                return;
            }
            const nodes = root.querySelectorAll(".my_badge_placeholder");
            if (!nodes.length) {
                console.warn("No .my_badge_placeholder found in KanbanRenderer onMounted()");
            }
            nodes.forEach((node) => {
                const sendButton = document.createElement("button");
                sendButton.type = "button";
                sendButton.textContent = this.env._t ? this.env._t("Send") : "Send";
                sendButton.className = "btn btn-secondary me-2";
                sendButton.onclick = (event) => {
                    event.stopPropagation();
                    let recordId = null;
                    let node = event.target;
                    while (node && !node.dataset.resId) {
                        node = node.parentElement;
                    }
                    if (node && node.dataset.resId) {
                        recordId = parseInt(node.dataset.resId, 10);
                    }
                    console.log("node------", node);
                    console.log("-event------", event);
                    console.log("-recordId------", recordId);


                    // Set context on the record before opening the form view
                    var record = null;
                    if (recordId) {
                        // Find the record in the renderer's state and update its context
                        var record = this.props && this.props.records && this.props.records.find(r => r.resId === recordId);
                        if (record) {
                            record.context = {
                                ...(record.context || {}),
                                active_id: recordId,
                                sign_directly_without_mail: false,
                            };
                        }
                    }
                    this.action.doAction({
                        name: "Signature Request",
                        type: "ir.actions.act_window",
                        res_model: "otl_document_sign.send.request",
                        views: [
                            [false, "form"],
                        ],
                        target: 'new',
                        context: {
                            record: record,
                            active_id: recordId,
                            sign_directly_without_mail: false,
                        },
                    });
                };
                
                // Create a "Send Now" button
                const sendNowButton = document.createElement("button");
                sendNowButton.textContent = "Send Now";
                sendNowButton.className = "btn btn-success me-2";
                sendNowButton.onclick = () => {
                    alert("Send Now button clicked!");
                };

                // Create a "Share" button
                const shareButton = document.createElement("button");
                shareButton.textContent = "Share";
                shareButton.className = "btn btn-info";
                shareButton.onclick = () => {
                    alert("Share button clicked!");
                };

                node.innerHTML = ""; // Clear previous content
                node.appendChild(sendButton);
                node.appendChild(sendNowButton);
                node.appendChild(shareButton);
            });
        });
    }
    get template() {
        return super.template;
    }
}

// Optionally, you can subclass KanbanController if you need custom logic
class MyKanbanController extends KanbanController {}

const myKanbanView = {
    ...kanbanView,
    Renderer: MyKanbanRenderer,
    Controller: MyKanbanController,
};

registry.category("views").add("otl_document_sign.document_sign_kanban_renderer", myKanbanView);
