#!/usr/bin/env python3
"""Exercise the unchanged initialize method with controlled transport results."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

PRELUDE = r"""
#include <array>
#include <cstdlib>
#include <cstdio>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <vector>
#define ALOGI(...) ((void)0)
#define ALOGE(...) ((void)0)
#define LOG_ALWAYS_FATAL(...) std::abort()
namespace hal {
enum class Status { SUCCESS, ALREADY_INITIALIZED, UNABLE_TO_OPEN_INTERFACE };
struct IBluetoothHciCallbacks {
  std::vector<Status> results;
  void initializationComplete(Status status) { results.push_back(status); }
  void aclDataReceived(const std::vector<uint8_t>&) {}
  void scoDataReceived(const std::vector<uint8_t>&) {}
  void hciEventReceived(const std::vector<uint8_t>&) {}
  void isoDataReceived(const std::vector<uint8_t>&) {}
};
}
using hal::Status;
static int transport_fd = -1, watchers = 0, protocols = 0;
struct NetBluetoothMgmt { int openHci() { return transport_fd; } };
struct H4Protocol {
  template<class... T> H4Protocol(T&&...) { ++protocols; }
  void OnDataReady() {}
};
struct Watcher {
  template<class T> void WatchFdForNonBlockingReads(int, T) { ++watchers; }
  void StopWatchingFileDescriptors() {}
};
std::optional<std::string> GetSystemProperty(const std::string&) { return {}; }
bool starts_with(const std::string& s, const std::string& p) {
  return s.compare(0, p.size(), p) == 0;
}
struct BluetoothHci {
  enum class HalState { READY, INITIALIZING, ONE_CLIENT };
  HalState mState = HalState::READY;
  std::mutex mStateMutex;
  std::shared_ptr<hal::IBluetoothHciCallbacks> mCb;
  std::unique_ptr<NetBluetoothMgmt> management_;
  std::shared_ptr<H4Protocol> mH4;
  Watcher mFdWatcher;
  int mFd = -1;
  void initialize(const std::shared_ptr<hal::IBluetoothHciCallbacks>& cb);
  void close() { mState = HalState::READY; }
  void reset() {}
  int getFdFromDevPath() { return -1; }
};
"""

MAIN = r"""
int main(int argc, char** argv) {
  if (argc != 2) return 2;
  std::string scenario = argv[1];
  BluetoothHci hci;
  transport_fd = scenario == "unavailable" ? -1 : 23;
  if (scenario == "already_initialized")
    hci.mState = BluetoothHci::HalState::ONE_CLIENT;
  auto cb = std::make_shared<hal::IBluetoothHciCallbacks>();
  hci.initialize(cb);
  const bool success = scenario == "success";
  const auto expected = success ? Status::SUCCESS :
      scenario == "unavailable" ? Status::UNABLE_TO_OPEN_INTERFACE :
      Status::ALREADY_INITIALIZED;
  const bool accepted = cb->results.size() == 1 && cb->results[0] == expected &&
      watchers == (success ? 1 : 0) && protocols == (success ? 1 : 0);
  printf("{\"scenario\":\"%s\",\"callbacks\":%zu,\"watchers\":%d,"
         "\"protocols\":%d,\"accepted\":%s}\n", scenario.c_str(),
         cb->results.size(), watchers, protocols, accepted ? "true" : "false");
  return accepted ? 0 : 1;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="hardware/interfaces checkout")
    args = parser.parse_args()
    source = (args.source / "bluetooth/aidl/default/BluetoothHci.cpp").read_text()
    start = source.index("void BluetoothHci::initialize(")
    end = source.index("\nvoid BluetoothHci::close()", start)
    method = source[start:end]
    with tempfile.TemporaryDirectory(prefix="hci-init-") as directory:
        root = Path(directory)
        (root / "harness.cpp").write_text(PRELUDE + method + MAIN)
        binary = root / "hci-init"
        subprocess.run(["c++", "-std=c++17", "-pthread", str(root / "harness.cpp"),
                        "-o", str(binary)], check=True)
        results = []
        for scenario in ("success", "unavailable", "already_initialized"):
            result = subprocess.run([str(binary), scenario], text=True,
                                    capture_output=True, timeout=3)
            data = json.loads(result.stdout)
            data["exit_code"] = result.returncode
            results.append(data)
        print(json.dumps(results, indent=2))
        return 0 if all(row["accepted"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
