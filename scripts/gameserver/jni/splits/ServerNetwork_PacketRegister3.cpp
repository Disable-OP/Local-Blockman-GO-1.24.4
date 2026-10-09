#include "ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

using namespace BLOCKMAN;

void ServerNetwork::registerPacket3(AutoRegisterS2C& pRegister) {
	GSReg::reg3a(pRegister);
	GSReg::reg3b(pRegister);
	GSReg::reg3c(pRegister);
	GSReg::reg3d(pRegister);
}
