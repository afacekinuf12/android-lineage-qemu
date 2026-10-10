#!/usr/bin/env python3
"""Run the real Linux HCI discovery code against controlled kernel responses."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

HARNESS = r"""
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static std::string scenario;
static int polls = 0, event_reads = 0, sockets = 0, control_closes = 0;
static int bound_index = -1;

extern "C" int __wrap_socket(int, int, int) { return 400 + sockets++; }
extern "C" int __wrap_bind(int fd, const sockaddr* addr, socklen_t) {
  if (fd == 401) bound_index = reinterpret_cast<const uint16_t*>(addr)[1];
  return 0;
}
extern "C" int __wrap_open(const char*, int, ...) {
  errno = ENOENT;
  return -1;  // No rfkill device; HCI discovery must still work.
}
extern "C" ssize_t __wrap_write(int, const void*, size_t n) { return n; }
extern "C" int __wrap_close(int fd) {
  if (fd == 400) ++control_closes;
  return 0;
}
extern "C" int __real_poll(pollfd*, nfds_t, int);
extern "C" int __wrap_poll(pollfd* fds, nfds_t, int timeout) {
  ++polls;
  if (scenario == "interrupted") {
    __real_poll(nullptr, 0, 100);
    errno = EINTR;
    return -1;
  }
  if (scenario == "unrelated") {
    __real_poll(nullptr, 0, 100);
    fds[0].revents = POLLIN;
    return 1;
  }
  if (event_reads == 0 || (scenario == "late" && event_reads == 1)) {
    fds[0].revents = POLLIN;
    return 1;
  }
  return __real_poll(nullptr, 0, timeout);
}
extern "C" ssize_t __wrap_read(int, void* output, size_t capacity) {
  ++event_reads;
  std::vector<uint16_t> words;
  if (scenario == "unrelated") {
    words = {0x0006, 0, 0};  // An unrelated management event.
  } else if (scenario == "late" && event_reads == 2) {
    words = {0x0004, 0, 0};  // Index added after an empty list.
  } else {
    // Packed Read Index List: header, opcode, status, count, indices.
    unsigned char packet[32] = {1, 0, 255, 255, 5, 0, 3, 0, 0, 0, 0};
    std::vector<uint16_t> indices;
    if (scenario == "exact") indices = {2, 0};
    if (scenario == "larger") indices = {2};
    packet[4] += indices.size() * 2;
    packet[9] = indices.size();
    if (!indices.empty()) memcpy(packet + 11, indices.data(), indices.size() * 2);
    const size_t length = 11 + indices.size() * 2;
    if (capacity < length) std::abort();
    memcpy(output, packet, length);
    return length;
  }
  memcpy(output, words.data(), words.size() * 2);
  return words.size() * 2;
}

#include "net_bluetooth_mgmt.h"
int main(int argc, char** argv) {
  if (argc != 2) return 2;
  scenario = argv[1];
  auto start = std::chrono::steady_clock::now();
  int fd;
  {
    aidl::android::hardware::bluetooth::impl::NetBluetoothMgmt management;
    fd = management.openHci();
  }
  const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now() - start).count();
  const bool found = scenario == "exact" || scenario == "larger" || scenario == "late";
  const int expected_index = scenario == "larger" ? 2 : 0;
  const bool accepted = control_closes == 1 &&
      (found ? fd == 401 && bound_index == expected_index
             : fd == -1 && elapsed >= 900 && elapsed < 1800);
  printf("{\"scenario\":\"%s\",\"fd\":%d,\"elapsed_ms\":%lld,"
         "\"polls\":%d,\"accepted\":%s}\n",
         scenario.c_str(), fd, static_cast<long long>(elapsed), polls,
         accepted ? "true" : "false");
  return accepted ? 0 : 1;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="hardware/interfaces checkout")
    args = parser.parse_args()
    source = args.source / "bluetooth/aidl/default"
    with tempfile.TemporaryDirectory(prefix="hci-wait-") as directory:
        root = Path(directory)
        (root / "log").mkdir()
        (root / "log/log.h").write_text(
            "#define ALOGI(...) ((void)0)\n#define ALOGE(...) ((void)0)\n")
        (root / "harness.cpp").write_text(HARNESS)
        binary = root / "hci-wait"
        command = ["c++", "-std=c++17", "-Wall", "-Wextra", "-I" + str(root),
                   "-I" + str(source), str(root / "harness.cpp"),
                   str(source / "net_bluetooth_mgmt.cpp"), "-o", str(binary)]
        command += ["-Wl,--wrap=" + name for name in
                    ("socket", "bind", "open", "write", "close", "poll", "read")]
        subprocess.run(command, check=True)
        results = []
        for scenario in ("exact", "larger", "late", "absent", "interrupted", "unrelated"):
            try:
                result = subprocess.run([str(binary), scenario], text=True,
                                        capture_output=True, timeout=3)
                data = json.loads(result.stdout)
                data["exit_code"] = result.returncode
            except subprocess.TimeoutExpired:
                data = {"scenario": scenario, "accepted": False, "timeout_seconds": 3}
            results.append(data)
        print(json.dumps(results, indent=2))
        return 0 if all(row["accepted"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
