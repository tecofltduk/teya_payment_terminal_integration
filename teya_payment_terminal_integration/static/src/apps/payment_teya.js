/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { sprintf } from "@web/core/utils/strings";

export class PaymentTeya extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.paymentLineResolvers = {};
    }

    set_payment_id(id) {
        this.payment_request_id = id;
    }

    send_payment_request(cid) {
        super.send_payment_request(cid);
        // Clear polling from a previous attempt (important for Retry).
        if (this.getPaymentStatus) {
            clearInterval(this.getPaymentStatus);
            this.getPaymentStatus = null;
        }
        this.payment_request_id = null;
        return this._send_teya_pay_req(cid);
    }

    _send_teya_pay_req(cid) {
        const order = this.pos.get_order();
        const line = order.paymentlines.find((paymentLine) => paymentLine.cid === cid);
        if (!line) {
            return Promise.resolve(false);
        }
        if (line.amount <= 0) {
            this._show_error(_t("Cannot process transactions with negative amount."));
            return Promise.resolve(false);
        }

        const data = this.teya_pay_req_data(line);
        line.setTerminalServiceId?.(this.most_recent_service_id);

        return this._teya_payment_request(data, cid).then((response) =>
            this._teya_handle_response(response, line)
        );
    }

    _teya_handle_response(response, line) {
        if (!line) {
            line = this.pending_teya_line();
        }
        if (!response || typeof response !== "object") {
            this._show_error(_t("Invalid response from Teya. Please retry."));
            line?.set_payment_status("retry");
            return false;
        }

        if (response.status_code === 401 || response.status_code === 400) {
            this._show_error(
                _t("Authentication failed, %s. Please check your Teya credentials.", response.message || "")
            );
            line.set_payment_status("retry");
            return false;
        }
        if (response.status_code && response.status_code >= 400) {
            this._show_error(response.message || _t("Payment request failed. Please retry."));
            line.set_payment_status("retry");
            return false;
        }
        if (!response.payment_request_id) {
            this._show_error(
                response.message || _t("Teya did not return a payment request. Please retry.")
            );
            line.set_payment_status("retry");
            return false;
        }

        this.set_payment_id(response.payment_request_id);

        if (response?.status === "Reject") {
            this._show_error(_t("An unexpected error occurred. Message from Teya."));
            line.set_payment_status("retry");
            return false;
        }

        line.set_payment_status("waitingCard");
        this.getPaymentStatus = setInterval(() => {
            this.env.services.orm.silent.call(
                "pos.payment.method",
                "teya_payment_request_status",
                [[this.payment_method.id], this.payment_request_id, this.pos.pos_session.id]
            );
        }, 5000);
        return this.waitForPaymentConfirmation(line);
    }

    waitForPaymentConfirmation(line) {
        const targetLine = line || this.pending_teya_line();
        return new Promise((resolve) => {
            if (targetLine) {
                this.paymentLineResolvers[targetLine.cid] = resolve;
            }
        });
    }

    send_payment_cancel(order, cid) {
        super.send_payment_cancel(order, cid);
        if (this.getPaymentStatus) {
            clearInterval(this.getPaymentStatus);
            this.getPaymentStatus = null;
        }
        const line = order.get_paymentline(cid) || this.pending_teya_line();
        if (line) {
            line.set_payment_status("retry");
        }
        const resolver = line && this.paymentLineResolvers[line.cid];
        if (resolver) {
            resolver(false);
            delete this.paymentLineResolvers[line.cid];
        }
        return Promise.resolve(false);
    }

    _teya_payment_request(data, cid) {
        const order = this.pos.get_order();
        // Fresh idempotency key on every attempt (Send + Retry) — reusing the same key
        // can make Teya return an empty body and break response.json() on the server.
        const orderToken = `${order.access_token}-${cid}-${Date.now()}`;

        return this.env.services.orm.silent
            .call("pos.payment.method", "proxy_teya_payment_request", [
                [this.payment_method.id],
                data,
                this.pos.config.id,
                orderToken,
                false,
            ])
            .catch(this._handle_odoo_connection_failure.bind(this));
    }

    pending_teya_line() {
        return this.pos.getPendingPaymentLine("teya");
    }

    _handle_odoo_connection_failure(data = {}) {
        const line = this.pending_teya_line();
        if (line) {
            line.set_payment_status("retry");
        }
        this._show_error(
            _t(
                "Could not connect to the Odoo server, please check your internet connection and try again."
            )
        );
        return Promise.reject(data);
    }

    teya_pay_req_data(paymentLine) {
        const order = this.pos.get_order();
        const config = this.pos.config;
        const line = paymentLine || order.selected_paymentline;
        const base = {
            epos_instance_id: config.name,
            merchant_reference: order.name.split(" ")[1],
            requested_amount: {
                currency: "GBP",
                amount: Math.round(line.amount * 100),
                tip: 0,
            },
            transaction_type: "SALE",
        };
        if (order?.teya_response) {
            return {
                ...base,
                gateway_payment_id: order.teya_gateway_payment_id,
                transaction_id: order.teya_transaction_id || order.transaction_id,
            };
        }
        return base;
    }

    _show_error(msg, title) {
        this.env.services.popup.add(ErrorPopup, {
            title: title || _t("Teya Error"),
            body: msg,
        });
    }

    async handleTeyaStatusResponse(response) {
        const line = this.pending_teya_line();
        if (this.getPaymentStatus) {
            clearInterval(this.getPaymentStatus);
            this.getPaymentStatus = null;
        }

        const isPaymentSuccessful = this.isPaymentSuccessful(response);
        if (isPaymentSuccessful) {
            this.pos.get_order().set_teya_response(response);
            if (this.pos.get_order().get_due() <= 0) {
                await this.pos.get_order().selected_paymentline?.set_amount(
                    this.pos.get_order().get_due()
                );
            }
            this.handleSuccessResponse(line, response);
        } else if (response?.status) {
            this._show_error(sprintf(_t("Message from Teya: Payment %s"), response.status));
            line?.set_payment_status("retry");
        }

        const resolver = line && this.paymentLineResolvers[line.cid];
        if (resolver) {
            resolver(isPaymentSuccessful);
            delete this.paymentLineResolvers[line.cid];
        } else if (line) {
            line.handle_payment_response(isPaymentSuccessful);
        }
    }

    isPaymentSuccessful(response) {
        return response && response.status === "SUCCESSFUL";
    }

    handleSuccessResponse(line, payment_response) {
        if (line) {
            line.payment_request_id = payment_response.payment_request_id;
        }
    }
}
