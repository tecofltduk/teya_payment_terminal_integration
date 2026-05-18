/** @odoo-module */
import { register_payment_method } from "@point_of_sale/app/store/pos_store";
import { PaymentTeya } from "@teya_payment_terminal_integration/apps/payment_teya";
import { patch } from "@web/core/utils/patch";
import {Order, Orderline, Payment } from "@point_of_sale/app/store/models";

register_payment_method("teya", PaymentTeya);

patch(Payment.prototype, {
    setup() {
        super.setup(...arguments);
        this.terminalServiceId = this.terminalServiceId || null;
    },
    //@override
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        if (json) {
            json.terminal_service_id = this.terminalServiceId;
        }
        return json;
    },
    //@override
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.terminalServiceId = json.terminal_service_id;
    },
    setTerminalServiceId(id) {
        this.terminalServiceId = id;
    },
});

patch(Order.prototype, {
     init_from_JSON(json) {
        super.init_from_JSON(...arguments);        
        this.teya_gateway_payment_id = json.teya_gateway_payment_id;
        this.teya_transaction_id = json.teya_transaction_id;
        this.teya_response = json.teya_response;
    },
    set_teya_response(response){
        this.teya_gateway_payment_id = response.gateway_payment_id;
        this.teya_transaction_id = response.transaction_id;
        this.teya_response = response;
    },
    export_as_JSON() {
        const json = super.export_as_JSON(...arguments);
        json.teya_gateway_payment_id = this.teya_gateway_payment_id||"";
        json.teya_transaction_id = this.teya_transaction_id || "";
        json.teya_response = this.teya_response || "";
        return json;
    },
    add_paymentline(payment_method) {
        let res= super.add_paymentline(...arguments)
        if (this?.teya_response){
            this.selected_paymentline.set_amount(-(this.get_due()));
        }
        return res
    }
})