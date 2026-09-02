#pragma once

#include <array>
#include <iomanip>
#include <random>
#include <sstream>
#include <string>

namespace Rook::Infrastructure
{
    inline std::string GenerateHostGenerationId()
    {
        std::array<unsigned char, 16> bytes{};
        std::random_device random;
        for (auto& value : bytes)
            value = static_cast<unsigned char>(random());

        bytes[6] = static_cast<unsigned char>((bytes[6] & 0x0f) | 0x40);
        bytes[8] = static_cast<unsigned char>((bytes[8] & 0x3f) | 0x80);

        std::ostringstream stream;
        stream << std::hex << std::setfill('0');
        for (std::size_t index = 0; index < bytes.size(); ++index)
        {
            if (index == 4 || index == 6 || index == 8 || index == 10)
                stream << '-';
            stream << std::setw(2) << static_cast<int>(bytes[index]);
        }
        return stream.str();
    }
}
