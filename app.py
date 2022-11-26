import os
import asyncio

import dnf
import libdnf.transaction

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input


from textual.containers import Container
from textual.widgets import Button, Header, Footer, Static
from textual import events
from textual.widgets import DataTable
from textual import events
from textual.message import Message, MessageTarget


def scan_packges():
    """Main entrypoint. Does stuff, sometimes sanely."""
    base = dnf.Base()

    packages = []
    rdepends = []
    pkgmap = {}

    print("Querying rpm database")
    query = dnf.sack._rpmdb_sack(base).query().apply()
    for i,pkg in enumerate(query):
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
           if sreq.startswith('rpmlib('):
               continue
           if sreq == 'solvable:prereqmarker':
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

from dataclasses import dataclass
from typing import Any, List

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


def filter_packages(packages, depends, rdepends):
    result = []
    print("Filtering results")
    for i, pkg in enumerate(packages):
        if pkg.reason == "user":
            has_binaries = any("bin/" in s for s in pkg.files)
            needed_by = len(rdepends[i])
            _rdepends = [str(packages[n]) for n in rdepends[i]]

            p = Package(name=str(pkg), needed_by=needed_by,
                        info=pkg.description, has_binaries=has_binaries,
                        _pkg=pkg, _rdepends=_rdepends)
            result.append(p)
    return result



class ListDisplay(DataTable):
    """Widget of our list of thingies."""
    def __init__(self, *args, **kws):
        super().__init__(*args, **kws)
        self.pkgs = {}

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
        self.styles.background = "darkblue"
        self.styles.border = ("round", "white")
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


from textual.reactive import reactive


class InfoDisplay(Static):
    """Widget of the information pane."""
    text = reactive("text")
    dependents = reactive("text")

    def render(self) -> str:
        return f"{self.text} \n\nNeeded by:\n\t{self.dependents}"

    def on_mount(self):
        """Stylish"""
        self.styles.border = ("round", "yellow")
        self.styles.dock = "bottom"
        self.styles.width = "100%"
        self.styles.height = "30%"


class ThatApp(App):
    """Start using an app toolkit."""

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("spacebar", "show_info", "Show more info"),
        ("escape", "exit_app", "Time to escape"),
    ]


    def on_list_display_row_changed(self, message: ListDisplay.RowChanged) -> None:
        """Recieves RowChanged events from ListDisplay class."""
        self.query_one(InfoDisplay).text = message.package.info
        deps = "\n\t".join(message.package._rdepends)
        self.query_one(InfoDisplay).dependents = deps


    async def on_input_changed(self, message: Input.Changed) -> None:
        """Event handler on input."""
        if message.value:
            asyncio.create_task(self.lookup_info(message.value))
        else:
            self.query_one("#info", InfoDisplay).update("empty")

    async def lookup_info(self, word: str) -> None:
        """check out the word"""
        # Do some logic here
        self.query_one("#info", "InfoDisplay").update(word + "word")

    def on_mount(self, event: events.Mount) -> None:
        self.query_one(ListDisplay).focus()

#    def on_list_display_selected(self):
#        self.query_one(ListDisplay).update("Selected once")


    def compose(self) -> ComposeResult:
        """Create child widgets for that App."""
        yield Header()
        yield ListDisplay()
        yield InfoDisplay("no info", id="info")
        yield Footer()

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_show_info(self) -> None:
        """When we want more info."""
        self.query_one("#info").update("Show info")

    def action_exit_app(self) -> None:
        """When we want out."""
        self.exit()
# Todo, mark remove
# https://github.com/rpm-software-management/dnf/blob/master/dnf/cli/commands/mark.py
# has details

if __name__ == "__main__":
    app = ThatApp()
    app.run()
