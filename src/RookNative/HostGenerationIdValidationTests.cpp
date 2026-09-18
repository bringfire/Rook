#include "Infrastructure/HostGenerationId.h"

#include <iostream>
#include <regex>
#include <string>

int main()
{
    const std::regex canonicalUuid(
        "^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$");
    const std::string first = Rook::Infrastructure::GenerateHostGenerationId();
    const std::string second = Rook::Infrastructure::GenerateHostGenerationId();

    if (!std::regex_match(first, canonicalUuid)
        || !std::regex_match(second, canonicalUuid))
    {
        std::cerr << "Host generation IDs must be canonical lowercase UUIDv4 values.\n";
        return 1;
    }
    if (first == second)
    {
        std::cerr << "Separate host lifetimes must receive different generation IDs.\n";
        return 1;
    }

    std::cout << "Host generation ID validation tests passed.\n";
    return 0;
}
