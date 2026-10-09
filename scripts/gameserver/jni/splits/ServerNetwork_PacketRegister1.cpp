#include "ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

using namespace BLOCKMAN;

void ServerNetwork::registerPacket1(AutoRegisterS2C& pRegister) {
	GSReg::reg1a(pRegister);
	GSReg::reg1b(pRegister);
	GSReg::reg1c(pRegister);
	GSReg::reg1d(pRegister);
}
