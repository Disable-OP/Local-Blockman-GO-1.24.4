#include "Network/ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

using namespace BLOCKMAN;

namespace GSReg {
void reg3b(AutoRegisterS2C& r) {
	r.autoRegister<S2CPacketType(225), S2CPacketType(250)>();
}
}
