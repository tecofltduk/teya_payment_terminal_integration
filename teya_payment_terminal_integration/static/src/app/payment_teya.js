import { _t } from "@web/core/l10n/translation";
import { PaymentInterface } from "@point_of_sale/app/utils/payment/payment_interface";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { register_payment_method } from "@point_of_sale/app/services/pos_store";
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

    setPaymentRequestId(id) {
        this.payment_request_id = id;
    }

    _getLine(uuid) {
        return this.pos.getOrder()?.getPaymentlineByUuid(uuid);
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

    sendPaymentRequest(uuid) {
        super.sendPaymentRequest(uuid);
        this._resetAttemptState(uuid);
        this._nextAttemptKey(uuid);
        return this._sendTeyaPayReq(uuid);
    }

    _sendTeyaPayReq(uuid) {
        const line = this._getLine(uuid);
        if (!line) {
            return Promise.resolve(false);
        }

        if (line.amount <= 0) {
            this._showError(_t("Cannot process transactions with negative amount."));
            return Promise.resolve(false);
        }

        const data = this._teyaPayReqData(line);
        line.setTerminalServiceId(this.most_recent_service_id);
        return this._teyaPaymentRequest(data, uuid).then((response) => {
            return this._teyaHandleResponse(response, uuid);
        });
    }

    _teyaHandleResponse(response, uuid) {
        const line = this._getLine(uuid);
        if (!line) {
            return false;
        }

        if (response.status_code) {
            const hint =
                response.message ||
                _t(
                    "Check Teya credentials, Payment mode (sandbox vs production), and store/terminal access."
                );
            this._showError(
                response.status_code === 401
                    ? sprintf(_t("Authentication failed: %s"), hint)
                    : sprintf(
                          _t("Teya refused the payment request (%s): %s"),
                          String(response.status_code),
                          hint
                      )
            );
            line.setPaymentStatus("retry");
            return false;
        }

        if (!response.payment_request_id) {
            this._showError(
                _t(
                    "Teya did not return a payment request id. See Odoo server log for the Teya HTTP response."
                )
            );
            line.setPaymentStatus("retry");
            return false;
        }

        this.setPaymentRequestId(response.payment_request_id);
        const status = (response?.status || "").toUpperCase();
        if (status === "REJECT" || TERMINAL_STATUSES.has(status)) {
            return this.handleTeyaStatusResponse(response, uuid);
        }

        line.setPaymentStatus("waitingCard");
        this._responseHandled = false;
        this._startPaymentStatusPolling(uuid);
        return this._waitForPaymentConfirmation(uuid);
    }

    _startPaymentStatusPolling(uuid) {
        clearInterval(this.getPaymentStatus);
        const poll = async () => {
            if (!this.payment_request_id || this._activeLineUuid !== uuid) {
                clearInterval(this.getPaymentStatus);
                return;
            }
            const line = this._getLine(uuid);
            if (!line || line.getPaymentStatus() === "retry") {
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

    _waitForPaymentConfirmation(uuid) {
        return new Promise((resolve) => {
            this.paymentLineResolvers[uuid] = resolve;
        });
    }

    sendPaymentCancel(order, uuid) {
        super.sendPaymentCancel(order, uuid);
        this._resetAttemptState(uuid);
        return Promise.resolve(true);
    }

    _teyaPaymentRequest(data, lineUuid, operation = false) {
        const attempt = this._attemptByLine[lineUuid] || 1;
        const orderToken = buildTeyaIdempotencyKey(lineUuid, attempt);
        return this.pos.data
            .silentCall("pos.payment.method", "proxy_teya_payment_request", [
                [this.payment_method_id.id],
                data,
                this.pos.config.id,
                orderToken,
                operation,
            ])
            .catch(this._handleOdooConnectionFailure.bind(this));
    }

    pendingTeyaLine() {
        return this.pos.getPendingPaymentLine("teya");
    }

    _handleOdooConnectionFailure(data = {}) {
        const line = this.pendingTeyaLine();
        if (line) {
            line.setPaymentStatus("retry");
        }
        this._showError(
            _t(
                "Could not connect to the Odoo server, please check your internet connection and try again."
            )
        );

        return Promise.reject(data);
    }

    _teyaPayReqData(line) {
        const order = this.pos.getOrder();
        const config = this.pos.config;
        const refStr = String(
            order.pos_reference || order.floatingOrderName || order.tracking_number || ""
        );
        const parts = refStr.trim().split(/\s+/);
        const merchantReference = parts.length > 1 ? parts[1] : refStr || String(order.uuid);

        if (order?.teya_response) {
            return {
                epos_instance_id: config.name,
                merchant_reference: merchantReference,
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
            merchant_reference: merchantReference,
            requested_amount: {
                currency: "GBP",
                amount: line.amount * 100,
                tip: 0,
            },
            transaction_type: "SALE",
        };
    }

    _showError(msg, title) {
        this.env.services.dialog.add(AlertDialog, {
            title: title || _t("Teya Error"),
            body: msg,
        });
    }

    async handleTeyaStatusResponse(response, uuid = this._activeLineUuid) {
        const line = uuid ? this._getLine(uuid) : this.pendingTeyaLine();
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
            this.pos.getOrder().setTeyaResponse(response);
            if (this.pos.getOrder().remainingDue <= 0) {
                await line.setAmount(this.pos.getOrder().remainingDue);
            }
            line.payment_request_id = response.payment_request_id;
        } else if (status === "CANCELLED") {
            this._showError(_t("Payment was cancelled on the Teya terminal."));
        } else if (status === "FAILED") {
            this._showError(_t("Payment was declined or failed on the Teya terminal."));
        } else {
            this._showError(sprintf(_t("Message from Teya: Payment %s"), response?.status || status));
        }

        const resolver = this.paymentLineResolvers?.[line.uuid];
        if (resolver) {
            delete this.paymentLineResolvers[line.uuid];
            resolver(isPaymentSuccessful);
        } else {
            line.handlePaymentResponse(isPaymentSuccessful);
        }
        return isPaymentSuccessful;
    }
}

register_payment_method("teya", PaymentTeya);
