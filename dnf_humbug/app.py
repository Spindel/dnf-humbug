from dataclasses import dataclass
from operator import itemgetter
from typing import Any, List
from rich.markdown import Markdown

# dnf is not typed for mypy
import dnf  # type: ignore
import libdnf.transaction  # type: ignore
from dnf.package import Package as Pkg  # type: ignore

from textual import events
from textual.app import App, ComposeResult
from textual.message import Message, MessageTarget
from textual.reactive import reactive
from textual.widgets import Header, Footer, Static, DataTable
from textual.widgets import TextLog
from rich.text import Text


def scan_packges():
    """Main entrypoint. Does stuff, sometimes sanely."""
    base = dnf.Base()

    packages = []
    rdepends = []
    pkgmap = {}

    print("Querying rpm database")
    query = dnf.sack._rpmdb_sack(base).query().apply()
    for i, pkg in enumerate(query):
        pkgmap[pkg] = i
        packages.append(pkg)
        rdepends.append([])

    providers = set()
    deps = set()
    depends = []

    print("Building dependency tree")
    for i, pkg in enumerate(packages):
        for req in pkg.requires:
            sreq = str(req)
            if sreq.startswith("rpmlib("):
                continue
            if sreq == "solvable:prereqmarker":
                continue
            for dpkg in query.filter(provides=req):
                providers.add(pkgmap[dpkg])
            if len(providers) == 1 and i not in providers:
                deps.update(providers)
            providers.clear()
            deplist = list(deps)
            deps.clear()
            depends.append(deplist)
            for j in deplist:
                rdepends[j].append(i)

    return packages, depends, rdepends


@dataclass
class Package:
    """Package that we may want to remove."""

    name: str
    needed_by: int
    binaries: int
    pkg: Any
    rdepends: List[Any]

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


def pkg_binaries(pkg) -> int:
    binaries = sum(["bin/" in s for s in pkg.files])
    return binaries


def filter_packages(packages: List[Pkg], depends, rdepends):
    result = []
    for i, pkg in enumerate(packages):
        if pkg.reason == "user":
            # rdepends can have multiple (duplicate) entries, deduplicate first.
            unique_deps = set(rdepends[i])
            needed_by = len(unique_deps)
            pkg_rdepends = [str(packages[n]) for n in unique_deps]

            p = Package(
                name=str(pkg),
                needed_by=needed_by,
                binaries=pkg_binaries(pkg),
                pkg=pkg,
                rdepends=pkg_rdepends,
            )
            result.append(p)
    return result


class ListDisplay(DataTable):
    """Widget of our list of thingies."""

    def __init__(self, *args, **kws):
        super().__init__(*args, **kws)
        self.pkgs = {}

    @property
    def current_package(self) -> Package:
        """Get the current package selected."""
        name = self.data[self.cursor_cell.row][0]
        package = self.pkgs[name]
        return package

    class RowChanged(Message):
        """Event sent when we change the displayed package in the list."""

        def __init__(self, sender: MessageTarget, package: Package) -> None:
            self.package = package
            super().__init__(sender)

    async def send_row_changed(self) -> None:
        """Send an row changed update event."""
        row = self.cursor_cell.row
        if row < 0:
            row = 0
        package_name = self.data[row][0]
        package = self.pkgs.get(package_name)
        if package is not None:
            await self.emit(self.RowChanged(self, package=package))

    async def key_down(self, event: events.Key) -> None:
        """Hooked into key down to send row changed event to the app."""
        super().key_down(event)
        await self.send_row_changed()

    async def key_up(self, event: events.Key) -> None:
        """Hooked into key up to send row changed event to the app."""
        super().key_up(event)
        await self.send_row_changed()

    async def on_click(self, event: events.Click) -> None:
        # User clicked on a data-row. perform default
        if self.hover_cell.row > 0:
            super().on_click(event)
            return

        # User clicked on the header, re-do the content.
        col = self.hover_cell.column
        if 0 <= col < 3:
            await self.re_sort_display(column=col)
        else:
            # Not a known column, just use default
            await self.re_sort_display()

    async def on_mount(self):
        """Stylish"""
        self.add_column("name")
        self.add_column("binaries")
        self.add_column("dependents")

        packages, depends, rdepends = scan_packges()
        filtered = filter_packages(packages, depends, rdepends)
        for p in filtered:
            assert p.name == str(p.pkg)

        for p in filtered:
            self.pkgs[str(p.pkg)] = p

        await self.re_sort_display()

    async def re_sort_display(self, column: int = -1):
        """As we cannot sort the data without re-adding it, this re-adds the
        data."""
        self.clear()
        rows = [
            (str(p.pkg), pkg_binaries(p.pkg), p.needed_by) for p in self.pkgs.values()
        ]

        if column == -1:
            # Sort by name first
            rows.sort(key=itemgetter(0))
            # Then re-sort by dependencies
            rows.sort(key=itemgetter(2), reverse=True)
            # And finally sort by binaries
            rows.sort(key=itemgetter(1), reverse=True)
        else:
            # We sort column 0 by name, the rest we sort decreasing
            reverse = column > 0
            rows.sort(key=itemgetter(column), reverse=reverse)

        for row in rows:
            # All columns must be the same data-type, so cast it to string
            # first.
            self.add_row(row[0], str(row[1]), str(row[2]))
        await self.send_row_changed()


class InfoDisplay(TextLog, can_focus=True):
    """Widget of the information pane."""

    text = reactive("text")
    description = reactive("text")

    def clear(self):
        super().clear()
        # Manually clean the line cache, otherwise it will contain stale
        # refernces
        self._line_cache.clear()


#    def render(self) -> str:
#        self.write(f"{self.text}\n\n{self.description}")


class ThatApp(App[List[str]]):
    """Start using an app toolkit."""

    CSS = """
    Screen {
        layout: grid;
        grid-size: 3 2;
        grid-columns: 2fr 1fr;
        grid-rows: 70% 30%;
        layers: below above;

    }
    .box {
        height: 100%;
        border: solid green;
        layer: below;
    }
    InfoDisplay {
        layout: vertical;
    }
    ListDisplay {
    }
    #list {
        column-span: 2;
    }
    #Unwanted {
    }
    #extra {
    }
    #info {
        column-span: 2;
    }
    .box:blur {
        border: round white;
    }
    .box:focus {
        background: darkblue;
        border: round yellow;
        overflow-y: scroll;
        overflow: auto;
    }
    """

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("m", "mark_unwanted", "Toggle (un)wanted"),
        ("i", "show_info", "Show package description"),
        ("f", "show_files", "Show package files"),
        ("escape", "exit_app", "Time to escape"),
    ]

    def on_list_display_row_changed(self, message: ListDisplay.RowChanged) -> None:
        """Recieves RowChanged events from ListDisplay class."""
        table = self.query_one(ListDisplay)
        package = table.current_package
        # package = message.package
        info = str(package.pkg.summary)
        desc = str(package.pkg.description)
        name = str(package.pkg)
        assert str(package.pkg) == message.package.name
        idt = self.query_one(InfoDisplay)
        text = f"{package.pkg.summary}\n\n{package.pkg.description}"
        idt.write(text)
        idt.clear()
        idt.write(text)
        deps = Markdown(
            f"### Packages that need {name}\n    " + " ".join(message.package.rdepends)
        )
        self.query_one("#extra").update(deps)

    def on_mount(self, event: events.Mount) -> None:
        self.title = "dnf....humbug"
        self.sub_title = "List of packages DNF thinks you want."
        self.unwanted = set()

    def compose(self) -> ComposeResult:
        """Create child widgets for that App."""
        yield Header()
        display = ListDisplay(id="list", classes="box")
        display.focus()
        yield display
        yield Static(Markdown("### Final command line"), id="Unwanted", classes="box")
        yield InfoDisplay(max_lines=50, id="info", classes="box")
        yield Static("", id="extra", classes="box")
        yield Footer()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_show_info(self) -> None:
        """When we want more info."""
        table = self.query_one(ListDisplay)
        table.focus()
        info = self.query_one(InfoDisplay)
        info.clear()
        package = table.current_package
        if package:
            info.write(package.pkg.description)

    def action_show_files(self) -> None:
        """When we want file info."""
        table = self.query_one(ListDisplay)
        package = table.current_package
        if package:
            content = "\n".join(row for row in package.pkg.files)
            info = self.query_one(InfoDisplay)
            info.clear()
            info.write(content)
            info.focus()
            # info.scroll_home()

    def action_mark_unwanted(self) -> None:
        """When we want more info."""
        table = self.query_one(ListDisplay)
        table.focus()
        pkg = table.current_package.pkg
        if pkg in self.unwanted:
            self.unwanted.remove(pkg)
        else:
            self.unwanted.add(pkg)
        names = sorted(str(p) for p in self.unwanted)
        untext = Markdown(
            "### Final command line\n"
            + "    dnf mark remove\n     "
            + "\n     ".join(names)
        )
        self.query_one("#Unwanted").update(untext)

    def action_exit_app(self):
        """When we want out."""
        names = (pkg.name for pkg in self.unwanted)
        output = " ".join(sorted(names))
        if output:
            result = f"dnf mark remove {output}"
        else:
            result = ""
        self.exit(result)


# Todo, mark remove
# https://github.com/rpm-software-management/dnf/blob/master/dnf/cli/commands/mark.py
# has details


def main():
    app = ThatApp()
    unwanted = app.run()
    print(unwanted)
