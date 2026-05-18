/** @odoo-module */

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { onMounted } from "@odoo/owl";

/**
 * Auto-send Teya payment requests:
 *   - When the cashier picks the Teya payment method (a new payment line in
 *     status "pending" is added), immediately dispatch sendPaymentRequest so
 *     the request is sent to the terminal without clicking the Send button.
 *   - The Retry button (status === "retry") keeps working because the template
 *     binds it to the same sendPaymentRequest handler.
 *   - On screen mount, also resume any pending Teya line (safety net for users
 *     who navigated away and came back).
 */
function _autoSendPendingTeyaLine(screen, line) {
    if (!line || line.payment_method?.use_payment_terminal !== "teya") {
        return;
    }
    if (line.get_payment_status() !== "pending") {
        return;
    }
    // Defer to the next microtask so the UI shows the line first.
    Promise.resolve().then(() => {
        // Re-check status because the line could have been removed in between.
        if (line.get_payment_status() === "pending") {
            screen.sendPaymentRequest(line);
        }
    });
}

patch(PaymentScreen.prototype, {
    setup() {
        super.setup(...arguments);
        onMounted(() => {
            const pendingTeyaLine = this.currentOrder?.paymentlines.find(
                (paymentLine) =>
                    paymentLine.payment_method.use_payment_terminal === "teya" &&
                    paymentLine.get_payment_status() === "pending"
            );
            _autoSendPendingTeyaLine(this, pendingTeyaLine);
        });
    },

    /**
     * Core POS calls this when a payment method button is clicked. We auto-fire
     * the Teya request right after the line is created.
     */
    addNewPaymentLine(paymentMethod) {
        const added = super.addNewPaymentLine(paymentMethod);
        if (added && paymentMethod.use_payment_terminal === "teya") {
            _autoSendPendingTeyaLine(this, this.selectedPaymentLine);
        }
        return added;
    },
});
