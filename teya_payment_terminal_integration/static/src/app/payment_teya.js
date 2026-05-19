import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/store/pos_store";
import { sprintf } from "@web/core/utils/strings";

const TERMINAL_STATUSES = new Set(["SUCCESSFUL", "CANCELLED", "FAILED"]);
const TEYA_IDEMPOTENCY_KEY_MAX_LENGTH = 64;

function buildTeyaIdempotencyKey(lineUuid, attempt) {
    const linePart = lineUuid.replace(/-/g, "").slice(0, 24);
    const key = `${linePart}-${attempt}-${Date.now().toString(36)}`;
    return key.length <= TEYA_IDEMPOTENCY_KEY_MAX_LENGTH
        ? key
        : key.slice(0, TEYA_IDEMPOTENCY_KEY_MAX_LENGTH);
}

export class PaymentTeya extends PaymentInterface {
    setup() {
        super.setup(...arguments);
        this.paymentLineResolvers = {};
        this._attemptByLine = {};
        this._activeLineUuid = null;
    }

    set_payment_id(id) {
        this.payment_request_id = id;
    }

    _getLine(uuid) {
        const order = this.pos.get_order();
        return order?.payment_ids?.find((paymentLine) => paymentLine.uuid === uuid);
    }

    _nextAttemptKey(lineUuid) {
        this._attemptByLine[lineUuid] = (this._attemptByLine[lineUuid] || 0) + 1;
        return this._attemptByLine[lineUuid];
    }

    _resetAttemptState(lineUuid) {
        clearInterval(this.getPaymentStatus);
        this._responseHandled = false;
        this.payment_request_id = null;
        this._activeLineUuid = lineUuid;
        delete this.paymentLineResolvers[lineUuid];
    }

    send_payment_request(uuid) {
        super.send_payment_request(uuid);
        this._resetAttemptState(uuid);
        this._nextAttemptKey(uuid);
        return this._send_teya_pay_req(uuid);
    }

    _send_teya_pay_req(uuid) {
        const order = this.pos.get_order();
        const line = this._getLine(uuid);
        if (!line) {
            return Promise.resolve(false);
        }

        if (line.amount <= 0) {
            this._show_error(_t("Cannot process transactions with negative amount."));
            return Promise.resolve(false);
        }

        const data = this.teya_pay_req_data(line);
        line.setTerminalServiceId(this.most_recent_service_id);
        return this._teya_payment_request(data, uuid).then((response) => {
            return this._teya_handle_response(response, uuid);
        });
    }

    _teya_handle_response(response, uuid) {
        const line = this._getLine(uuid);
        if (!line) {
            return false;
        }

        if (response.status_code) {
            const hint =
                response.message ||
                _t("Check Teya credentials, Payment mode (sandbox vs production), and store/terminal access.");
            this._show_error(
                response.status_code === 401
                    ? sprintf(_t("Authentication failed: %s"), hint)
                    : sprintf(
                          _t("Teya refused the payment request (%s): %s"),
                          String(response.status_code),
                          hint
                      )
            );
            line.set_payment_status("retry");
            return false;
        }

        if (!response.payment_request_id) {
            this._show_error(
                _t(
                    "Teya did not return a payment request id. See Odoo server log for the Teya HTTP response."
                )
            );
            line.set_payment_status("retry");
            return false;
        }

        this.set_payment_id(response.payment_request_id);
        const status = (response?.status || "").toUpperCase();
        if (status === "REJECT" || TERMINAL_STATUSES.has(status)) {
            return this.handleTeyaStatusResponse(response, uuid);
        }

        line.set_payment_status("waitingCard");
        this._responseHandled = false;
        this._startPaymentStatusPolling(uuid);
        return this.waitForPaymentConfirmation(uuid);
    }

    _startPaymentStatusPolling(uuid) {
        clearInterval(this.getPaymentStatus);
        const poll = async () => {
            if (!this.payment_request_id || this._activeLineUuid !== uuid) {
                clearInterval(this.getPaymentStatus);
                return;
            }
            const line = this._getLine(uuid);
            if (!line || line.get_payment_status() === "retry") {
                clearInterval(this.getPaymentStatus);
                return;
            }
            try {
                const result = await this.pos.data.silentCall(
                    "pos.payment.method",
                    "teya_payment_request_status",
                    [
                        [this.payment_method_id.id],
                        this.payment_request_id,
                        this.pos.session.id,
                    ]
                );
                this._processStatusPollResult(result, uuid);
            } catch (error) {
                console.error("Teya status poll failed", error);
            }
        };
        setTimeout(poll, 2000);
        this.getPaymentStatus = setInterval(poll, 5000);
    }

    _processStatusPollResult(result, uuid) {
        if (!result || result.status_code || result.status === "pending") {
            return;
        }
        if (
            result.payment_request_id &&
            String(result.payment_request_id) !== String(this.payment_request_id)
        ) {
            return;
        }
        const status = (result.status || "").toUpperCase();
        if (TERMINAL_STATUSES.has(status)) {
            this.handleTeyaStatusResponse(result, uuid);
        }
    }

    waitForPaymentConfirmation(uuid) {
        return new Promise((resolve) => {
            this.paymentLineResolvers[uuid] = resolve;
        });
    }

    send_payment_cancel(order, uuid) {
        super.send_payment_cancel(order, uuid);
        this._resetAttemptState(uuid);
        return Promise.resolve(true);
    }

    _teya_payment_request(data, lineUuid, operation = false) {
        const attempt = this._attemptByLine[lineUuid] || 1;
        const order_token = buildTeyaIdempotencyKey(lineUuid, attempt);
        return this.pos.data
            .silentCall("pos.payment.method", "proxy_teya_payment_request", [
                [this.payment_method_id.id],
                data,
                this.pos.config.id,
                order_token,
                operation,
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

    teya_pay_req_data(line) {
        const order = this.pos.get_order();
        const config = this.pos.config;
        const refStr = String(order.pos_reference || order.getName?.() || order.tracking_number || "");
        const parts = refStr.trim().split(/\s+/);
        const merchant_reference = parts.length > 1 ? parts[1] : refStr || String(order.uuid);

        if (order?.teya_response) {
            return {
                epos_instance_id: config.name,
                merchant_reference: merchant_reference,
                requested_amount: {
                    currency: "GBP",
                    amount: line.amount * 100,
                    tip: 0,
                },
                gateway_payment_id: order.teya_gateway_payment_id,
                transaction_id: order.teya_transaction_id,
                transaction_type: "SALE",
            };
        }
        return {
            epos_instance_id: config.name,
            merchant_reference: merchant_reference,
            requested_amount: {
                currency: "GBP",
                amount: line.amount * 100,
                tip: 0,
            },
            transaction_type: "SALE",
        };
    }

    _show_error(msg, title) {
        if (!title) {
            title = _t("Teya Error");
        }
        this.env.services.dialog.add(AlertDialog, {
            title: title,
            body: msg,
        });
    }

    async handleTeyaStatusResponse(response, uuid = this._activeLineUuid) {
        const line = uuid ? this._getLine(uuid) : this.pending_teya_line();
        clearInterval(this.getPaymentStatus);
        if (!line || this._responseHandled) {
            return false;
        }
        if (
            response?.payment_request_id &&
            this.payment_request_id &&
            String(response.payment_request_id) !== String(this.payment_request_id)
        ) {
            return false;
        }

        this._responseHandled = true;
        this.payment_request_id = null;

        const status = (response?.status || "").toUpperCase();
        const isPaymentSuccessful = status === "SUCCESSFUL";

        if (isPaymentSuccessful) {
            this.pos.get_order().set_teya_response(response);
            if (this.pos.get_order().get_due() <= 0) {
                await line.set_amount(this.pos.get_order().get_due());
            }
            line.payment_request_id = response.payment_request_id;
        } else if (status === "CANCELLED") {
            this._show_error(_t("Payment was cancelled on the Teya terminal."));
        } else if (status === "FAILED") {
            this._show_error(_t("Payment was declined or failed on the Teya terminal."));
        } else {
            this._show_error(sprintf(_t("Message from Teya: Payment %s"), response?.status || status));
        }

        const resolver = this.paymentLineResolvers?.[line.uuid];
        if (resolver) {
            delete this.paymentLineResolvers[line.uuid];
            resolver(isPaymentSuccessful);
        } else {
            line.handle_payment_response(isPaymentSuccessful);
        }
        return isPaymentSuccessful;
    }
}

register_payment_method("teya", PaymentTeya);
