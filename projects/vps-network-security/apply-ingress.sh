#!/bin/sh
set -eu
config=/etc/vps-network-security/ingress.nft
if /usr/sbin/nft list table inet vps_ingress_guard >/dev/null 2>&1; then
  { printf '%s\n' 'delete table inet vps_ingress_guard'; cat "$config"; } | /usr/sbin/nft -f -
else
  /usr/sbin/nft -f "$config"
fi
