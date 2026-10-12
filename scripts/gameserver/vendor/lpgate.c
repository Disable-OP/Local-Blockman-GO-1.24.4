#include <stdio.h>
#include "lua.h"
#include "lauxlib.h"
int main(int argc, char **argv) {
    if (argc < 2) return 2;
    lua_State *L = luaL_newstate();
    int rc = luaL_loadfile(L, argv[1]);
    if (rc != 0) { fprintf(stderr, "PARSE FAIL %s: %s\n", argv[1], lua_tostring(L, -1)); lua_close(L); return 1; }
    lua_close(L);
    return 0;
}
