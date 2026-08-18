#!/usr/bin/env python3
"""Minimal HTTP/HTTPS CONNECT forward proxy for bridging the build host to the
Mac's internet. Only handles CONNECT (HTTPS tunneling) plus plain GET/POST
forwarding, which is all git/repo over https need. Bind to localhost only; it is
exposed to the build host through an ssh -R reverse tunnel, not the network."""
import select
import socket
import sys
import threading

LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899


def pipe(a, b):
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 60)
            if not r:
                break
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.close()
            except OSError:
                pass


def handle(client):
    try:
        client.settimeout(30)
        req = b""
        while b"\r\n\r\n" not in req:
            chunk = client.recv(4096)
            if not chunk:
                client.close()
                return
            req += chunk
        line = req.split(b"\r\n", 1)[0].decode("latin1")
        method, target, _ = line.split(" ", 2)
        if method.upper() == "CONNECT":
            host, port = target.split(":")
            upstream = socket.create_connection((host, int(port)), timeout=30)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            client.settimeout(None)
            upstream.settimeout(None)
            pipe(client, upstream)
        else:
            # Plain HTTP forward: target is an absolute URL.
            from urllib.parse import urlsplit

            parts = urlsplit(target)
            host = parts.hostname
            port = parts.port or 80
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            upstream = socket.create_connection((host, port), timeout=30)
            rebuilt = req.replace(target.encode(), path.encode(), 1)
            upstream.sendall(rebuilt)
            pipe(client, upstream)
    except Exception:
        try:
            client.close()
        except OSError:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(128)
    print(f"proxy listening on {LISTEN_HOST}:{LISTEN_PORT}", flush=True)
    while True:
        client, _ = srv.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
