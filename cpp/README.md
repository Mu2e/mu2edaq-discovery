# mu2edaq-discovery — C++ library

A C++17 port of the discovery **Responder**, so C++ DAQ applications (e.g.
`mu2edaq-trigger-scalers`) are discoverable by the Python `mu2edaq-discover`
client and the control room browser. Implements the same wire protocol as the
Python package (`mu2edaq-discovery/1`; see [`../doc/PROTOCOL.md`](../doc/PROTOCOL.md)).

- **Dependency-free**: C++17 stdlib + POSIX sockets. JSON is handled by a small
  internal parser/serializer (`Json.hpp`); no third-party libraries.
- **Platforms**: Linux and macOS. Windows (Winsock) is future work.

## Usage

```cpp
#include <mu2edaq_discovery/Responder.hpp>

mu2edaq_discovery::Responder::Options opt;
opt.name   = "Trigger Scalers";
opt.app    = "trigger-scalers";
opt.port   = 5557;
opt.scheme = "udp";
opt.meta   = {{"zmq_port", "5556"}};

mu2edaq_discovery::Responder responder(opt);
responder.start();   // joins the multicast group, answers DISCOVER queries
// ... run the application ...
responder.stop();    // on shutdown
```

Start the responder **after** the service socket is bound (never advertise a
port that is not accepting), and call `stop()` on shutdown.

## Building

```bash
cmake -S . -B build && cmake --build build
ctest --test-dir build        # JSON unit tests
./build/responder_demo --app trigger-scalers --port 5557 --seconds 30
```

## Consuming from another CMake project

Via `FetchContent` (builds only the library; tests/examples are skipped when
not the top-level project):

```cmake
include(FetchContent)
FetchContent_Declare(mu2edaq_discovery
    GIT_REPOSITORY https://github.com/Mu2e/mu2edaq-discovery.git
    GIT_TAG main
    SOURCE_SUBDIR cpp)
FetchContent_MakeAvailable(mu2edaq_discovery)

target_link_libraries(your_app PRIVATE mu2edaq_discovery::mu2edaq_discovery)
```

## Layout

- `include/mu2edaq_discovery/Responder.hpp` — public API
- `include/mu2edaq_discovery/Json.hpp` — minimal JSON (header-only)
- `src/Responder.cpp` — implementation (POSIX multicast sockets)
- `tests/test_json.cpp` — JSON unit tests (`ctest`)
- `examples/responder_demo.cpp` — standalone responder for manual testing
