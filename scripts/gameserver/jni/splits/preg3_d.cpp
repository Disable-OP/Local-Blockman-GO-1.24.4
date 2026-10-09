#include "ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

using namespace BLOCKMAN;

namespace GSReg {
void reg3d(AutoRegisterS2C& r) {
	r.autoRegister<S2CPacketType(275), S2CPacketType(300)>();
}
}
