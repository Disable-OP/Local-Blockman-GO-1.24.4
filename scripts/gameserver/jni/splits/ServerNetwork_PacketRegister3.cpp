// Split TU replacement for ServerNetwork_PacketRegister300.cpp — the
// original instantiates a 100-packet template recursion in ONE function
// (giant TU); this shim delegates to the four quarter-range GSReg::reg3?
// definitions (preg3_?.cpp). ServerNetwork.cpp's init calls the
// registerPacket300 entry point, which the class already declares.
#include "Network/ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

void ServerNetwork::registerPacket300(AutoRegisterS2C& pRegister) {
	GSReg::reg3a(pRegister);
	GSReg::reg3b(pRegister);
	GSReg::reg3c(pRegister);
	GSReg::reg3d(pRegister);
}
