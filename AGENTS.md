This repository contains Debian packaging for the MComix image viewer. The
goal is to carry small local fixes and produce installable `.deb` packages.

## Layout and workflow

- Work in `mcomix-<upstream-version>/`; Debian packaging lives in its
  `debian/` directory. Build artifacts belong in the repository root.
- Keep upstream code changes as DEP-3 quilt patches under `debian/patches/`
  and list them in `debian/patches/series`. Do not hand-edit `.pc/`.
- Create patches with `quilt new`, `quilt add <file>`, edit the file, then
  `quilt refresh`; add a short DEP-3 header to the resulting patch.
- For a local fix, increment the Debian revision in `debian/changelog`, add
  the patch, then rebuild both source and binary packages.
- For an upstream update, use the official tarball as
  `mcomix_<version>.orig.tar.gz`, carry forward `debian/`, drop patches that
  are upstream, refresh the remaining patches, and remove obsolete artifacts.

## Build and verification

From the repository root, build the source package with:

    dpkg-source -b mcomix-<version>

From inside the source directory, build binaries with:

    dpkg-buildpackage -us -uc -b

Verify the resulting package with `dpkg-deb --info`, inspect its contents,
run an `apt-get -s install ./<package>.deb` upgrade simulation, and perform a
targeted runtime smoke test for every local patch. Run `git diff --check` and
clean generated build directories before handing off. The checked-in source
tree keeps the patch series applied; restore that state after a build with
`dpkg-source --before-build .`.
