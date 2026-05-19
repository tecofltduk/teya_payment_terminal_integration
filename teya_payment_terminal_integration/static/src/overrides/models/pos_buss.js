/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { PosBus } from "@point_of_sale/app/bus/pos_bus_service";

patch(PosBus.prototype, {
    // Override
    dispatch(message) {
        super.dispatch(...arguments);

        if (message.type === "TEYA_LATEST_RESPONSE" && message.payload.config_id === this.pos.config.id) {
            const pendingLine = this.pos.getPendingPaymentLine("teya");
            if (pendingLine) {
                const terminal = pendingLine.payment_method.payment_terminal;
                if (terminal.payment_request_id === message.payload.payment_request_id) {
                    console.log('Matching payment request found, processing response.');
                    terminal.handleTeyaStatusResponse(message.payload.response);
                } else {
                    console.log('Teya response received but payment_request_id mismatch. Ignored.');
                }
            }
        }
    },
});
