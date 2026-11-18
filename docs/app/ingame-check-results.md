# In-game check results

| Id | Game | Check | Result | Details | Covers | When |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | GFEE01 | Add chapter after chapter 1: the game plays it next | **PASS** | after chapter 2 retail goes to 3, the edited disc to 33 (the added chapter 33), whose map reaches its player phase | 1.0 §3 Add chapter ⭐ (POR) | 2026-11-18T14:40 |
| A1r | RFEE01 | Add chapter after 1-1: the game plays it next | **PASS** | after chapter 2 retail goes to 3, the edited disc to 56 (the added chapter 0501), whose map reaches its player phase | 1.0 §3 Add chapter ⭐ (RD) | 2026-11-18T14:43 |
| D1 | GFEE01 | Deployment: an enemy's tile and level | **PASS** | PID_BANDIT_MOU: the edited unit is at (10, 7) level 3 (edited destination (10, 7), level 1 -> 3); in retail at (9, 7) level 1 | 1.0 §3 Build/Deployment (POR) | 2026-11-18T14:49 |
| D1r | RFEE01 | Deployment: an enemy's tile and level | **PASS** | PID_GOON: the edited unit is at (14, 15) level 3 (edited destination (14, 15), level 1 -> 3); in retail at (12, 13) level 1 | 1.0 §3 Build/Deployment (RD) | 2026-11-18T14:51 |
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
| T1 | GFEE01 | Dialogue: an edited line is what the talk window shows | **PASS** | 31 messages in capitals; first talk window differs from retail on 4.8% of the lower screen, 0.0% of the upper (see shots) | 1.0 §3 Dialogue ⭐ (POR) | 2026-11-18T14:24 |
| T1r | RFEE01 | Dialogue: an edited line is what the talk window shows | **PASS** | 27 messages in capitals; first talk window differs from retail on 2.1% of the lower screen, 0.0% of the upper (see shots) | 1.0 §3 Dialogue ⭐ (RD) | 2026-11-18T14:32 |
