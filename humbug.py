#!/usr/bin/env python3
import os
import dnf
import libdnf.transaction


def present(pkg):
    pkgout = str(pkg)
    col = min(10, len(pkgout))
    target = os.get_terminal_size().columns - col
    pkgdesc = "\n".join(s.rjust(target) for s in pkg.description.split("\n"))
    print(pkgout)
    print(pkgdesc)
    print()

def main():
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

    print("\n", "*" * 32, "\n")
    print("Strong candidates for `dnf mark remove`  (Things depend on them, does not install binaries) `dnf mark remove `")
    print("*" * 32, "\n")
    for pkg in has_deps:
        if pkg in non_binaries:
            depended_on_by  = [str(packages[n]) for n in rdepends[i]]
            present(pkg)
            print("Depended on by: ", depended_on_by)

    print("\n", "*" * 32, "\n")
    print("Weak candidates for `dnf mark remove`  (Things depend on them, also installs binaries)")
    print("*" * 32, "\n")
    for pkg in has_deps:
        if pkg in binaries:
            depended_on_by  = [str(packages[n]) for n in rdepends[i]]
            present(pkg)
            print("depends on: ", str(depended_on_by))


    print("\n", "*" * 32, "\n")
    print("Candidates mark as dependency (nothing depends on them, does not install binaries)  `dnf mark remove`")
    print("*" * 32, "\n")
    for pkg in non_deps:
        if pkg in non_binaries:
            depends_on  = [str(packages[n]) for n in depends[i]]
            print("depends on: ", str(depends_on))
            present(pkg)

    print("\n", "*" * 32, "\n")
    print("These are probably expected, (nothing depends on them, but they install binaries)")
    print("*" * 32, "\n")
    for pkg in non_deps:
        if pkg in binaries:
            depends_on  = [str(packages[n]) for n in depends[i]]
            present(pkg)

if __name__ == "__main__":
    main()
