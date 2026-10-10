// Split TU replacement for ServerNetwork_PacketRegister400.cpp — the
// original instantiates a 100-packet template recursion in ONE function
// (giant TU); this shim delegates to the four quarter-range GSReg::reg4?
// definitions (preg4_?.cpp). ServerNetwork.cpp's init calls the
// registerPacket400 entry point, which the class already declares.
#include "Network/ServerNetwork.h"
#include "Network/protocol/AutoRegisterPacketS2C.h"
#include "Network/protocol/S2CPackets.h"
#include "gs_reg.h"

void ServerNetwork::registerPacket400(AutoRegisterS2C& pRegister) {
	GSReg::reg4a(pRegister);
	GSReg::reg4b(pRegister);
	GSReg::reg4c(pRegister);
	GSReg::reg4d(pRegister);
}
