# dnf-humbug

[dnf-humbug](https://github.com/Spindel/dnf-humbug) tool lists packages that
are marked as "user installed" and gives a list of such, allowing a user to
adjust this.

"user installed" are packages the system thinks you have directly installed,
and are thus always kept and not removed automatically.

So, as my list of "user installed" packages included a ton of old dev packages,
lots of libraries I could not remember installing, I wanted something to make a
list out of those and see what was where.

One such way was this:

    comm -2 -3    <(dnf repoquery --userinstalled --qf '%{name}-%{version}-%{release}.%{arch}'|sort)  <(dnf leaves| sed 's/^[- ] //'|sort)


Clearly not optimal, so I wrote this utility.


# To install in a venv

    python3 -m venv --system-site-packages humbug-venv
    source humbug-venv/bin/activate
    pip install dnf-humbug


# Launching

Either use:

    python3 -m dnf_humbug

Or:

    dnf-humbug



# Bugs, Features, Issues?

Feel free to hack on it, I'll probably do too. I don't have a plan to port it
to dnf5 yet, but who knows, dnf5 might also annoy me and I'll have to do it
there as well.


# License

I snagged some code from the "dnf leaves" code when I started this, so we follow suit with GPLv2 license.


# Dependencies

This is not a DNF plugin, but a separate tool that uses python3-dnf on Fedora
(or other systems).

So make sure to install python3-dnf  and python3-textual,
or you can just have python3-dnf installed and use pypi to install textual.


