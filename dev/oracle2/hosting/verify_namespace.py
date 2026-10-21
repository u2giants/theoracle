#!/usr/bin/env python3
"""Owned invented traffic proves isolated gateway mode; no production mutation."""
import argparse
import json
import pathlib
import subprocess
import time

IMAGE = "node@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20"


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


def private_controlplane():
    import sys
    from pathlib import Path
    from urllib.parse import urlsplit
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'services' / 'oracle-brain'))
    from oracle_brain.private_targets import read_private_target
    endpoint = urlsplit(read_private_target('coolify_api_base_url'))
    return endpoint.hostname, endpoint.port or (443 if endpoint.scheme == 'https' else 80)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", required=True)
    parser.add_argument("--result", type=pathlib.Path, required=True)
    args = parser.parse_args()
    if not args.owner.replace("-", "").isalnum() or len(args.owner) > 40:
        raise ValueError("unsafe owner label")
    prefix = "oracle-hosting-" + args.owner
    network = prefix + "-isolated"
    server, client, unrelated = (prefix + suffix for suffix in ("-server", "-client", "-unrelated"))
    names = [server, client, unrelated]
    # Existing resources are never adopted or removed by this verifier.
    for name in [network, *names]:
        if subprocess.run(["docker", "inspect", name], capture_output=True).returncode == 0:
            raise RuntimeError("resource already exists: " + name)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    created = []
    network_created = False
    result = {"owner": args.owner, "synthetic": True, "production_mutated": False}
    try:
        docker("network", "create", "--internal", "--opt", "com.docker.network.bridge.gateway_mode_ipv4=isolated",
               "--opt", "com.docker.network.bridge.gateway_mode_ipv6=isolated",
               "--label", "oracle.hosting.synthetic=true", "--label", "oracle.owner=" + args.owner, network)
        network_created = True
        listen = "require('net').createServer(s=>{s.end('invented')}).listen(9000,'0.0.0.0');"
        for name, net, command in [(server, network, listen),
                                    (client, network, "setInterval(()=>{},1000)"),
                                    (unrelated, "bridge", "setInterval(()=>{},1000)")]:
            docker("run", "-d", "--name", name, "--network", net, "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges=true", "--read-only",
                   "--label", "oracle.hosting.synthetic=true", "--label", "oracle.owner=" + args.owner,
                   IMAGE, "node", "-e", command)
            created.append(name)
        inspection = json.loads(docker("network", "inspect", network))[0]
        result["network"] = inspection
        assert inspection["Internal"] is True
        assert all(not part.get("Gateway") for part in inspection["IPAM"]["Config"])
        assert inspection["Options"]["com.docker.network.bridge.gateway_mode_ipv4"] == "isolated"
        containers = json.loads(docker("inspect", *names))
        result["containers"] = containers
        for container in containers:
            assert container["HostConfig"]["PortBindings"] == {}
            assert container["HostConfig"]["Privileged"] is False
            assert "ALL" in container["HostConfig"]["CapDrop"]
            assert container["HostConfig"]["Binds"] is None
        address = containers[0]["NetworkSettings"]["Networks"][network]["IPAddress"]
        probe = """const net=require('net'); const host=process.argv[1], port=+process.argv[2];
const s=net.connect({host,port});s.setTimeout(800);s.on('connect',()=>{console.log('CONNECTED');s.destroy()});
s.on('timeout',()=>{console.log('DENIED:timeout');s.destroy()});s.on('error',e=>console.log('DENIED:'+e.code));"""
        # Container readiness is observed, not asserted after a blind sleep.
        positive = ""
        for _ in range(20):
            positive = docker("exec", client, "node", "-e", probe, address, "9000")
            if positive == "CONNECTED":
                break
            time.sleep(.05)
        assert positive == "CONNECTED", positive
        result["allowed_internal_peer"] = positive
        controlplane_host, controlplane_port = private_controlplane()
        for label, hostname, port in [("shared_controlplane", controlplane_host, str(controlplane_port)),
                                       ("shared_ssh", controlplane_host, "22"),
                                       ("internet_v4", "1.1.1.1", "443"),
                                       ("internet_v6", "2606:4700:4700::1111", "443")]:
            response = docker("exec", client, "node", "-e", probe, hostname, port)
            assert response.startswith("DENIED:"), response
            result[label] = response
        response = docker("exec", unrelated, "node", "-e", probe, address, "9000")
        assert response.startswith("DENIED:"), response
        result["unrelated_container"] = response
        result["passed"] = True
    finally:
        # Save recovery identity and inspection before stopping owned resources.
        result["created_containers"] = created
        result["created_network"] = network if network_created else None
        args.result.write_text(json.dumps(result, indent=2))
        args.result.chmod(0o600)
        for name in created:
            docker("stop", "--time", "2", name)
    print(json.dumps({"passed": result.get("passed", False), "containers_stopped": len(created),
                      "recovery_receipt": str(args.result)}))


if __name__ == "__main__":
    main()
