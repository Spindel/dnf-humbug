from textual.app import App, ComposeResult
from textual.widgets import Static, DataTable

TEXT = """\
Docking a widget removes it from the layout and fixes its position, aligned to either the top, right, bottom, or left edges of a container.

Docked widgets will not scroll out of view, making them ideal for sticky headers, footers, and sidebars.

"""
from textual.reactive import reactive
from textual import events
from textual.message import Message, MessageTarget
class Table(DataTable):

    class RowChanged(Message):
        def __init__(self, sender: MessageTarget, package: str) -> None:
            self.package = package
            super().__init__(sender)

    async def send_row_changed(self) -> None:
        """Send an row changed update event."""
        package_name = self.data[self.cursor_cell.row][0]
        await self.emit(self.RowChanged(self, package=package_name))

    async def key_down(self, event: events.Key) -> None:
        """Hooked into key down to send row changed event to the app."""
        super().key_down(event)
        await self.send_row_changed()

    async def key_up(self, event: events.Key) -> None:
        """Hooked into key up to send row changed event to the app."""
        super().key_up(event)
        await self.send_row_changed()


class Info(Static):
    """Our info pane, with a reactive text."""
    text = reactive("text")

    def render(self) -> str:
        return f"info: {self.text}!"



class DockLayoutExample(App):
    CSS_PATH = "dock_layout1_sidebar.css"

    def compose(self) -> ComposeResult:
        yield Info("Sidebar", id="sidebar")
        yield Table(id="body")

    def on_table_row_changed(self, message: Table.RowChanged) -> None:
        """Recieves RowChanged events from Table class."""
        self.query_one(Info).text = message.package

    def on_mount(self):
        table = self.query_one(Table)
        table.add_columns(*["Main data", "extra", "detail"])
        rows = [
            ("systemd-udev-251.8-586.fc37.x86_64",  "12",  "0"),
            ("perl-Socket-2.036-1.fc37.x86_64", "11", "0"),
            ("fedora-packager-yubikey-0.6.0.7-1.fc37.noarch", "13","0"),
            ("sane-backends-libs-1.1.1-8.fc37.x86_64", "0","0"),
            ("python3-systemd-235-1.fc37.x86_64", "30","0"),
            ("pipewire-utils-0.3.60-5.fc37.x86_64", "0","0"),
            ("libX11-common-1.8.1-2.fc37.noarch", "3","0"),
            ("gpg-pubkey-6dc1be18-5ca9b41f", "0","0"),
            ("cfitsio-4.0.0-3.fc37.x86_64", "2","0"),
            ("syslinux-extlinux-6.04-0.23.fc37.x86_64", "1","0"),
        ]
        table.add_rows(rows)
        table.focus()

if __name__ == "__main__":
    app = DockLayoutExample()
    app.run()
