// Regression coverage for GitHub issue #4.
#include "mu2edaq_discovery/Json.hpp"

#include <array>
#include <exception>
#include <iostream>

using namespace mu2edaq_discovery;

int main() {
    const std::array<const char*, 7> valid = {
        "0", "-0", "1", "-1", "12.5", "1e3", "-1.2E-3",
    };
    for (const char* text : valid) {
        try {
            Json::parse(text);
        } catch (const std::exception& exc) {
            std::cerr << "rejected valid JSON number " << text << ": "
                      << exc.what() << "\n";
            return 1;
        }
    }

    const std::array<const char*, 8> invalid = {
        "-", "+", "1e", "1.", "01", "+1", "1e+", "1-2",
    };

    for (const char* text : invalid) {
        try {
            Json::parse(text);
            std::cerr << "accepted invalid JSON number: " << text << "\n";
            return 1;
        } catch (const JsonError&) {
            continue;
        } catch (const std::exception& exc) {
            std::cerr << "wrong exception for " << text << ": " << exc.what() << "\n";
            return 1;
        }
    }
    return 0;
}
