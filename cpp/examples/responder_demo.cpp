// Minimal demo: run a mu2edaq-discovery Responder until SIGINT or --seconds.
// Useful for interop-testing against the Python `mu2edaq-discover` client.
#include "mu2edaq_discovery/Responder.hpp"

#include <chrono>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <thread>

using namespace mu2edaq_discovery;

static volatile std::sig_atomic_t g_stop = 0;

int main(int argc, char** argv) {
    Responder::Options o;
    o.name = "C++ Discovery Demo";
    o.app = "demo";
    o.port = 5557;
    o.scheme = "udp";
    int run_secs = 0;

    for (int i = 1; i < argc; ++i) {
        auto next = [&](const char* flag) {
            return std::strcmp(argv[i], flag) == 0 && i + 1 < argc;
        };
        if (next("--name")) o.name = argv[++i];
        else if (next("--app")) o.app = argv[++i];
        else if (next("--port")) o.port = std::atoi(argv[++i]);
        else if (next("--scheme")) o.scheme = argv[++i];
        else if (next("--seconds")) run_secs = std::atoi(argv[++i]);
    }

    std::signal(SIGINT, [](int) { g_stop = 1; });
    std::signal(SIGTERM, [](int) { g_stop = 1; });

    Responder r(std::move(o));
    r.start();
    std::cerr << "responder started; id=" << r.instance_id() << "\n";

    auto start = std::chrono::steady_clock::now();
    while (!g_stop) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        if (run_secs > 0 &&
            std::chrono::steady_clock::now() - start >= std::chrono::seconds(run_secs))
            break;
    }

    r.stop();
    std::cerr << "responder stopped\n";
    return 0;
}
