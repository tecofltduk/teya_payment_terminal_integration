import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";

patch(PosStore.prototype, {
    async setup() {
        await super.setup(...arguments);
        this.data.connectWebSocket("TEYA_LATEST_RESPONSE", (payload) => {
            if (payload.config_id !== this.config.id) {
                return;
            }
            const terminalName = "teya";
            for (const order of this.models["pos.order"].getAll()) {
                const pendingLine = order.payment_ids.find(
                    (paymentLine) =>
                        paymentLine.payment_method_id.use_payment_terminal === terminalName &&
                        !paymentLine.isDone() &&
                        paymentLine.getPaymentStatus() !== "retry"
                );
                if (!pendingLine) {
                    continue;
                }
                const terminal = pendingLine.payment_method_id.payment_terminal;
                if (
                    terminal &&
                    terminal._activeLineUuid === pendingLine.uuid &&
                    String(terminal.payment_request_id) === String(payload.payment_request_id)
                ) {
                    terminal.handleTeyaStatusResponse(payload.response, pendingLine.uuid);
                    return;
                }
            }
        });
    },
});
