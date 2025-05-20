/** @odoo-module **/

import { registry } from "@web/core/registry";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { KanbanColumn } from "@web/views/kanban/kanban_column";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { getDataURLFromFile } from "@web/core/utils/urls";

export class SignatureKanbanRecord extends KanbanRecord {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    }

    async openRecord() {
        if (this.props.record.resModel === "otl_document_sign.template" && this.el.closest(".o_kanban_dashboard")) {
            const action = await this.orm.call(
                "otl_document_sign.template",
                "go_to_custom_template",
                [this.props.record.resId]
            );
            this.action.doAction(action);
        } else if (this.props.record.resModel === "otl_document_sign.request" && this.el.closest(".o_sign_request_kanban")) {
            const action = await this.orm.call(
                "otl_document_sign.request", 
                "go_to_document",
                [this.props.record.resId]
            );
            this.action.doAction(action);
        } else {
            super.openRecord();
        }
    }
}

export class SignatureKanbanColumn extends KanbanColumn {
    setup() {
        super.setup();
        if (this.props.record.resModel === "otl_document_sign.request") {
            this.props.draggable = false;
        }
    }
}

export class SignatureKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    }

    async signUploadFile(inactive = false, signDirectlyWithoutMail = false, signEditContext) {
        const fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.accept = ".pdf";
        fileInput.name = "files[]";

        fileInput.onchange = async (event) => {
            const file = event.target.files[0];
            const dataUrl = await getDataURLFromFile(file);
            const args = inactive ? [file.name, dataUrl, false] : [file.name, dataUrl];

            try {
                const result = await this.orm.call(
                    "otl_document_sign.template",
                    "upload_template",
                    args
                );

                this.action.doAction({
                    type: "ir.actions.client",
                    tag: "otl_document_sign.Template",
                    name: _t("Template ") + ` "${file.name}"`,
                    context: {
                        sign_edit_call: signEditContext,
                        id: result.template,
                        sign_directly_without_mail: signDirectlyWithoutMail,
                    },
                });
            } finally {
                fileInput.removeAttribute("disabled");
                fileInput.value = "";
            }
        };

        fileInput.click();
    }

    getButtons() {
        const buttons = super.getButtons();
        if (this.props.resModel === "otl_document_sign.template") {
            return [
                {
                    name: _t("Send a Request"),
                    icon: "fa fa-plus",
                    onClick: () => this.signUploadFile(true, false, "sign_send_request"),
                },
                {
                    name: _t("Sign Now"),
                    icon: "fa fa-pencil",
                    onClick: () => this.signUploadFile(true, true, "sign_sign_now"),
                },
                {
                    name: _t("UPLOAD A PDF TEMPLATE"),
                    type: "link",
                    onClick: () => this.signUploadFile(false, false, "sign_template_edit"),
                },
            ];
        } else if (this.props.resModel === "otl_document_sign.request") {
            return [
                {
                    name: _t("Request a Signature"),
                    icon: "fa fa-plus",
                    onClick: () => this.action.doAction("otl_document_sign.sign_template_action"),
                },
            ];
        }
        return buttons;
    }
}

registry.category("views").add("signature_kanban", {
    ...registry.category("views").get("kanban"),
    Controller: SignatureKanbanController,
    Record: SignatureKanbanRecord, 
    Column: SignatureKanbanColumn,
});
