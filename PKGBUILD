# Maintainer: HaxNet <simon@108cap.com>
pkgname=inkclip
pkgver=0.1.0
pkgrel=1
pkgdesc="Fast scratchpad drawing app that copies straight to the clipboard"
arch=('any')
url="https://github.com/HaxNet/InkClip"
# TODO: add a LICENSE file to the repo, then set this properly (e.g. 'MIT').
license=('custom')
depends=('python' 'pyside6')
optdepends=('qt6-wayland: native Wayland support (recommended on Wayland compositors)')
makedepends=('make')

# Builds straight from this checkout, so `makepkg -si` works in the repo.
source=()
sha256sums=()

# To publish this on the AUR instead, replace the package() body below with a
# real source tarball:
#   source=("$pkgname-$pkgver.tar.gz::$url/archive/refs/tags/v$pkgver.tar.gz")
#   sha256sums=('<checksum>')
#   package() { make -C "$srcdir/InkClip-$pkgver" DESTDIR="$pkgdir" PREFIX=/usr install; }

package() {
	make -C "$startdir" DESTDIR="$pkgdir" PREFIX=/usr install
}
