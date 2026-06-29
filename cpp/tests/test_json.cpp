// Unit tests for the minimal JSON parser/serializer.
#include "mu2edaq_discovery/Json.hpp"

#include <iostream>
#include <string>

using namespace mu2edaq_discovery;

static int failures = 0;
#define CHECK(cond)                                                      \
    do {                                                                 \
        if (!(cond)) {                                                   \
            std::cerr << "FAIL: " #cond " @line " << __LINE__ << "\n";   \
            ++failures;                                                  \
        }                                                                \
    } while (0)

int main() {
    // Parse a DISCOVER message with a nested filter.
    Json m = Json::parse(
        R"({"proto":"mu2edaq-discovery/1","type":"DISCOVER",)"
        R"("qid":"abc-123","filter":{"app":"trig*"}})");
    CHECK(m.is_object());
    CHECK(m.find("type") && m.find("type")->as_string() == "DISCOVER");
    CHECK(m.find("qid") && m.find("qid")->as_string() == "abc-123");
    const Json* f = m.find("filter");
    CHECK(f && f->is_object());
    CHECK(f->find("app") && f->find("app")->as_string() == "trig*");
    CHECK(m.find("missing") == nullptr);

    // Serialize: integers have no decimal point; strings are escaped.
    CHECK(Json(static_cast<std::int64_t>(5557)).dump() == "5557");
    JsonObject o;
    o.emplace_back("a", std::string("x\"y\nz"));
    o.emplace_back("p", static_cast<std::int64_t>(28999));
    std::string s = Json(std::move(o)).dump();
    Json back = Json::parse(s);
    CHECK(back.find("a") && back.find("a")->as_string() == std::string("x\"y\nz"));
    CHECK(back.find("p") != nullptr);

    // Round-trip an ANNOUNCE-like message.
    Json ann = Json::parse(
        R"({"proto":"mu2edaq-discovery/1","type":"ANNOUNCE","port":5557,)"
        R"("meta":{"zmq_port":"5556"}})");
    CHECK(ann.find("meta") && ann.find("meta")->is_object());
    CHECK(ann.find("meta")->find("zmq_port")->as_string() == "5556");

    // Malformed input must throw.
    bool threw = false;
    try { Json::parse("{bad json"); } catch (const JsonError&) { threw = true; }
    CHECK(threw);

    if (failures) {
        std::cerr << failures << " test(s) failed\n";
        return 1;
    }
    std::cout << "all JSON tests passed\n";
    return 0;
}
