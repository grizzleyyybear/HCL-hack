"""Tiny TCP forwarder: exposes a WSL-only Ollama (127.0.0.1:11434) on 0.0.0.0:11435 so Windows/Docker can reach it.

Run inside WSL:  python3 scripts/wsl_ollama_forward.py   (no install, no config change; stops when WSL stops)
"""
import socket
import threading

LISTEN, TARGET = ("0.0.0.0", 11435), ("127.0.0.1", 11434)


# Copy bytes from one socket to the other until either side closes.
def pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while data := src.recv(65536):
            dst.sendall(data)
    except OSError:
        pass
    finally:
        src.close()
        dst.close()


# Accept connections forever and splice each one to the Ollama server.
def main() -> None:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(LISTEN)
    server.listen(64)
    while True:
        client, _ = server.accept()
        upstream = socket.create_connection(TARGET)
        threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
        threading.Thread(target=pipe, args=(upstream, client), daemon=True).start()


if __name__ == "__main__":
    main()
