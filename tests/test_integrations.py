from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import respx

from tindabot.integrations import ORDER_HEADERS, DeliveryError, Integrations


@pytest.fixture
def adapter(settings):
    settings.meta_graph_version = "v99.0"
    instance = Integrations(settings)
    yield instance
    instance.close()


@respx.mock
def test_meta_response_and_bearer_header(adapter):
    route = respx.post("https://graph.facebook.com/v99.0/100/messages").mock(
        return_value=httpx.Response(200, json={"message_id": "mid"})
    )
    assert adapter.send_message("200", {"text": "test"}) == "mid"
    assert "access_token" not in str(route.calls[0].request.url)
    assert route.calls[0].request.headers.get("authorization").startswith("Bearer")


@pytest.mark.parametrize(
    "status,error,retry,uncertain",
    [
        (429, {}, True, False),
        (400, {"code": 4}, True, False),
        (400, {"code": 190}, False, False),
        (500, {}, False, True),
        (400, {"code": 100}, False, False),
    ],
)
@respx.mock
def test_meta_error_classification(adapter, status, error, retry, uncertain):
    respx.post("https://graph.facebook.com/v99.0/100/messages").mock(
        return_value=httpx.Response(status, json={"error": error})
    )
    with pytest.raises(DeliveryError) as caught:
        adapter.send_message("200", {"text": "test"})
    assert caught.value.retry == retry
    assert caught.value.uncertain == uncertain


def test_sheet_reconciliation_uses_stable_order_id_and_raw_cells(adapter):
    worksheet = Mock()
    worksheet.get_all_values.return_value = [ORDER_HEADERS, ["order-id"]]
    adapter._sheet = Mock()
    adapter._sheet.worksheet.return_value = worksheet
    order = SimpleNamespace(
        id="order-id",
        code="CODE",
        created_at=100,
        status="pending",
        payment_status="unpaid",
        version=1,
        details={"name": '=IMPORTXML("bad")', "phone": "09171234567"},
        items=[],
        total_minor=100,
    )
    adapter.export_order(order)
    worksheet.append_row.assert_not_called()
    assert worksheet.update.call_args.kwargs["value_input_option"] == "RAW"
    assert worksheet.update.call_args.args[0][0][6] == '=IMPORTXML("bad")'


def test_sheet_duplicate_rows_stop_export(adapter):
    worksheet = Mock()
    worksheet.get_all_values.return_value = [ORDER_HEADERS, ["order-id"], ["order-id"]]
    adapter._sheet = Mock()
    adapter._sheet.worksheet.return_value = worksheet
    with pytest.raises(DeliveryError, match="sheet_duplicate_order"):
        adapter.export_order(SimpleNamespace(id="order-id"))
    worksheet.append_row.assert_not_called()
    worksheet.update.assert_not_called()
