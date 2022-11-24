from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input


from textual.containers import Container
from textual.widgets import Button, Header, Footer, Static
from textual import events
import asyncio

from rich.table import Table
import os
import dnf
import libdnf.transaction


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


def filter_packages(packages, depends, rdepends):
    binaries = []
    non_binaries = []
    has_deps = []
    non_deps = []

    print("Filtering results")
    for i, pkg in enumerate(packages):
        if pkg.reason == "user":
            if rdepends[i]:
                has_deps.append(pkg)
            else:
                non_deps.append(pkg)
            if any('/usr/bin' in s for s in pkg.files):
                binaries.append(pkg)
            else:
                non_binaries.append(pkg)
    return binaries, non_binaries, has_deps, non_deps


class ListDisplay(Static):
    """Widget of our list of thingies."""

    def done_on_mount(self):
        """Stylish"""
        self.styles.background = "darkblue"
        self.styles.border = ("round", "white")
        packages, depends, rdepends = scan_packges()
        binaries, non_binaries, has_deps, non_deps = filter_packages(packages,
                                                                     depends,
                                                                     rdepends)
        t = Table(title="Packages marked as user installed")
        t.add_column("name")
        t.add_column("dependencies")
        t.add_column("dependents")
        for pkg in  has_deps:
            for pkg in non_binaries:
                t.add_row(str(pkg)   )
        self.update(t)

    def on_mount(self):
        """Stylish"""
        self.styles.background = "darkblue"
        self.styles.border = ("round", "white")
        self.update("I have been mounted")

    def on_selected(self):
        self.update("Now I am selected")


class InfoDisplay(Static):
    """Widget of the information pane."""
    def on_mount(self):
        """Stylish"""
        self.styles.border = ("round", "yellow")
        self.styles.height = "15%"
        self.styles.width = "100%"


class That(Static):
    """The widget we use."""
    def compose(self) -> ComposeResult:
        """Create child widgets of the app."""
        yield ListDisplay()
        yield InfoDisplay("no info", id="info")
        yield Button("Start", id="start", variant="success")


class ThatApp(App):
    """Start using an app toolkit."""

    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("spacebar", "show_info", "Show more info"),
        ("escape", "exit_app", "Time to escape"),
    ]

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

    def on_list_display_selected(self):
        self.query_one(ListDisplay).update("Selected once")


    def compose(self) -> ComposeResult:
        """Create child widgets for that App."""
        yield Header()
        yield Footer()
        yield Container(That())

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    def action_show_info(self) -> None:
        """When we want more info."""
        self.query_one("#info").update("Show info")
        self.query_one("#start").update("Show info")

    def action_exit_app(self) -> None:
        """When we want out."""
        self.exit()


if __name__ == "__main__":
    app = ThatApp()
    app.run()
