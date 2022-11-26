from dataclasses import dataclass
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
    info: str
    has_binaries: bool
    _pkg: Any
    _rdepends: List[Any]

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


def filter_packages(packages: List[Pkg], depends, rdepends):
    result = []
    for i, pkg in enumerate(packages):
        if pkg.reason == "user":
            has_binaries = any("bin/" in s for s in pkg.files)
            # rdepends can have multiple (duplicate) entries, deduplicate first.
            unique_deps = set(rdepends[i])
            needed_by = len(unique_deps)
            _rdepends = [str(packages[n]) for n in unique_deps]

            p = Package(
                name=str(pkg),
                needed_by=needed_by,
                info=pkg.summary,
                has_binaries=has_binaries,
                _pkg=pkg,
                _rdepends=_rdepends,
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
        package_name = self.data[self.cursor_cell.row][0]
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

    async def on_mount(self):
        """Stylish"""
        # self.styles.background = "darkblue"
        self.add_column("name")
        self.add_column("binaries")
        self.add_column("dependents")

        packages, depends, rdepends = scan_packges()
        filtered = filter_packages(packages, depends, rdepends)

        for pkg in filtered:
            self.pkgs[pkg.name] = pkg
        # Quite likely, no binaries, and nothing needs it.
        # Could be dev package, etc.
        for pkg in filtered:
            if (not pkg.has_binaries) and pkg.needed_by > 0:
                self.add_row(pkg.name, str(pkg.has_binaries), str(pkg.needed_by))

        # No deps, but doesn't isntall binaries.
        # Could be a dev package (headers, etc) or service (usr/libexec etc..)
        for pkg in filtered:
            if pkg.needed_by == 0 and not pkg.has_binaries:
                self.add_row(pkg.name, str(pkg.has_binaries), str(pkg.needed_by))

        # Has binaries, but also dependents.
        for pkg in filtered:
            if pkg.has_binaries and pkg.needed_by > 0:
                self.add_row(pkg.name, str(pkg.has_binaries), str(pkg.needed_by))

        # Least likely to be our choice, no deps and installs binaries
        for pkg in filtered:
            if pkg.needed_by == 0 and pkg.has_binaries:
                self.add_row(pkg.name, str(pkg.has_binaries), str(pkg.needed_by))
        await self.send_row_changed()


class InfoDisplay(TextLog):
    """Widget of the information pane."""

    text = reactive("text")
    description = reactive("text")


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
        ("i", "show_info", "Show description"),
        ("f", "show_files", "Show files"),
        ("m", "mark_unwanted", "Mark as unwanted"),
        ("escape", "exit_app", "Time to escape"),
    ]

    def on_list_display_row_changed(self, message: ListDisplay.RowChanged) -> None:
        """Recieves RowChanged events from ListDisplay class."""
        self.query_one(InfoDisplay).clear()
        self.query_one(InfoDisplay).write(message.package.info)
        self.query_one(InfoDisplay).write("")
        self.query_one(InfoDisplay).write(message.package._pkg.description)
        deps = Markdown(
            "### Packages that need this:\n" + "\n".join(message.package._rdepends)
        )
        self.query_one("#extra").update(deps)

    def on_mount(self, event: events.Mount) -> None:
        self.unwanted = set()

    def compose(self) -> ComposeResult:
        """Create child widgets for that App."""
        yield Header()
        display = ListDisplay(id="list", classes="box")
        display.focus()
        yield display
        yield Static(
            Markdown("### Marked these as unwanted"), id="Unwanted", classes="box"
        )
        yield InfoDisplay(id="info", classes="box")
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
        package = table.current_package
        if package:
            info.clear()
            info.write(package._pkg.description)

    def action_show_files(self) -> None:
        """When we want file info."""
        table = self.query_one(ListDisplay)
        package = table.current_package
        if package:
            content = "\n".join(row for row in package._pkg.files)
            info = self.query_one(InfoDisplay)
            info.clear()
            info.write(content)
            info.focus()
            # info.scroll_home()

    def action_mark_unwanted(self) -> None:
        """When we want more info."""
        table = self.query_one(ListDisplay)
        table.focus()
        pkg = table.current_package._pkg
        if pkg in self.unwanted:
            self.unwanted.remove(pkg)
        else:
            self.unwanted.add(pkg)
        names = sorted(pkg.name for pkg in self.unwanted)
        untext = "\n".join(names)
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
