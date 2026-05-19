import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    setup() {
        super.setup(...arguments);
        this.teya_gateway_payment_id ??= "";
        this.teya_transaction_id ??= "";
        this.teya_response ??= "";
    },
    setTeyaResponse(response) {
        this.teya_gateway_payment_id = response.gateway_payment_id;
        this.teya_transaction_id = response.transaction_id;
        this.teya_response = response;
    },
    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        data.teya_gateway_payment_id = this.teya_gateway_payment_id || "";
        data.teya_transaction_id = this.teya_transaction_id || "";
        if (this.teya_response === undefined || this.teya_response === "") {
            data.teya_response = "";
        } else if (typeof this.teya_response === "string") {
            data.teya_response = this.teya_response;
        } else {
            data.teya_response = JSON.stringify(this.teya_response);
        }
        return data;
    },
    addPaymentline(payment_method) {
        const res = super.addPaymentline(...arguments);
        if (res?.status && this?.teya_response) {
            this.getSelectedPaymentline()?.setAmount(-this.remainingDue);
        }
        return res;
    },
});
