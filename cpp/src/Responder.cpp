#include "mu2edaq_discovery/Responder.hpp"

#include "mu2edaq_discovery/Json.hpp"

#include <arpa/inet.h>
#include <fnmatch.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstring>
#include <ctime>
#include <random>
#include <stdexcept>
#include <system_error>
#include <thread>

namespace mu2edaq_discovery {
namespace {

std::string make_uuid4() {
    std::random_device rd;
    std::mt19937_64 gen((static_cast<std::uint64_t>(rd()) << 32) ^ rd());
    std::uniform_int_distribution<std::uint64_t> dist;
    std::uint64_t hi = dist(gen), lo = dist(gen);
    // Set version (4) and variant (10xx) bits.
    hi = (hi & ~0xF000ULL) | 0x4000ULL;
    lo = (lo & ~(0xC000ULL << 48)) | (0x8000ULL << 48);
    char buf[37];
    std::snprintf(
        buf, sizeof(buf),
        "%08x-%04x-%04x-%04x-%012llx",
        static_cast<unsigned>(hi >> 32),
        static_cast<unsigned>((hi >> 16) & 0xFFFF),
        static_cast<unsigned>(hi & 0xFFFF),
        static_cast<unsigned>((lo >> 48) & 0xFFFF),
        static_cast<unsigned long long>(lo & 0xFFFFFFFFFFFFULL));
    return std::string(buf);
}

std::string iso8601_utc_now() {
    std::time_t t = std::time(nullptr);
    std::tm tm{};
    gmtime_r(&t, &tm);
    char buf[32];
    std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
    return std::string(buf);
}

std::string resolve_fqdn() {
    char host[256] = {0};
    if (gethostname(host, sizeof(host) - 1) != 0) return "localhost";
    struct addrinfo hints{};
    hints.ai_family = AF_UNSPEC;
    hints.ai_flags = AI_CANONNAME;
    struct addrinfo* res = nullptr;
    if (getaddrinfo(host, nullptr, &hints, &res) == 0 && res) {
        std::string fqdn = (res->ai_canonname && *res->ai_canonname)
                               ? res->ai_canonname : host;
        freeaddrinfo(res);
        return fqdn;
    }
    return host;
}

}  // namespace

Responder::Responder(Options opts) : opt_(std::move(opts)) {
    instance_id_ = make_uuid4();
    started_ = iso8601_utc_now();
    if (opt_.scheme.empty()) opt_.scheme = opt_.app;
    if (opt_.host.empty()) opt_.host = resolve_fqdn();
    if (opt_.bind_interface.empty()) opt_.bind_interface = "0.0.0.0";
}

Responder::~Responder() { stop(); }

void Responder::start() {
    sock_ = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (sock_ < 0)
        throw std::system_error(errno, std::generic_category(), "socket");

    int one = 1;
    ::setsockopt(sock_, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
#ifdef SO_REUSEPORT
    ::setsockopt(sock_, SOL_SOCKET, SO_REUSEPORT, &one, sizeof(one));
#endif

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(static_cast<std::uint16_t>(opt_.listen_port));
    if (::bind(sock_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) != 0) {
        int e = errno;
        ::close(sock_);
        sock_ = -1;
        throw std::system_error(e, std::generic_category(), "bind 28999");
    }

    ip_mreq mreq{};
    mreq.imr_multiaddr.s_addr = ::inet_addr(opt_.group.c_str());
    mreq.imr_interface.s_addr = ::inet_addr(opt_.bind_interface.c_str());
    if (::setsockopt(sock_, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq)) != 0) {
        int e = errno;
        ::close(sock_);
        sock_ = -1;
        throw std::system_error(e, std::generic_category(), "join multicast group");
    }

    // 0.5 s receive timeout so the loop can observe the stop flag.
    timeval tv{};
    tv.tv_sec = 0;
    tv.tv_usec = 500000;
    ::setsockopt(sock_, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    stop_flag_ = false;
    thread_ = std::thread(&Responder::run, this);
}

void Responder::stop() {
    if (!thread_.joinable()) return;
    stop_flag_ = true;
    // Unblock recvfrom() by poking our own listen port.
    int poke = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (poke >= 0) {
        sockaddr_in to{};
        to.sin_family = AF_INET;
        to.sin_port = htons(static_cast<std::uint16_t>(opt_.listen_port));
        to.sin_addr.s_addr = ::inet_addr("127.0.0.1");
        ::sendto(poke, "", 0, 0, reinterpret_cast<sockaddr*>(&to), sizeof(to));
        ::close(poke);
    }
    thread_.join();
    if (sock_ >= 0) { ::close(sock_); sock_ = -1; }
}

bool Responder::matches_filter(const Json& filter) const {
    if (!filter.is_object()) return true;
    auto check = [&](const char* key, const std::string& value) {
        const Json* pat = filter.find(key);
        if (!pat || !pat->is_string()) return true;
        return ::fnmatch(pat->as_string().c_str(), value.c_str(), 0) == 0;
    };
    return check("app", opt_.app) && check("name", opt_.name) &&
           check("host", opt_.host);
}

std::string Responder::build_announce(const std::string* qid) const {
    JsonObject obj;
    obj.emplace_back("proto", std::string(PROTO));
    obj.emplace_back("type", std::string("ANNOUNCE"));
    obj.emplace_back("id", instance_id_);
    obj.emplace_back("name", opt_.name);
    obj.emplace_back("app", opt_.app);
    obj.emplace_back("host", opt_.host);
    obj.emplace_back("port", static_cast<std::int64_t>(opt_.port));
    obj.emplace_back("scheme", opt_.scheme);
    obj.emplace_back("version", opt_.version);
    obj.emplace_back("pid", static_cast<std::int64_t>(::getpid()));
    obj.emplace_back("started", started_);
    if (qid) obj.emplace_back("qid", *qid);
    if (!opt_.meta.empty()) {
        JsonObject meta;
        for (const auto& kv : opt_.meta)
            meta.emplace_back(kv.first, kv.second);
        obj.emplace_back("meta", Json(std::move(meta)));
    }
    return Json(std::move(obj)).dump();
}

void Responder::run() {
    int send_sock = ::socket(AF_INET, SOCK_DGRAM, 0);
    unsigned char ttl = 4;
    if (send_sock >= 0)
        ::setsockopt(send_sock, IPPROTO_IP, IP_MULTICAST_TTL, &ttl, sizeof(ttl));

    std::mt19937 rng{std::random_device{}()};
    std::uniform_int_distribution<int> jitter_ms(0, 250);

    auto next_announce = std::chrono::steady_clock::now();

    while (!stop_flag_) {
        char buf[MAX_DATAGRAM + 1];
        sockaddr_in src{};
        socklen_t srclen = sizeof(src);
        ssize_t n = ::recvfrom(sock_, buf, MAX_DATAGRAM, 0,
                               reinterpret_cast<sockaddr*>(&src), &srclen);
        if (stop_flag_) break;

        if (n > 0) {
            try {
                Json msg = Json::parse(std::string(buf, static_cast<std::size_t>(n)));
                const Json* type = msg.find("type");
                const Json* proto = msg.find("proto");
                if (type && type->as_string() == "DISCOVER" &&
                    proto && proto->as_string() == PROTO) {
                    const Json* filter = msg.find("filter");
                    if (!filter || matches_filter(*filter)) {
                        const Json* qid = msg.find("qid");
                        std::string qid_str = qid ? qid->as_string() : std::string();
                        std::string reply =
                            build_announce(qid ? &qid_str : nullptr);
                        // Random jitter avoids reply storms.
                        std::this_thread::sleep_for(
                            std::chrono::milliseconds(jitter_ms(rng)));
                        if (send_sock >= 0)
                            ::sendto(send_sock, reply.data(), reply.size(), 0,
                                     reinterpret_cast<sockaddr*>(&src), srclen);
                    }
                }
            } catch (const JsonError&) {
                // Ignore malformed datagrams.
            }
        }

        // Optional periodic unsolicited announce.
        if (opt_.announce_interval > 0 && send_sock >= 0) {
            auto now = std::chrono::steady_clock::now();
            if (now >= next_announce) {
                std::string ann = build_announce(nullptr);
                sockaddr_in grp{};
                grp.sin_family = AF_INET;
                grp.sin_port = htons(static_cast<std::uint16_t>(opt_.listen_port));
                grp.sin_addr.s_addr = ::inet_addr(opt_.group.c_str());
                ::sendto(send_sock, ann.data(), ann.size(), 0,
                         reinterpret_cast<sockaddr*>(&grp), sizeof(grp));
                next_announce = now + std::chrono::seconds(opt_.announce_interval);
            }
        }
    }

    if (send_sock >= 0) ::close(send_sock);
}

}  // namespace mu2edaq_discovery
