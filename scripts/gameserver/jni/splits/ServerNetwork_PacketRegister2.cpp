// Split TU replacement for ServerNetwork_PacketRegister200.cpp — the
// original instantiates a 100-packet template recursion in ONE function
// (giant TU); this shim delegates to the four quarter-range GSReg::reg2?
// definitions (preg2_?.cpp). ServerNetwork.cpp's init calls the
// registerPacket200 entry point, which the class already declares.
#include "Network/ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

void ServerNetwork::registerPacket200(AutoRegisterS2C& pRegister) {
	GSReg::reg2a(pRegister);
	GSReg::reg2b(pRegister);
	GSReg::reg2c(pRegister);
	GSReg::reg2d(pRegister);
}
