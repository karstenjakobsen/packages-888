#!/bin/sh
# Runs in isolated network namespaces, with no external traffic.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
server=vps-ingress-test-server
client=vps-ingress-test-client
cleanup() {
  ip netns pids "$server" 2>/dev/null | xargs -r kill || :
  ip netns del "$client" 2>/dev/null || :
  ip netns del "$server" 2>/dev/null || :
}
trap cleanup EXIT INT TERM
! ip netns list | grep -q 'vps-ingress-test-'
ip netns add "$server"
ip netns add "$client"
ip link add vps-test-s type veth peer name vps-test-c
ip link set vps-test-s netns "$server"
ip link set vps-test-c netns "$client"
ip -n "$server" link set vps-test-s name ens6
ip -n "$server" link set lo up
ip -n "$client" link set lo up
ip -n "$server" addr add 198.18.0.1/24 dev ens6
ip -n "$client" addr add 198.18.0.2/24 dev vps-test-c
ip -n "$client" addr add 86.52.144.219/32 dev vps-test-c
ip -n "$client" addr add 87.49.147.6/32 dev vps-test-c
ip -n "$server" -6 addr add fd00:888::1/64 dev ens6 nodad
ip -n "$client" -6 addr add fd00:888::2/64 dev vps-test-c nodad
ip -n "$server" link set ens6 up
ip -n "$client" link set vps-test-c up
ip -n "$server" route add default via 198.18.0.2
ip netns exec "$server" nft -f "$source_dir/ingress.nft"
ip netns exec "$server" python3 -m http.server 8080 --bind :: >/dev/null 2>&1 &
sleep 1
for administrator in 86.52.144.219 87.49.147.6; do
  ip netns exec "$client" curl --noproxy '*' -fsS --interface "$administrator" --max-time 3 http://198.18.0.1:8080/ >/dev/null
  echo "PASS allowed IPv4 $administrator"
done
if ip netns exec "$client" curl --noproxy '*' -fsS --max-time 2 http://198.18.0.1:8080/ >/dev/null 2>&1; then exit 1; fi
echo "PASS disallowed IPv4"
if ip netns exec "$client" curl --noproxy '*' -g -fsS --max-time 2 'http://[fd00:888::1]:8080/' >/dev/null 2>&1; then exit 1; fi
echo "PASS disallowed IPv6"
ip netns exec "$server" curl --noproxy '*' -g -fsS --max-time 2 'http://[::1]:8080/' >/dev/null
echo "PASS local loopback"
ip netns exec "$server" nft list table inet vps_ingress_guard
