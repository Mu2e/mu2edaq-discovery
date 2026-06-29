// C++ port of the mu2edaq-discovery Responder.
//
// Answers DISCOVER queries on the UDP multicast group with a unicast ANNOUNCE,
// and (optionally) multicasts periodic unsolicited ANNOUNCE messages. Wire
// protocol matches mu2edaq-discovery/1 (see doc/PROTOCOL.md), so a C++ service
// using this library is discoverable by the Python `mu2edaq-discover` client
// and the control room browser.
//
// Dependency-free: C++17 stdlib + POSIX sockets (Linux/macOS). Windows is not
// yet supported (a Winsock backend is future work).
#ifndef MU2EDAQ_DISCOVERY_RESPONDER_HPP
#define MU2EDAQ_DISCOVERY_RESPONDER_HPP

#include <atomic>
#include <map>
#include <string>
#include <thread>

namespace mu2edaq_discovery {

constexpr const char* PROTO = "mu2edaq-discovery/1";
constexpr const char* GROUP = "239.255.42.99";
constexpr int PORT = 28999;
constexpr int MAX_DATAGRAM = 1400;

class Responder {
public:
    struct Options {
        std::string name;                         // human-readable label
        std::string app;                          // short app id
        int port = 0;                             // primary service port
        std::string scheme;                       // default: app
        std::string version = "0";
        std::map<std::string, std::string> meta;  // free-form extra detail
        std::string host;                         // default: resolved FQDN
        std::string group = GROUP;
        int listen_port = PORT;
        int announce_interval = 0;                 // seconds; 0 = solicited-only
        std::string bind_interface = "0.0.0.0";
    };

    explicit Responder(Options opts);
    ~Responder();
    Responder(const Responder&) = delete;
    Responder& operator=(const Responder&) = delete;

    // Open the socket, join the multicast group, and start the responder
    // thread. Throws std::runtime_error on socket setup failure.
    void start();

    // Signal the thread to exit and join it. Safe to call more than once.
    void stop();

    const std::string& instance_id() const { return instance_id_; }

private:
    void run();
    bool matches_filter(const class Json& filter) const;
    std::string build_announce(const std::string* qid) const;

    Options opt_;
    std::string instance_id_;
    std::string started_;
    std::thread thread_;
    std::atomic<bool> stop_flag_{false};
    int sock_ = -1;
};

}  // namespace mu2edaq_discovery

#endif  // MU2EDAQ_DISCOVERY_RESPONDER_HPP
