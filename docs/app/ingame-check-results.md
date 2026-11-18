# In-game check results

| Id | Game | Check | Result | Details | Covers | When |
| --- | --- | --- | --- | --- | --- | --- |
| G1 | GFEE01 | Ike's Str bonus +2 is the record his unit uses | **PASS** | PID_IKE person: RAM +0x1e 2 -> 4 as edited | 1.0 §2 Characters ▸ Stats (POR) | 2026-11-18T10:10 |
| G1r | RFEE01 | Micaiah's Str bonus +2 is the record her unit uses | **PASS** | PID_MICAIAH person: RAM +0x23 2 -> 4 as edited | 1.0 §2 Characters ▸ Stats (RD) | 2026-11-18T13:57 |
| G2 | GFEE01 | Class movement +2 on Ike's class | **PASS** | PID_IKE job: RAM +0x3e 6 -> 8 as edited | 1.0 §2 Game Data ▸ Classes (POR) | 2026-11-18T13:25 |
| G2r | RFEE01 | Class movement +2 on Micaiah's class | **PASS** | PID_MICAIAH job: RAM +0xf5 5 -> 7 as edited | 1.0 §2 Game Data ▸ Classes (RD) | 2026-11-18T13:59 |
| G3 | GFEE01 | Item Might +5 (Ike's Practice Sword) | **PASS** | PID_IKE item IID_PRACTICESWORD: RAM +0x19 6 -> 11 as edited | 1.0 §2 Game Data ▸ Items (POR) | 2026-11-18T13:27 |
| G3r | RFEE01 | Iron Sword Might +5 (Edward's) | **PASS** | PID_EDDIE item IID_IRONSWORD: RAM +0x1c 6 -> 11 as edited | 1.0 §2 Game Data ▸ Items (RD) | 2026-11-18T14:00 |
| S1 | RFEE01 | Class, item, skill and support edits load and survive the game's save | **PASS** | in game: Light Sage, Elixir, SID_PARAGON; re-saved by the game with them and Edward support 50 (set 50) | SAVE-07; rdcheck R3 (points); 1.0 §5 Saves RD (unit item) | 2026-11-18T14:03 |
| S2 | RFEE01 | An Iron Sword added to the convoy is kept | **PASS** | Iron Swords in the re-saved convoy: retail 0, edited 1 | SAVE-05 convoy; 1.0 §5 Saves RD ⭐ convoy | 2026-11-18T14:05 |
| S6 | RFEE01 | Copy to new slot and Remove on the RD Units tab | **PASS** | re-saved: 2 Edward records (retail 1), 0 PID_NOYCE (removed); map: 2 Edward on the map | RD Units tab Copy/Remove | 2026-11-18T14:12 |
| S8 | RFEE01 | An event flag survives the game's own save | **PASS** | flag 127 after the game's save: edited True, retail False | rdcheck R2; SAVE-02 | 2026-11-18T14:08 |
