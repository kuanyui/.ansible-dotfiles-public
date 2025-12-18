#!/usr/bin/env bash
set -euo pipefail

PACKAGE_LIST="emacs-packages.txt"

# Check if package list file exists
if [[ ! -f "$PACKAGE_LIST" ]]; then
  echo "Error: $PACKAGE_LIST not found"
  exit 1
fi

sudo apt update

# Read package list line by line
while IFS= read -r line; do
  # Trim leading and trailing whitespace
  pkg="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

  # Skip empty lines
  [[ -z "$pkg" ]] && continue

  # Skip commented lines
  [[ "$pkg" == \#* ]] && continue

  echo "Installing: $pkg"
  sudo apt install -y "$pkg"

done < "$PACKAGE_LIST"
