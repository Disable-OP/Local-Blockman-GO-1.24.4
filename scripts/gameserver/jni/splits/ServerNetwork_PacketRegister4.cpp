#include "ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

using namespace BLOCKMAN;

void ServerNetwork::registerPacket4(AutoRegisterS2C& pRegister) {
	GSReg::reg4a(pRegister);
	GSReg::reg4b(pRegister);
	GSReg::reg4c(pRegister);
	GSReg::reg4d(pRegister);
}
