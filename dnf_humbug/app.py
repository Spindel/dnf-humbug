from dataclasses import dataclass
from operator import itemgetter
from typing import Any

# dnf is not typed for mypy
import dnf  # type: ignore
from dnf.package import Package as Pkg  # type: ignore
from rich.markdown import Markdown
from textual import events
from textual.app import App, ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Header, Static, TextLog


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
    rdepends: list[Any]

    def __repr__(self) -> str:
        return self.name

    def __str__(self) -> str:
        return self.name


def pkg_binaries(pkg) -> int:
    binaries = sum(["bin/" in s for s in pkg.files])
    return binaries


def filter_packages(packages: list[Pkg], _depends, rdepends):
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
        self.cursor_type = "row"

    @property
    def current_package(self) -> Package:
        """Get the current package selected."""
        row_key, _col_key = self.coordinate_to_cell_key(self.cursor_coordinate)
        name = self.get_row(row_key)[0]
        package = self.pkgs[name]
        return package

    class RowChanged(Message):
        """Event sent when we change the displayed package in the list."""

        def __init__(self, package: Package) -> None:
            self.package = package
            super().__init__()

    async def on_data_table_row_highlighted(self, message) -> None:
        package_name = self.get_row(message.row_key)[0]
        await self.send_row_changed(package_name=package_name)

    async def on_data_table_row_selected(self, message) -> None:
        package_name = self.get_row(message.row_key)[0]
        await self.send_row_changed(package_name=package_name)

    async def on_data_table_header_selected(self, message) -> None:
        reverse = message.column_index > 0
        self.sort(message.column_key, reverse=reverse)
        await self.send_row_changed()

    async def send_row_changed(self, package_name=None) -> None:
        """Send an row changed update event."""
        if package_name is None:
            row_key, _col_key = self.coordinate_to_cell_key(self.cursor_coordinate)
            package_name = self.get_row(row_key)[0]
        package = self.pkgs.get(package_name)
        if package is not None:
            self.post_message(self.RowChanged(package=package))

    async def on_mount(self):
        """Stylish"""
        self.add_columns("name", "binaries", "dependents")

        packages, depends, rdepends = scan_packges()
        filtered = filter_packages(packages, depends, rdepends)
        for p in filtered:
            assert p.name == str(p.pkg)

        for p in filtered:
            self.pkgs[str(p.pkg)] = p

        rows = [
            (str(p.pkg), pkg_binaries(p.pkg), p.needed_by) for p in self.pkgs.values()
        ]
        # Sort by name first
        rows.sort(key=itemgetter(0))
        # Then re-sort by dependencies
        rows.sort(key=itemgetter(2), reverse=True)
        # And finally sort by binaries
        rows.sort(key=itemgetter(1), reverse=True)
        for row in rows:
            self.add_row(row[0], row[1], row[2])
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


class ThatApp(App[str]):
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

    def update_info_display(self):
        """Only updates the info display, does not adjust scrolling or focus."""
        table = self.query_one(ListDisplay)
        package = table.current_package
        text = f"{package.pkg.summary}\n\n{package.pkg.description}"

        info = self.query_one(InfoDisplay)
        info.clear()
        info.write(text, scroll_end=False)

    def on_list_display_row_changed(self, message: ListDisplay.RowChanged) -> None:
        """Recieves RowChanged events from ListDisplay class."""
        table = self.query_one(ListDisplay)
        package = table.current_package
        name = str(package.pkg)
        self.update_info_display()
        deps = Markdown(
            f"### Packages that need {name}\n    " + " ".join(message.package.rdepends),
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
        inital_help = """### What is this?
DNF Humbug lists __user installed__ packages and lets you decide if you want
them or not.

DNF has a system to track which packages are __user installed__ and which ones
are only dependencies (transitive or not), and can then automatically remove
_unwanted_ packages.

However, as entropy gathers, so do these __user installed__ packages, keeping
old, unwanted or obsolete packages around.

DNF Humbug lists the __user installed__ packages, and lets you decide if you want
to keep them or not.

DNF Humbug does **NOT** remove any packages from your system, and only builds a
command line to help you.

For example, a package that is marked __user installed__ but which has no
binaries of it's own, and has multiple other packages depending on it, may be a
library or a dev-package, and should probably be considered a transient
dependency.

And a package that has nothing depending on it, but installs a few binaries,
may indeed be a tool that was once wanted, but not anymore.
"""
        yield display
        yield Static(Markdown(inital_help), id="Unwanted", classes="box")
        yield InfoDisplay(max_lines=None, auto_scroll=False, id="info", classes="box")
        yield Static("", id="extra", classes="box")
        yield Footer()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_show_info(self) -> None:
        """When we want more info."""
        table = self.query_one(ListDisplay)
        table.focus()
        self.update_info_display()

    def action_show_files(self) -> None:
        """When we want file info."""
        table = self.query_one(ListDisplay)
        package = table.current_package
        if package:
            content = "\n".join(row for row in package.pkg.files)
            info = self.query_one(InfoDisplay)
            info.clear()
            info.write(content, scroll_end=False)
            info.focus()

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
        # The amount of spaces after line-breaks are important due to markdown.
        # Heading + code-format
        indent = "\n    "
        pkglist = f"{indent} ".join(names)
        untext = Markdown(
            f"### Final command line{indent}dnf mark remove{indent} " + pkglist,
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


# TODO, mark remove
# https://github.com/rpm-software-management/dnf/blob/master/dnf/cli/commands/mark.py
# has details


def main():
    app = ThatApp()
    unwanted = app.run()
    print(unwanted)
