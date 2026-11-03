"""Verified retail core-flag bodies; generated from local regional DOL audit.

Addresses and body SHA-256 values are strict preconditions, not search hints.
The boot hook is OSSetArenaLo, before OSInit clears the arena.
"""

PARTY = {'GFEE01': 2150827784, 'GFEP01': 2150868744, 'GFEJ01': 2150819720}
# Called by the read-only size preflight to match retail's faction-mask exception.
SKILL_TEST = {
    'GFEE01': (0x80105BC0, 156, '132cb5e9076b6bcad1f4013d561d7ca49dfc1167dcc44105eb47077df9d6e533'),
    'GFEP01': (0x80106398, 156, 'ad630021af6574dd578936e8c8e9620c6e2b4a3f22d16d16e796080aaf869a52'),
    'GFEJ01': (0x80103538, 156, 'a3c293d0f1f8671de63321b283c3f4e776f86f1e02e98b2b59cb06d45ffc7e9c'),
}
SITES = {
    'GFEE01': {
        'flag_register_local': (0x800BDDCC, 116, 'c66c4c9c141978b44cb4b27f8ae2c86b27135ea6f5ad4df333618fac0db2bdb7'),
        'flag_register_global': (0x800BDE40, 152, '6f8975178b4652865c791926e02ec870305bf6ff620222e19d2d92bb3d342760'),
        'flag_get': (0x800BDD08, 196, 'af40632845d6a65a73526bf87ed1e481e76a7a274ff2112e08888970b03b1645'),
        'flag_set': (0x800BDC68, 160, '6af7f884bc43ad46a9d4d43a8e8149e23650af9a4f8f829da38427a0d3520147'),
        'flag_clear': (0x800BDBC8, 160, '31aa54d953ca665a9b8a6413eca9fbead569dc8d8933eef081c67c4e50827080'),
        'flag_reset_locals': (0x800BDED8, 400, '907d962dba2204553da05ef734f8969f76339a5b2f0c96f46f09ce209c1288a9'),
        'flag_init': (0x800BE228, 204, 'deb9af00de1e2b64b2b212edf0b7057c34cee1d65f8539e3a8d7b4f87665cb7a'),
        'flag_clear_playthrough': (0x800BE068, 448, 'b3c005cb5116ac731816ada23bb7c457e6257c6ec09403d1a8b34daa09e223ed'),
        "arena_low": (0x80204DD8, 8, '51c7060daa4175c7f6a1f1df733f2801957c1757f2a0681a468958f9e193f8f3'),
    },
    'GFEP01': {
        'flag_register_local': (0x800BE3E0, 116, '4e0565c71425dae9598259608b196bdc0c8c5db9382875f1d54ee9a07934e2a7'),
        'flag_register_global': (0x800BE454, 152, '03c79bff40565875ee2153e9d1dc98dceead665cb7cfb6599399c90f1d15eb08'),
        'flag_get': (0x800BE31C, 196, '210c253392c98767e35f06e7246852ca7f415e64717774992dca5ec091004e27'),
        'flag_set': (0x800BE27C, 160, 'b5f77de5a87d0e90c1b0224afdf6e712920451b43d77fd81fa12243a51cd6be3'),
        'flag_clear': (0x800BE1DC, 160, '96c45f10505e6044db76ca44ac75adbdff57ed776f6351605928f40cf93eacc6'),
        'flag_reset_locals': (0x800BE4EC, 400, '907d962dba2204553da05ef734f8969f76339a5b2f0c96f46f09ce209c1288a9'),
        'flag_init': (0x800BE83C, 204, 'deb9af00de1e2b64b2b212edf0b7057c34cee1d65f8539e3a8d7b4f87665cb7a'),
        'flag_clear_playthrough': (0x800BE67C, 448, 'b3c005cb5116ac731816ada23bb7c457e6257c6ec09403d1a8b34daa09e223ed'),
        "arena_low": (0x8020D930, 8, '51c7060daa4175c7f6a1f1df733f2801957c1757f2a0681a468958f9e193f8f3'),
    },
    'GFEJ01': {
        'flag_register_local': (0x800BBE28, 116, 'd38722da5a9640a1bb2e8bd89f9aa41ba2a426a00f9587e6729289f1224d7e2a'),
        'flag_register_global': (0x800BBE9C, 152, 'b70a74187ccc2866083db1b97e937183dd4886fb05635de2fc554a5ef9963a2c'),
        'flag_get': (0x800BBD64, 196, '1fe81bb3f31cfa95ea1830374e8a2be10829f93a214ba18efbd7b64dccaa2bcd'),
        'flag_set': (0x800BBCC4, 160, '6c98713f2d9c883c1516b0456417bc4eb9cc56067ef86bf4e7cad38e4671c1ca'),
        'flag_clear': (0x800BBC24, 160, 'c2f1c7bceb5c1bc91986ecec1802fb69fe40725a6990a62c308de6cc15ae5701'),
        'flag_reset_locals': (0x800BBF34, 400, '907d962dba2204553da05ef734f8969f76339a5b2f0c96f46f09ce209c1288a9'),
        'flag_init': (0x800BC284, 204, 'deb9af00de1e2b64b2b212edf0b7057c34cee1d65f8539e3a8d7b4f87665cb7a'),
        'flag_clear_playthrough': (0x800BC0C4, 448, 'b3c005cb5116ac731816ada23bb7c457e6257c6ec09403d1a8b34daa09e223ed'),
        "arena_low": (0x801FF730, 8, '51c7060daa4175c7f6a1f1df733f2801957c1757f2a0681a468958f9e193f8f3'),
    },
}
