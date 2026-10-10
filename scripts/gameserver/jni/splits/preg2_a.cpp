#include "Network/ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

using namespace BLOCKMAN;

namespace GSReg {
void reg2a(AutoRegisterS2C& r) {
	r.autoRegister<S2CPacketType(100), S2CPacketType(125)>();
}
}
