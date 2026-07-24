// Loopback integration coverage for the C++ responder.
#include "mu2edaq_discovery/Json.hpp"
#include "mu2edaq_discovery/Responder.hpp"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <cstring>
#include <iostream>
#include <system_error>

using namespace mu2edaq_discovery;

namespace {

constexpr int SKIP_RETURN_CODE = 77;

int reserve_loopback_port() {
    int sock = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) return -1;
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::bind(sock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        ::close(sock);
        return -1;
    }
    socklen_t len = sizeof(addr);
    if (::getsockname(sock, reinterpret_cast<sockaddr*>(&addr), &len) != 0) {
        ::close(sock);
        return -1;
    }
    int port = ntohs(addr.sin_port);
    ::close(sock);
    return port;
}

int open_announcement_listener(int port) {
    int sock = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) return -1;
    int one = 1;
    ::setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
#ifdef SO_REUSEPORT
    ::setsockopt(sock, SOL_SOCKET, SO_REUSEPORT, &one, sizeof(one));
#endif
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(static_cast<std::uint16_t>(port));
    if (::bind(sock, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        ::close(sock);
        return -1;
    }
    ip_mreq membership{};
    membership.imr_multiaddr.s_addr = ::inet_addr(GROUP);
    membership.imr_interface.s_addr = htonl(INADDR_LOOPBACK);
    if (::setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP,
                     &membership, sizeof(membership)) != 0) {
        ::close(sock);
        return -1;
    }
    timeval timeout{};
    timeout.tv_sec = 2;
    ::setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    return sock;
}

bool send_packet(int sock, const std::string& text, int port) {
    sockaddr_in target{};
    target.sin_family = AF_INET;
    target.sin_port = htons(static_cast<std::uint16_t>(port));
    target.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    return ::sendto(sock, text.data(), text.size(), 0,
                    reinterpret_cast<sockaddr*>(&target), sizeof(target)) >= 0;
}

}  // namespace

int main() {
    int port = reserve_loopback_port();
    if (port < 0) {
        std::cout << "SKIP: UDP loopback sockets are unavailable\n";
        return SKIP_RETURN_CODE;
    }

    Responder::Options options;
    options.name = "C++ test responder";
    options.app = "test-app";
    options.port = 5557;
    options.host = "127.0.0.1";
    options.listen_port = port;
    options.bind_interface = "127.0.0.1";
    options.announce_interval = 1;
    Responder responder(options);
    try {
        responder.start();
    } catch (const std::system_error&) {
        std::cout << "SKIP: multicast sockets are unavailable\n";
        return SKIP_RETURN_CODE;
    }

    int client = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (client < 0) {
        responder.stop();
        std::cerr << "failed to create client socket\n";
        return 1;
    }
    sockaddr_in local{};
    local.sin_family = AF_INET;
    local.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::bind(client, reinterpret_cast<sockaddr*>(&local), sizeof(local)) != 0) {
        responder.stop();
        ::close(client);
        std::cerr << "failed to bind client socket\n";
        return 1;
    }
    timeval timeout{};
    timeout.tv_sec = 2;
    ::setsockopt(client, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

    const std::string rejected =
        R"({"proto":"mu2edaq-discovery/1","type":"DISCOVER","qid":"no-match","filter":{"app":"other"}})";
    const std::string query =
        R"({"proto":"mu2edaq-discovery/1","type":"DISCOVER","qid":"match","filter":{"app":"test-app"}})";
    // Sent while the responder's port is still exclusively its own: no other
    // socket is sharing that SO_REUSEPORT bind yet, so this unicast query is
    // guaranteed to land on the responder rather than racing a second
    // listener for the single delivery (see the announcements listener note
    // below).
    bool sent = send_packet(client, "-", port) &&
                send_packet(client, rejected, port) &&
                send_packet(client, query, port);
    if (!sent) {
        responder.stop();
        ::close(client);
        std::cerr << "failed to send test datagram\n";
        return 1;
    }

    char buffer[MAX_DATAGRAM];
    ssize_t received = ::recvfrom(client, buffer, sizeof(buffer), 0, nullptr, nullptr);
    if (received <= 0) {
        responder.stop();
        ::close(client);
        std::cerr << "responder did not answer the matching query\n";
        return 1;
    }

    try {
        Json reply = Json::parse(std::string(buffer, static_cast<std::size_t>(received)));
        const Json* type = reply.find("type");
        const Json* qid = reply.find("qid");
        const Json* id = reply.find("id");
        if (!type || type->as_string() != "ANNOUNCE" ||
            !qid || qid->as_string() != "match" ||
            !id || id->as_string() != responder.instance_id()) {
            responder.stop();
            ::close(client);
            std::cerr << "unexpected responder reply\n";
            return 1;
        }
    } catch (const std::exception& exc) {
        responder.stop();
        ::close(client);
        std::cerr << "invalid responder reply: " << exc.what() << "\n";
        return 1;
    }

    // Only bind a second socket to the responder's port now, to catch the
    // periodic multicast beacon: multicast fans out to every listener on a
    // shared port, but SO_REUSEPORT delivers unicast traffic to just one of
    // them, so opening this earlier could have stolen the query above
    // instead of the responder ever seeing it.
    int announcements = open_announcement_listener(port);
    char announcement_buffer[MAX_DATAGRAM];
    ssize_t announcement = announcements >= 0
        ? ::recvfrom(announcements, announcement_buffer, sizeof(announcement_buffer), 0,
                     nullptr, nullptr)
        : 0;
    responder.stop();
    ::close(client);
    if (announcements >= 0) ::close(announcements);
    if (announcements < 0) {
        std::cout << "SKIP: multicast announcement listener is unavailable\n";
        return 0;
    }
    if (announcement <= 0) {
        std::cerr << "responder did not multicast a periodic announcement\n";
        return 1;
    }
    try {
        Json announce = Json::parse(
            std::string(announcement_buffer, static_cast<std::size_t>(announcement)));
        const Json* type = announce.find("type");
        const Json* id = announce.find("id");
        if (!type || type->as_string() != "ANNOUNCE" ||
            !id || id->as_string() != responder.instance_id() ||
            announce.find("qid") != nullptr) {
            std::cerr << "unexpected multicast announcement\n";
            return 1;
        }
    } catch (const std::exception& exc) {
        std::cerr << "invalid multicast announcement: " << exc.what() << "\n";
        return 1;
    }
    return 0;
}
