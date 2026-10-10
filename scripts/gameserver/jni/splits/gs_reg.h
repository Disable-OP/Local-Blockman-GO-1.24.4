// Quarter-range registration split declarations (build-tree shim)
#pragma once
#include "Network/protocol/AutoRegisterPacketS2C.h"

// AutoRegisterS2C is a GLOBAL class (dev/logic/Src/Network/protocol/
// AutoRegisterPacketS2C.h; ServerNetwork.h forward-declares it at global
// scope) — the declarations below must match the definitions in preg*.cpp
// (reg1a..reg4d) and the calls in ServerNetwork_PacketRegister1..4.cpp.
namespace GSReg {
void reg1a(AutoRegisterS2C& r);
void reg1b(AutoRegisterS2C& r);
void reg1c(AutoRegisterS2C& r);
void reg1d(AutoRegisterS2C& r);
void reg2a(AutoRegisterS2C& r);
void reg2b(AutoRegisterS2C& r);
void reg2c(AutoRegisterS2C& r);
void reg2d(AutoRegisterS2C& r);
void reg3a(AutoRegisterS2C& r);
void reg3b(AutoRegisterS2C& r);
void reg3c(AutoRegisterS2C& r);
void reg3d(AutoRegisterS2C& r);
void reg4a(AutoRegisterS2C& r);
void reg4b(AutoRegisterS2C& r);
void reg4c(AutoRegisterS2C& r);
void reg4d(AutoRegisterS2C& r);
}
