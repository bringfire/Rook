#include "stdafx.h"
#include "Serialization/RhinoSerializer.h"

#include <iostream>
#include <limits>

int main()
{
    for (const unsigned int serial : {1u, 55u, (std::numeric_limits<unsigned int>::max)()})
    {
        Rook::DocumentSnapshot snapshot;
        snapshot.documentSerialNumber = serial;
        snapshot.name = "Synthetic document";
        const auto result = Rook::Serializer::SerializeDocument(snapshot);
        if (!result.contains("documentSerialNumber")
            || !result["documentSerialNumber"].is_number_unsigned()
            || result["documentSerialNumber"].get<unsigned int>() != serial
            || result["name"] != snapshot.name)
        {
            std::cerr << "Document snapshot identity validation failed.\n";
            return 1;
        }
    }
    std::cout << "Document snapshot identity: 3 cases passed.\n";
    return 0;
}
