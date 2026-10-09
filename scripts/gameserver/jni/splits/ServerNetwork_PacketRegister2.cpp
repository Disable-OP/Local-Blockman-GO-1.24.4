#include "ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

using namespace BLOCKMAN;

void ServerNetwork::registerPacket2(AutoRegisterS2C& pRegister) {
	GSReg::reg2a(pRegister);
	GSReg::reg2b(pRegister);
	GSReg::reg2c(pRegister);
	GSReg::reg2d(pRegister);
}
