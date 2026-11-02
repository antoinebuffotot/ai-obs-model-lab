#!/bin/sh
# Install a pinned dtctl release (Dynatrace CLI) into /usr/local/bin, checksum verified.
# Downloads the release asset directly (no GitHub API call, so no rate limit on shared cloud IPs).
# Never fails the image build: on error it prints a WARNING and the dtctl tool stays unavailable.
#   install-dtctl.sh [version]        (default 0.45.0)
VERSION="${1:-0.45.0}"
arch="$(dpkg --print-architecture 2>/dev/null || echo amd64)"
file="dtctl_${VERSION}_linux_${arch}.tar.gz"
base="https://github.com/Dynatrace/dtctl/releases/download/v${VERSION}"
tmp="$(mktemp -d)"
(
  set -e
  cd "$tmp"
  curl -fsSL --retry 3 -O "$base/$file"
  curl -fsSL --retry 3 -O "$base/checksums.txt"
  grep " $file\$" checksums.txt | sha256sum -c -
  mkdir x
  tar -xzf "$file" -C x
  bin="$(find x -name dtctl -type f | head -1)"
  test -n "$bin"
  install -m 0755 "$bin" /usr/local/bin/dtctl
  /usr/local/bin/dtctl --help >/dev/null
) && echo "dtctl ${VERSION} installed" || echo "WARNING: dtctl ${VERSION} installation FAILED - the dtctl tool will be unavailable"
rm -rf "$tmp"
exit 0
