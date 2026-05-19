import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";

patch(TicketScreen.prototype, {
    async addAdditionalRefundInfo(order, destinationOrder) {
        destinationOrder.teya_gateway_payment_id = order.teya_gateway_payment_id;
        destinationOrder.teya_transaction_id = order.teya_transaction_id;
        destinationOrder.teya_response = order.teya_response;
        await super.addAdditionalRefundInfo(...arguments);
    },
});
