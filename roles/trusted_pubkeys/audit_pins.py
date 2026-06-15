#!/usr/bin/env python3
"""On-demand audit of the SSH host-key pins in vars/main.yml.

Re-checks every pinned fingerprint in `trusted_pubkeys_ssh_host_keys` against its
live AUTHORITATIVE sources, so a maintainer can spot when a forge has rotated a
key (pin gone stale) or when a pin no longer matches anything trustworthy:

  - HTTPS instance_configuration page (`source`): the pinned SHA256 must still
    appear verbatim in the page body. A page need not list every key type (e.g.
    GNOME's omits RSA), so ABSENCE from the page is inconclusive, not a failure.
  - DNSSEC-signed SSHFP DNS records: the pinned key's SHA256 must appear under
    its algorithm in the host's SSHFP set AND the zone must be DNSSEC-validated
    (dig `ad` flag). An SSHFP set present but NOT DNSSEC-signed is spoofable, so
    it does not count as confirmation.

Per-key verdict:
  - OK          confirmed by at least one authoritative source.
  - ALERT       a trustworthy source contradicts the pin - the DNSSEC SSHFP for
                this algorithm is a DIFFERENT key (rotation), or only an
                un-signed SSHFP matches. Investigate before trusting.
  - UNCONFIRMED could not positively confirm and found no contradiction (sources
                unreachable, key type absent from the page, no SSHFP, or `dig`
                missing). Re-run on a host with network + `dig`.

The script exits non-zero unless every key is OK. Read-only: outbound HTTPS + DNS
only; it writes nothing. Maintainer tool, NOT deployed by the role.

Usage:
    python3 roles/trusted_pubkeys/audit_pins.py
"""
from __future__ import annotations

import base64
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

VARS_PATH = Path(__file__).resolve().parent / "vars" / "main.yml"
BROWSER_USER_AGENT = "Mozilla/5.0 (audit_pins.py; ansible-dotfiles trusted_pubkeys)"
VALIDATING_RESOLVER = "1.1.1.1"

# known_hosts key type -> SSHFP algorithm number (RFC 4255 / 6594 / 7479).
KEYTYPE_TO_SSHFP_ALGORITHM = {
    "ssh-rsa": 1,
    "ecdsa-sha2-nistp256": 3,
    "ecdsa-sha2-nistp384": 3,
    "ecdsa-sha2-nistp521": 3,
    "ssh-ed25519": 4,
}


def fingerprint_sha256_to_hex(sha256_fingerprint: str) -> str:
    """'SHA256:Y9G4..b64..' -> lowercase hex of the raw digest (the SSHFP form)."""
    base64_without_padding = sha256_fingerprint.split(":", 1)[1]
    padded = base64_without_padding + "=" * (-len(base64_without_padding) % 4)
    return base64.b64decode(padded).hex()


def fetch_https_page(source_url: str) -> str | None:
    """Fetch a forge's published-fingerprints page; None on any network error."""
    print(f"    GET  {source_url}")
    request = urllib.request.Request(source_url, headers={"User-Agent": BROWSER_USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, ValueError) as fetch_error:
        print(f"         (fetch failed: {fetch_error})")
        return None


def dnssec_validated_sshfp(ssh_host: str) -> tuple[bool, dict[int, set[str]]] | None:
    """Return (dnssec_validated, {sshfp_algorithm: {sha256_hex, ...}}) for the host
    via a validating resolver, or None if `dig` is not installed."""
    dig_argv = ["dig", "+dnssec", f"@{VALIDATING_RESOLVER}", "SSHFP", ssh_host,
                "+noall", "+comments", "+answer"]
    print(f"    dig  {' '.join(dig_argv[1:])}")
    try:
        dig_result = subprocess.run(dig_argv, capture_output=True, text=True)
    except FileNotFoundError:
        print("         (dig not installed - skipping the SSHFP check)")
        return None
    dnssec_validated = any(
        "flags:" in line and " ad" in line for line in dig_result.stdout.splitlines()
    )
    algorithm_to_sha256_hexes: dict[int, set[str]] = {}
    for line in dig_result.stdout.splitlines():
        if "SSHFP" not in line or line.lstrip().startswith(";"):
            continue
        tokens_after_sshfp = line.split("SSHFP", 1)[1].split()
        # tokens: <algorithm> <fingerprint_type> <hex...>; fingerprint_type 2 == SHA-256
        if len(tokens_after_sshfp) >= 3 and tokens_after_sshfp[1] == "2":
            algorithm = int(tokens_after_sshfp[0])
            joined_hex = "".join(tokens_after_sshfp[2:]).lower()
            algorithm_to_sha256_hexes.setdefault(algorithm, set()).add(joined_hex)
    return dnssec_validated, algorithm_to_sha256_hexes


def verdict_for_key(
    key_type: str,
    pinned_fingerprint: str,
    page_body: str | None,
    sshfp_lookup: tuple[bool, dict[int, set[str]]] | None,
) -> tuple[str, list[str], list[str]]:
    """Return (verdict, confirmed_by, notes) for one pinned key. verdict is one of
    OK / ALERT / UNCONFIRMED (see module docstring)."""
    pinned_base64 = pinned_fingerprint.split(":", 1)[1]
    pinned_hex = fingerprint_sha256_to_hex(pinned_fingerprint)
    confirmed_by: list[str] = []
    contradictions: list[str] = []
    notes: list[str] = []

    if page_body is None:
        notes.append("HTTPS page unreachable")
    elif pinned_base64 in page_body:
        confirmed_by.append("HTTPS page")
    else:
        notes.append("not listed on HTTPS page (page may omit this key type)")

    if sshfp_lookup is None:
        notes.append("dig unavailable (SSHFP not checked)")
    else:
        dnssec_validated, algorithm_to_hexes = sshfp_lookup
        hexes_for_algorithm = algorithm_to_hexes.get(KEYTYPE_TO_SSHFP_ALGORITHM.get(key_type, -1), set())
        if pinned_hex in hexes_for_algorithm and dnssec_validated:
            confirmed_by.append("DNSSEC SSHFP")
        elif pinned_hex in hexes_for_algorithm:
            contradictions.append("SSHFP matches but the zone is NOT DNSSEC-signed (spoofable)")
        elif hexes_for_algorithm and dnssec_validated:
            contradictions.append(f"DNSSEC SSHFP for {key_type} is a DIFFERENT key - rotated?")
        elif hexes_for_algorithm:
            notes.append("SSHFP lists a different key but the zone is not DNSSEC-signed")
        else:
            notes.append("no SSHFP record for this key type")

    if confirmed_by:
        return "OK", confirmed_by, notes
    if contradictions:
        return "ALERT", confirmed_by, contradictions + notes
    return "UNCONFIRMED", confirmed_by, notes


def audit() -> int:
    forges = yaml.safe_load(VARS_PATH.read_text())["trusted_pubkeys_ssh_host_keys"]
    alerts: list[str] = []
    unconfirmed: list[str] = []

    for forge in forges:
        ssh_host = forge["host"]
        print(f"\n=== {ssh_host}  (source: {forge['source']}) ===")
        page_body = fetch_https_page(forge["source"])
        sshfp_lookup = dnssec_validated_sshfp(ssh_host)

        for key in forge["keys"]:
            key_type = key["line"].split()[1]
            verdict, confirmed_by, notes = verdict_for_key(
                key_type, key["fingerprint"], page_body, sshfp_lookup
            )
            print(f"  {key_type:20} {key['fingerprint']}")
            print(f"      confirmed by : {', '.join(confirmed_by) or '(none)'}")
            if notes:
                print(f"      note         : {'; '.join(notes)}")
            print(f"      -> {verdict}")
            if verdict == "ALERT":
                alerts.append(f"{ssh_host} {key_type}: {'; '.join(notes)}")
            elif verdict == "UNCONFIRMED":
                unconfirmed.append(f"{ssh_host} {key_type}: {'; '.join(notes)}")

    print("\n" + "=" * 64)
    if alerts:
        print(f"ALERT - {len(alerts)} pin(s) contradicted by a source:")
        for item in alerts:
            print(f"  - {item}")
    if unconfirmed:
        print(f"UNCONFIRMED - {len(unconfirmed)} pin(s) could not be checked:")
        for item in unconfirmed:
            print(f"  - {item}")
    if not alerts and not unconfirmed:
        print("AUDIT OK - every pinned key confirmed by an authoritative source.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(audit())
