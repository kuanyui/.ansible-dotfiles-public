#!/bin/bash
# =============================================================================
# MANAGED BY ANSIBLE - DO NOT EDIT MANUALLY
# (source: roles/mpv/files/KDE_global_shortcuts_examples.sh)
# =============================================================================
# Reference snippets for KDE global shortcuts - NOT executed by anything.
# Each line is one candidate shortcut command. Requires `input-ipc-server`
# uncommented in mpv.conf (off by default) and the `socat` package.
bash -c "echo 'ab-loop' | socat - /tmp/mpvsocket"
bash -c "echo 'cycle pause' | socat - /tmp/mpvsocket"
bash -c "echo 'seek -3 exact' | socat - /tmp/mpvsocket"
bash -c "echo 'seek +3 exact' | socat - /tmp/mpvsocket"
