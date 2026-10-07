import base64
import json
import smtplib
import ssl
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage

import gspread
import httpx
from google.oauth2.service_account import Credentials

from tindabot.catalog import CatalogImport


class DeliveryError(Exception):
    def __init__(self, code, *, retry=False, uncertain=False):
        self.code, self.retry, self.uncertain = code, retry, uncertain
        super().__init__(code)


ORDER_HEADERS = [
    "order_id",
    "order_code",
    "created_at",
    "status",
    "payment_status",
    "version",
    "name",
    "phone",
    "address",
    "delivery",
    "payment",
    "items",
    "total_minor",
]
COMMAND_HEADERS = ["command_id", "order_id", "expected_version", "action", "result"]


class Integrations:
    def __init__(self, settings):
        self.settings = settings
        self.http = httpx.Client(timeout=15, follow_redirects=False)
        self._sheet = None

    def close(self):
        self.http.close()

    def sheet(self):
        if self._sheet is None:
            credentials = json.loads(
                base64.b64decode(self.settings.google_service_account_json_b64.get_secret_value())
            )
            auth = Credentials.from_service_account_info(
                credentials, scopes=["https://www.googleapis.com/auth/spreadsheets"]
            )
            client = gspread.authorize(auth)
            client.set_timeout(15)
            self._sheet = client.open_by_key(self.settings.google_sheet_id)
        return self._sheet

    def send_message(self, psid, message):
        try:
            response = self.http.post(
                f"https://graph.facebook.com/{self.settings.meta_graph_version}/{self.settings.meta_page_id}/messages",
                headers={
                    "Authorization": f"Bearer {self.settings.meta_page_access_token.get_secret_value()}"
                },
                json={"recipient": {"id": psid}, "messaging_type": "RESPONSE", "message": message},
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            raise DeliveryError("meta_connect", retry=True) from exc
        except httpx.HTTPError as exc:
            raise DeliveryError("meta_transport_unknown", uncertain=True) from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        error = data.get("error", {})
        code = error.get("code")
        if response.is_success and data.get("message_id"):
            return str(data["message_id"])
        if code == 190 or response.status_code in {401, 403}:
            raise DeliveryError("meta_credentials")
        if response.status_code == 429 or code in {4, 17, 32, 613}:
            raise DeliveryError("meta_throttled", retry=True)
        if response.status_code >= 500:
            raise DeliveryError("meta_server_unknown", uncertain=True)
        if error.get("is_transient"):
            raise DeliveryError("meta_transient", retry=True)
        raise DeliveryError("meta_rejected")

    def send_email(self, order=None, handover=False):
        message = EmailMessage()
        message["From"] = self.settings.smtp_from
        message["To"] = self.settings.seller_notify_email
        message["Subject"] = (
            "TindaBot: customer requests a seller" if handover else f"TindaBot order {order.code}"
        )
        message["Message-ID"] = f"<{order.id if order else 'handover'}@tindabot.local>"
        body = (
            "A customer requested a seller. Check your Page inbox."
            if handover
            else f"Order {order.code} is saved. Review it in your restricted Orders sheet."
        )
        message.set_content(
            body + f"\nhttps://docs.google.com/spreadsheets/d/{self.settings.google_sheet_id}"
        )
        try:
            with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(self.settings.smtp_user, self.settings.smtp_password.get_secret_value())
                smtp.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise DeliveryError("smtp_credentials") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise DeliveryError("smtp_delivery_unknown", uncertain=True) from exc

    def export_order(self, order):
        worksheet = self.sheet().worksheet("Orders")
        rows = worksheet.get_all_values()
        if not rows or rows[0] != ORDER_HEADERS:
            raise DeliveryError("sheet_headers")
        matches = [i + 1 for i, row in enumerate(rows) if row and row[0] == order.id]
        if len(matches) > 1:
            raise DeliveryError("sheet_duplicate_order")
        d = order.details
        values = [
            order.id,
            order.code,
            order.created_at,
            order.status,
            order.payment_status,
            order.version,
            d.get("name", ""),
            d.get("phone", ""),
            d.get("address", ""),
            d.get("delivery", ""),
            d.get("payment", ""),
            "; ".join(f"{i['qty']} x {i['name']}" for i in order.items),
            order.total_minor,
        ]
        if matches:
            worksheet.update([values], f"A{matches[0]}:M{matches[0]}", value_input_option="RAW")
        else:
            worksheet.append_row(values, value_input_option="RAW")

    def read_catalog(self):
        rows = self.sheet().worksheet("Products").get_all_records(numericise_ignore=["all"])
        products = []
        for row in rows:
            try:
                price = Decimal(str(row["price"])) * 100
                if not price.is_finite() or price != price.to_integral_value():
                    raise ValueError("Price must have at most two decimal places")
                active = str(row.get("active", "true")).strip().lower()
                if active not in {"true", "false", "1", "0"}:
                    raise ValueError("Invalid active value")
                products.append(
                    {
                        "sku": str(row["sku"]),
                        "name": row["name"],
                        "price_minor": int(price),
                        "stock": int(row["stock"]),
                        "active": active in {"true", "1"},
                        "image_url": row.get("image_url", ""),
                    }
                )
            except (KeyError, InvalidOperation, ValueError) as exc:
                raise DeliveryError("invalid_catalog") from exc
        faq = self.sheet().worksheet("FAQ").get_all_records(numericise_ignore=["all"])
        return CatalogImport(
            products=products, faq=[{"keywords": r["keywords"], "answer": r["answer"]} for r in faq]
        )

    def commands(self):
        worksheet = self.sheet().worksheet("Commands")
        rows = worksheet.get_all_values()
        if not rows or rows[0] != COMMAND_HEADERS:
            raise DeliveryError("command_headers")
        return [
            (i + 2, (row + [""] * 5)[:5])
            for i, row in enumerate(rows[1:])
            if row and row[0] and (len(row) < 5 or not row[4])
        ]

    def command_result(self, row_number, original, result):
        worksheet = self.sheet().worksheet("Commands")
        # Detect sorting/edits before writing. Sheet commands remain an eventual interface.
        current = worksheet.row_values(row_number)
        if (current + [""] * 5)[:4] == original[:4]:
            worksheet.update([[result]], f"E{row_number}", value_input_option="RAW")
