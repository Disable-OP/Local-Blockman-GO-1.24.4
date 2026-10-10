#include "Network/ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

using namespace BLOCKMAN;

namespace GSReg {
void reg1a(AutoRegisterS2C& r) {
	r.autoRegister<S2CPacketType::ProtocolBegin, S2CPacketType(25)>();
}
}
