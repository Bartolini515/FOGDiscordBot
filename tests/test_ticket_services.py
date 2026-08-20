from datetime import datetime, timezone
from types import SimpleNamespace

from ticket.services import (
    generate_transcript_html,
    is_ticket_admin,
    parse_category_selection,
    ticket_create_custom_id,
)


def test_ticket_services_preserve_admin_and_category_selection_rules():
    administrator = SimpleNamespace(
        guild_permissions=SimpleNamespace(administrator=True),
    )
    manager = SimpleNamespace(
        guild_permissions=SimpleNamespace(administrator=False),
    )
    channel = SimpleNamespace(
        permissions_for=lambda _: SimpleNamespace(manage_messages=True),
    )

    assert is_ticket_admin(administrator, channel) is True
    assert is_ticket_admin(manager, channel) is True
    assert parse_category_selection(" Alpha; ;Bravo ") == ["Alpha", "Bravo"]
    assert parse_category_selection("  ") == []


def test_ticket_create_custom_id_preserves_button_and_select_wire_values():
    assert ticket_create_custom_id("button", 1001) == "ticket_create_button_1001"
    assert ticket_create_custom_id("select", 1001) == "ticket_create_select_1001"


async def test_generate_transcript_html_escapes_content_and_attachment_names():
    message = SimpleNamespace(
        author=SimpleNamespace(display_name="<Operator>"),
        created_at=datetime(2030, 1, 2, 18, 30, tzinfo=timezone.utc),
        content="<script>alert(1)</script>",
        attachments=[SimpleNamespace(url="https://example.invalid/file", filename="a&b.txt")],
    )

    class FakeChannel:
        name = "ticket-&"

        async def history(self, **kwargs):
            yield message

    html = await generate_transcript_html(FakeChannel())

    assert "<h2>Transcript kanału ticket-&amp;</h2>" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<a href='https://example.invalid/file'>a&amp;b.txt</a>" in html
