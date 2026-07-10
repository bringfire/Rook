#pragma once

#include <cstdint>

namespace Rook {
namespace Handlers {
namespace Detail {

constexpr int ValidateGhBridgeRegistration(
    bool registrationIsNull,
    uint32_t version,
    uint32_t structSize,
    uint32_t expectedVersion,
    uint32_t requiredSize) noexcept
{
    if (registrationIsNull)
        return 1;
    if (version != expectedVersion)
        return 2;
    if (structSize < requiredSize)
        return 3;
    return 0;
}

} // namespace Detail
} // namespace Handlers
} // namespace Rook
