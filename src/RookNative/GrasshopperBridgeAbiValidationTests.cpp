#include "Handlers/GrasshopperBridgeAbiValidation.h"

#include <cstdint>
#include <iostream>

namespace {

bool ExpectEqual(const char* scenario, int actual, int expected)
{
    if (actual == expected)
        return true;

    std::cerr << scenario << ": expected " << expected << ", got " << actual << '\n';
    return false;
}

} // namespace

int main()
{
    using Rook::Handlers::Detail::ValidateGhBridgeRegistration;

    constexpr uint32_t expectedVersion = 18;
    constexpr uint32_t requiredSize = 512;
    bool passed = true;
    passed &= ExpectEqual(
        "null registration",
        ValidateGhBridgeRegistration(true, 0, 0, expectedVersion, requiredSize),
        1);
    passed &= ExpectEqual(
        "older ABI",
        ValidateGhBridgeRegistration(false, 17, requiredSize, expectedVersion, requiredSize),
        2);
    passed &= ExpectEqual(
        "newer ABI",
        ValidateGhBridgeRegistration(false, 19, requiredSize, expectedVersion, requiredSize),
        2);
    passed &= ExpectEqual(
        "undersized registration",
        ValidateGhBridgeRegistration(false, expectedVersion, requiredSize - 1, expectedVersion, requiredSize),
        3);
    passed &= ExpectEqual(
        "exact registration",
        ValidateGhBridgeRegistration(false, expectedVersion, requiredSize, expectedVersion, requiredSize),
        0);
    passed &= ExpectEqual(
        "larger registration",
        ValidateGhBridgeRegistration(false, expectedVersion, requiredSize + 1, expectedVersion, requiredSize),
        0);

    if (!passed)
        return 1;

    std::cout << "Grasshopper bridge ABI validation tests passed.\n";
    return 0;
}
