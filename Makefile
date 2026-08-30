# InkClip installer.
#
#   make user-install            per-user install into ~/.local (no root)
#   sudo make install            system-wide install into /usr/local
#   sudo make install PREFIX=/usr
#   make user-uninstall / sudo make uninstall
#
# DESTDIR is honoured for packaging (see PKGBUILD).

PREFIX  ?= /usr/local
DESTDIR ?=
PYTHON  ?= /usr/bin/python3

BINDIR     := $(DESTDIR)$(PREFIX)/bin
APPDIR     := $(DESTDIR)$(PREFIX)/share/inkclip
DESKTOPDIR := $(DESTDIR)$(PREFIX)/share/applications
ICONDIR    := $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps

.PHONY: help install uninstall user-install user-uninstall update-caches check run

help:
	@echo 'InkClip make targets:'
	@echo '  make user-install     install into ~/.local (shows up in rofi, no root)'
	@echo '  sudo make install     install into $(PREFIX)'
	@echo '  make user-uninstall   remove the ~/.local install'
	@echo '  sudo make uninstall   remove the $(PREFIX) install'
	@echo '  make check            validate the generated .desktop entry'
	@echo '  make run              run straight from this checkout'

install:
	install -Dm644 main.py $(APPDIR)/main.py
	install -Dm644 packaging/inkclip.svg $(ICONDIR)/inkclip.svg
	# Launcher with the install prefix baked in, so it works regardless of PATH.
	install -d $(BINDIR)
	printf '#!/bin/sh\nexec %s %s/main.py "$$@"\n' \
		'$(PYTHON)' '$(PREFIX)/share/inkclip' > $(BINDIR)/inkclip
	chmod 755 $(BINDIR)/inkclip
	# Absolute Exec= keeps rofi/desktop launches working even if bin/ is not on PATH.
	install -d $(DESKTOPDIR)
	sed 's|@BINDIR@|$(PREFIX)/bin|g' packaging/inkclip.desktop.in \
		> $(DESKTOPDIR)/inkclip.desktop
	chmod 644 $(DESKTOPDIR)/inkclip.desktop
ifeq ($(strip $(DESTDIR)),)
	@$(MAKE) --no-print-directory update-caches
	@echo 'InkClip installed. Launch it from rofi, or run: $(PREFIX)/bin/inkclip'
endif

uninstall:
	rm -f $(BINDIR)/inkclip
	rm -f $(DESKTOPDIR)/inkclip.desktop
	rm -f $(ICONDIR)/inkclip.svg
	rm -rf $(APPDIR)
ifeq ($(strip $(DESTDIR)),)
	@$(MAKE) --no-print-directory update-caches
	@echo 'InkClip removed from $(PREFIX).'
endif

user-install:
	@$(MAKE) --no-print-directory install PREFIX=$(HOME)/.local

user-uninstall:
	@$(MAKE) --no-print-directory uninstall PREFIX=$(HOME)/.local

# Refresh the desktop/icon caches so launchers notice the change right away.
update-caches:
	@command -v update-desktop-database >/dev/null 2>&1 && \
		update-desktop-database "$(PREFIX)/share/applications" 2>/dev/null || true
	@command -v gtk-update-icon-cache >/dev/null 2>&1 && \
		gtk-update-icon-cache -qtf "$(PREFIX)/share/icons/hicolor" 2>/dev/null || true

check:
	@sed 's|@BINDIR@|$(PREFIX)/bin|g' packaging/inkclip.desktop.in > /tmp/inkclip-check.desktop
	@desktop-file-validate /tmp/inkclip-check.desktop && echo 'desktop entry OK'
	@rm -f /tmp/inkclip-check.desktop

run:
	@$(PYTHON) main.py
