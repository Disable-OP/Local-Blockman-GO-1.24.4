// Split TU replacement for ServerNetwork_PacketRegister100.cpp — the
// original instantiates a 100-packet template recursion in ONE function
// (giant TU); this shim delegates to the four quarter-range GSReg::reg1?
// definitions (preg1_?.cpp). ServerNetwork.cpp's init calls the
// registerPacket100 entry point, which the class already declares.
#include "Network/ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

void ServerNetwork::registerPacket100(AutoRegisterS2C& pRegister) {
	GSReg::reg1a(pRegister);
	GSReg::reg1b(pRegister);
	GSReg::reg1c(pRegister);
	GSReg::reg1d(pRegister);
}
