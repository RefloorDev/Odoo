/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ReferenceField, referenceField } from "@web/views/fields/reference/reference_field";

patch(ReferenceField.prototype, {
    setup() {
        super.setup();
        this.orm = useService('orm')
        const isCustomContext =
            this.props.context?.resource_reference_selection ||
            this.props.context?.send_button ||
            this.props.context?.sign_now_button;

        if(isCustomContext){
            this.dynamicSelection = [];
            const modelTuple = this.props.record.data.related_model_id;
            if (modelTuple && modelTuple.length > 0) {
                const modelId = modelTuple[0];
                this.orm.call("otl_document_sign.template", "selection_target_model", [modelId], {})
                    .then((result) => {
                        this.dynamicSelection = result;
                        this.render();
                    });
            }
        }
    },

    get selection() {
        const isCustomContext =
            this.props.context?.resource_reference_selection ||
            this.props.context?.send_button ||
            this.props.context?.sign_now_button;

        if(isCustomContext){
            return this.dynamicSelection || [];
        } else {
            if (!this._isCharField(this.props) && !this.hideModelSelector) {
                return this.props.record.fields[this.props.name].selection;
            }
            return [];
        }
    }

})
export default ReferenceField;