import pytest
from mcp import Client

pytestmark = pytest.mark.anyio

EXPECTED_TOOLS = {
    "whoami",
    "list_spaces",
    "check_availability",
    "book_space",
    "list_my_bookings",
    "cancel_booking",
}


def text_of(result) -> str:
    return " ".join(c.text for c in result.content if hasattr(c, "text"))


async def test_server_exposes_the_expected_tools(make_server):
    async with Client(make_server("u-corp-1"), raise_exceptions=True) as client:
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == EXPECTED_TOOLS


async def test_tool_annotations_describe_risk(make_server):
    async with Client(make_server("u-corp-1"), raise_exceptions=True) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert tools["list_spaces"].annotations.read_only_hint is True
    assert tools["cancel_booking"].annotations.destructive_hint is True
    assert tools["book_space"].annotations.read_only_hint is False


async def test_profile_routing_changes_what_the_model_sees(make_server):
    async with Client(make_server("u-corp-1"), raise_exceptions=True) as corp_client:
        who_corp = (await corp_client.call_tool("whoami", {})).structured_content
        spaces_corp = (await corp_client.call_tool("list_spaces", {})).structured_content["result"]
    async with Client(make_server("u-res-1"), raise_exceptions=True) as res_client:
        who_res = (await res_client.call_tool("whoami", {})).structured_content
        spaces_res = (await res_client.call_tool("list_spaces", {})).structured_content["result"]

    assert who_corp["profile"] == "corporate" and who_res["profile"] == "residential"
    assert who_corp["rules"]["max_duration_minutes"] == 480
    assert who_res["rules"]["max_duration_minutes"] == 120
    assert {s["id"] for s in spaces_corp}.isdisjoint({s["id"] for s in spaces_res})


async def test_book_list_and_cancel_round_trip(make_server):
    args = {
        "space_id": "room-atlas",
        "start": "2026-11-24T10:00:00+00:00",
        "end": "2026-11-24T11:00:00+00:00",
    }
    async with Client(make_server("u-corp-1"), raise_exceptions=True) as client:
        booked = await client.call_tool("book_space", args)
        assert not booked.is_error
        booking_id = booked.structured_content["id"]

        mine = (await client.call_tool("list_my_bookings", {})).structured_content["result"]
        assert [b["id"] for b in mine] == [booking_id]

        cancelled = await client.call_tool("cancel_booking", {"booking_id": booking_id})
        assert cancelled.structured_content["status"] == "cancelled"

        mine = (await client.call_tool("list_my_bookings", {})).structured_content["result"]
        assert mine == []


async def test_domain_errors_reach_the_model_as_readable_tool_errors(make_server):
    args = {
        "space_id": "room-atlas",
        "start": "2026-11-24T10:00:00+00:00",
        "end": "2026-11-24T11:00:00+00:00",
    }
    async with Client(make_server("u-corp-1"), raise_exceptions=True) as client:
        await client.call_tool("book_space", args)
        clash = await client.call_tool("book_space", args)
        assert clash.is_error
        assert "conflict" in text_of(clash)
        assert "check_availability" in text_of(clash)  # tells the model what to do next

        naive = await client.call_tool(
            "book_space",
            {"space_id": "room-birch", "start": "2026-11-24T10:00:00", "end": "2026-11-24T11:00:00"},
        )
        assert naive.is_error
        assert "UTC offset" in text_of(naive)


async def test_check_availability_through_the_tool(make_server):
    async with Client(make_server("u-corp-1"), raise_exceptions=True) as client:
        result = await client.call_tool(
            "check_availability", {"space_id": "room-atlas", "day": "2026-11-24"}
        )
    windows = result.structured_content["result"]
    assert len(windows) == 1
    assert windows[0]["start"].startswith("2026-11-24T07:00")
