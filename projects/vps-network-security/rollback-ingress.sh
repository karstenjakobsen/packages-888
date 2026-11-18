#!/bin/sh
set -eu
systemctl disable --now vps-ingress-guard.service
if /usr/sbin/nft list table inet vps_ingress_guard >/dev/null 2>&1; then
  /usr/sbin/nft delete table inet vps_ingress_guard
fi
echo "Removed only owner ingress gate; original UFW/Tailscale/Docker rules retained."
