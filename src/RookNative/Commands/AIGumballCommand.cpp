// AIGumballCommand.cpp
//
// Toggle command for the AI Gumball. Registered as "_AIGumball" so the
// existing toolbar button (Rook.rui) works with the C++ plugin.
//
// CRhinoCommand requires exactly one static instance per command class.
// The Rhino SDK discovers it automatically at plugin load time.

#include "stdafx.h"
#include "RookNativePlugin.h"
#include "Interactive/GumballManager.h"

class CAIGumballCommand : public CRhinoCommand
{
public:
    CAIGumballCommand()
        : CRhinoCommand(
            false,   // bTransparent
            false,   // bDoNotRepeat
            &RookNativePlugIn(),  // pPlugIn — binds to our plugin
            false    // bTestCommand
          )
    {}

    UUID CommandUUID() override
    {
        // {F3A1B2C4-D5E6-4F78-9A0B-1C2D3E4F5A6B}
        static const UUID uuid = {
            0xF3A1B2C4, 0xD5E6, 0x4F78,
            { 0x9A, 0x0B, 0x1C, 0x2D, 0x3E, 0x4F, 0x5A, 0x6B }
        };
        return uuid;
    }

    const wchar_t* EnglishCommandName() override { return L"AIGumball"; }

    CRhinoCommand::result RunCommand(const CRhinoCommandContext& context) override
    {
        auto& gm = Rook::CGumballManager::Instance();

        if (gm.IsEnabled())
        {
            gm.Deactivate();
            RhinoApp().Print(L"AI Gumball deactivated.\n");
        }
        else
        {
            // Activate with whatever is currently selected
            gm.Activate({});
            RhinoApp().Print(L"AI Gumball activated.\n");
        }

        return CRhinoCommand::success;
    }
};

// The one and only static instance — Rhino discovers this at load time
static CAIGumballCommand theAIGumballCommand;
