// Minimal JSON value, parser, and serializer for the mu2edaq-discovery
// protocol. Dependency-free (C++17 stdlib only). Scoped to what the protocol
// needs: objects, arrays, strings, numbers, booleans, null. Not a
// general-purpose, spec-exhaustive JSON library, but correct for the small,
// flat messages exchanged on the wire.
#ifndef MU2EDAQ_DISCOVERY_JSON_HPP
#define MU2EDAQ_DISCOVERY_JSON_HPP

#include <cstdint>
#include <cmath>
#include <map>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <variant>
#include <vector>

namespace mu2edaq_discovery {

class Json;
using JsonArray = std::vector<Json>;
// Ordered object: preserves insertion order so serialized output is stable.
using JsonObject = std::vector<std::pair<std::string, Json>>;

class JsonError : public std::runtime_error {
public:
    explicit JsonError(const std::string& what) : std::runtime_error(what) {}
};

class Json {
public:
    using Value = std::variant<std::nullptr_t, bool, std::int64_t, double,
                               std::string, JsonArray, JsonObject>;

    Json() : v_(nullptr) {}
    Json(std::nullptr_t) : v_(nullptr) {}
    Json(bool b) : v_(b) {}
    Json(int i) : v_(static_cast<std::int64_t>(i)) {}
    Json(std::int64_t i) : v_(i) {}
    Json(double d) : v_(d) {}
    Json(const char* s) : v_(std::string(s)) {}
    Json(std::string s) : v_(std::move(s)) {}
    Json(JsonArray a) : v_(std::move(a)) {}
    Json(JsonObject o) : v_(std::move(o)) {}

    bool is_object() const { return std::holds_alternative<JsonObject>(v_); }
    bool is_string() const { return std::holds_alternative<std::string>(v_); }

    // Object lookup; returns nullptr if not an object or key absent.
    const Json* find(const std::string& key) const {
        if (!is_object()) return nullptr;
        for (const auto& kv : std::get<JsonObject>(v_))
            if (kv.first == key) return &kv.second;
        return nullptr;
    }

    // Best-effort string accessor ("" if not a string).
    std::string as_string() const {
        return is_string() ? std::get<std::string>(v_) : std::string();
    }

    // ---- serialize ----
    std::string dump() const {
        std::ostringstream os;
        write(os);
        return os.str();
    }

    // ---- parse ----
    static Json parse(const std::string& text) {
        Parser p(text);
        p.skip_ws();
        Json result = p.parse_value();
        p.skip_ws();
        if (!p.at_end())
            throw JsonError("trailing data after JSON value");
        return result;
    }

private:
    Value v_;

    void write(std::ostream& os) const {
        struct Visitor {
            std::ostream& os;
            void operator()(std::nullptr_t) const { os << "null"; }
            void operator()(bool b) const { os << (b ? "true" : "false"); }
            void operator()(std::int64_t i) const { os << i; }
            void operator()(double d) const { os << d; }
            void operator()(const std::string& s) const { write_string(os, s); }
            void operator()(const JsonArray& a) const {
                os << '[';
                for (std::size_t i = 0; i < a.size(); ++i) {
                    if (i) os << ',';
                    a[i].write(os);
                }
                os << ']';
            }
            void operator()(const JsonObject& o) const {
                os << '{';
                for (std::size_t i = 0; i < o.size(); ++i) {
                    if (i) os << ',';
                    write_string(os, o[i].first);
                    os << ':';
                    o[i].second.write(os);
                }
                os << '}';
            }
        };
        std::visit(Visitor{os}, v_);
    }

    static void write_string(std::ostream& os, const std::string& s) {
        os << '"';
        for (unsigned char c : s) {
            switch (c) {
                case '"':  os << "\\\""; break;
                case '\\': os << "\\\\"; break;
                case '\b': os << "\\b";  break;
                case '\f': os << "\\f";  break;
                case '\n': os << "\\n";  break;
                case '\r': os << "\\r";  break;
                case '\t': os << "\\t";  break;
                default:
                    if (c < 0x20) {
                        static const char* hex = "0123456789abcdef";
                        os << "\\u00" << hex[(c >> 4) & 0xF] << hex[c & 0xF];
                    } else {
                        os << static_cast<char>(c);
                    }
            }
        }
        os << '"';
    }

    // ---- recursive-descent parser ----
    class Parser {
    public:
        explicit Parser(const std::string& s) : s_(s), i_(0) {}

        bool at_end() const { return i_ >= s_.size(); }
        void skip_ws() {
            while (i_ < s_.size()) {
                char c = s_[i_];
                if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ++i_;
                else break;
            }
        }

        Json parse_value() {
            skip_ws();
            if (at_end()) throw JsonError("unexpected end of input");
            char c = s_[i_];
            switch (c) {
                case '{': return parse_object();
                case '[': return parse_array();
                case '"': return Json(parse_string());
                case 't': case 'f': return parse_bool();
                case 'n': return parse_null();
                default:  return parse_number();
            }
        }

    private:
        const std::string& s_;
        std::size_t i_;

        char expect(char c) {
            if (at_end() || s_[i_] != c)
                throw JsonError(std::string("expected '") + c + "'");
            return s_[i_++];
        }

        Json parse_object() {
            expect('{');
            JsonObject obj;
            skip_ws();
            if (!at_end() && s_[i_] == '}') { ++i_; return Json(std::move(obj)); }
            while (true) {
                skip_ws();
                std::string key = parse_string();
                skip_ws();
                expect(':');
                Json val = parse_value();
                obj.emplace_back(std::move(key), std::move(val));
                skip_ws();
                if (at_end()) throw JsonError("unterminated object");
                char c = s_[i_++];
                if (c == ',') continue;
                if (c == '}') break;
                throw JsonError("expected ',' or '}' in object");
            }
            return Json(std::move(obj));
        }

        Json parse_array() {
            expect('[');
            JsonArray arr;
            skip_ws();
            if (!at_end() && s_[i_] == ']') { ++i_; return Json(std::move(arr)); }
            while (true) {
                arr.push_back(parse_value());
                skip_ws();
                if (at_end()) throw JsonError("unterminated array");
                char c = s_[i_++];
                if (c == ',') continue;
                if (c == ']') break;
                throw JsonError("expected ',' or ']' in array");
            }
            return Json(std::move(arr));
        }

        std::string parse_string() {
            expect('"');
            std::string out;
            while (!at_end()) {
                char c = s_[i_++];
                if (c == '"') return out;
                if (c == '\\') {
                    if (at_end()) break;
                    char e = s_[i_++];
                    switch (e) {
                        case '"':  out += '"';  break;
                        case '\\': out += '\\'; break;
                        case '/':  out += '/';  break;
                        case 'b':  out += '\b'; break;
                        case 'f':  out += '\f'; break;
                        case 'n':  out += '\n'; break;
                        case 'r':  out += '\r'; break;
                        case 't':  out += '\t'; break;
                        case 'u': {
                            if (i_ + 4 > s_.size()) throw JsonError("bad \\u escape");
                            unsigned code = 0;
                            for (int k = 0; k < 4; ++k) {
                                char h = s_[i_++];
                                code <<= 4;
                                if (h >= '0' && h <= '9') code |= unsigned(h - '0');
                                else if (h >= 'a' && h <= 'f') code |= unsigned(h - 'a' + 10);
                                else if (h >= 'A' && h <= 'F') code |= unsigned(h - 'A' + 10);
                                else throw JsonError("bad hex in \\u escape");
                            }
                            append_utf8(out, code);
                            break;
                        }
                        default: throw JsonError("invalid escape");
                    }
                } else {
                    out += c;
                }
            }
            throw JsonError("unterminated string");
        }

        static void append_utf8(std::string& out, unsigned code) {
            if (code < 0x80) {
                out += static_cast<char>(code);
            } else if (code < 0x800) {
                out += static_cast<char>(0xC0 | (code >> 6));
                out += static_cast<char>(0x80 | (code & 0x3F));
            } else {
                out += static_cast<char>(0xE0 | (code >> 12));
                out += static_cast<char>(0x80 | ((code >> 6) & 0x3F));
                out += static_cast<char>(0x80 | (code & 0x3F));
            }
        }

        Json parse_bool() {
            if (s_.compare(i_, 4, "true") == 0) { i_ += 4; return Json(true); }
            if (s_.compare(i_, 5, "false") == 0) { i_ += 5; return Json(false); }
            throw JsonError("invalid literal");
        }

        Json parse_null() {
            if (s_.compare(i_, 4, "null") == 0) { i_ += 4; return Json(nullptr); }
            throw JsonError("invalid literal");
        }

        Json parse_number() {
            std::size_t start = i_;
            if (!at_end() && s_[i_] == '-') ++i_;
            if (at_end()) throw JsonError("invalid number");

            if (s_[i_] == '0') {
                ++i_;
                if (!at_end() && s_[i_] >= '0' && s_[i_] <= '9')
                    throw JsonError("invalid number");
            } else if (s_[i_] >= '1' && s_[i_] <= '9') {
                do { ++i_; }
                while (!at_end() && s_[i_] >= '0' && s_[i_] <= '9');
            } else {
                throw JsonError("invalid number");
            }

            bool is_double = false;
            if (!at_end() && s_[i_] == '.') {
                is_double = true;
                ++i_;
                if (at_end() || s_[i_] < '0' || s_[i_] > '9')
                    throw JsonError("invalid number");
                do { ++i_; }
                while (!at_end() && s_[i_] >= '0' && s_[i_] <= '9');
            }
            if (!at_end() && (s_[i_] == 'e' || s_[i_] == 'E')) {
                is_double = true;
                ++i_;
                if (!at_end() && (s_[i_] == '+' || s_[i_] == '-')) ++i_;
                if (at_end() || s_[i_] < '0' || s_[i_] > '9')
                    throw JsonError("invalid number");
                do { ++i_; }
                while (!at_end() && s_[i_] >= '0' && s_[i_] <= '9');
            }

            std::string tok = s_.substr(start, i_ - start);
            try {
                if (!is_double) {
                    try {
                        return Json(static_cast<std::int64_t>(std::stoll(tok)));
                    } catch (const std::out_of_range&) {
                        // Preserve valid JSON integers that exceed int64 as doubles.
                    }
                }
                double value = std::stod(tok);
                if (!std::isfinite(value)) throw JsonError("number out of range");
                return Json(value);
            } catch (const std::exception&) {
                throw JsonError("invalid number");
            }
        }
    };
};

}  // namespace mu2edaq_discovery

#endif  // MU2EDAQ_DISCOVERY_JSON_HPP
