---
id: "event-flags"
title: "Event Flags"
description: "The 96 named on/off switches that let chapter scripts remember what has already happened"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Scripting","Save Data"]
aliases: ["tellius_archive.html#/event-flags"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/event-flags.md"
---
# Event Flags

*The 96 named on/off switches that let chapter scripts remember what has already happened*

Chapter scripts have no general memory. When a script needs to know whether something has already happened — a village visited, a boss conversation seen, a character dead — it uses a **flag**: one named bit in a single table of 96 that the whole game shares.

!!! info "The whole table"
    Each of the 96 slots holds a name, a hash of that name, and one bit. A script registers a name to claim a slot, then turns its bit on (`set`), off (`clr`) or reads it (`get`). A name that was never registered is simply ignored: `set` does nothing and `get` answers 0.

## Two kinds of flag

  Flags differ only in how they are registered. <span class="confidence confidence--confirmed">confirmed</span>

<div class="table-wrap">
<table><thead><tr><th></th><th>Global flags</th><th>Chapter flags</th></tr></thead><tbody>
    <tr><td>Registered by</td><td><code>global(name)</code>, once at power-on</td><td><code>regist(name)</code> in the chapter's <code>Startup</code></td></tr>
    <tr><td>Slots</td><td>From slot 0 upward</td><td>From slot 95 downward</td></tr>
    <tr><td>Lifetime</td><td>The whole playthrough</td><td>One chapter</td></tr>
    <tr><td>Examples</td><td>A character died, a recruitment condition, the Black Knight defeated</td><td>A chest opened, a boss conversation seen, a reinforcement wave triggered</td></tr>
  </tbody></table>
</div>

  At power-on the engine registers eight flags of its own — `gf_canceled`, `gf_gameover`, `gf_complete`, three reserved ones, and `gf_triA`/`gf_triB`, which make each triangle-attack message appear only once — and then `startup.cmb` registers 22 story flags, filling slots 0–29.

## What happens at a chapter start

1. Starting from slot 95, the engine erases names until it reaches an empty slot, removing the previous chapter's flags.
2. Every slot without a name has its bit cleared. Global flags keep their names and therefore their values.
3. `gf_gameover` and `gf_complete` are turned off.
4. The new chapter's `Startup` registers its flags from slot 95 downward, always in the same order. Vanilla chapters register up to 58.

  Because the erasure stops at the first empty slot, the table must never be completely full. If it were, the next chapter start would also erase every global flag.

## Flags as one-time switches for events

  Talk, battle and base-conversation events carry a label, and that label is a flag name. The engine skips the event while that flag is on; the event's own script turns it on after the conversation. A boss's pre-battle line therefore plays once even though the trigger condition is met at every encounter. <span class="confidence confidence--confirmed">confirmed</span>

## How flags are saved

  Every save block stores the 96 bits as 12 bytes inside its [BMST](../formats/save-format.md) chunk — bit *i* is byte *i* ÷ 8, bit *i* mod 8, least significant first. The names are not saved. Loading a save runs the same registrations again, so each slot gets back its name, and then restores the bits. A flag's identity in a save is therefore its slot number, which depends only on the order in which the scripts register their names. <span class="confidence confidence--confirmed">confirmed</span>

## The story flags

<div class="table-wrap">
<table><thead><tr><th>Slot</th><th>Name</th><th>Meaning</th></tr></thead><tbody>
    <tr><td>8–13</td><td><code>G_シノン死亡</code> … <code>G_リュシオン死亡</code></td><td>Shinon, Gatrie, Marcia, Lethe, Mordecai, Reyson died</td></tr>
    <tr><td>14</td><td><code>G_ＭＡＰ１２で漆黒とアイク戦闘</code></td><td>Ike fought the Black Knight on map 12</td></tr>
    <tr><td>15, 16</td><td><code>G_ヤナフ死亡</code>, <code>G_ウルキ死亡</code></td><td>Janaff, Ulki died</td></tr>
    <tr><td>17</td><td><code>G_情報３兄弟</code></td><td>Info conversation about three brothers</td></tr>
    <tr><td>18, 19, 22</td><td><code>G_リザーブド</code></td><td>Reserved, never used</td></tr>
    <tr><td>20</td><td><code>G_Map20の情報会話３</code></td><td>Map 20, third info conversation</td></tr>
    <tr><td>21</td><td><code>G_ティバーン死亡</code></td><td>Tibarn died</td></tr>
    <tr><td>23</td><td><code>G_Ｍａｐ４マーシャ会話</code></td><td>Map 4 Marcia conversation</td></tr>
    <tr><td>24</td><td><code>G_フォルカ仲間</code></td><td>Volke recruited</td></tr>
    <tr><td>25</td><td><code>G_Map31ネサラ使用</code></td><td>Naesala used on map 31</td></tr>
    <tr><td>26</td><td><code>G_ジル仲間条件</code></td><td>Jill's recruitment condition met</td></tr>
    <tr><td>27</td><td><code>G_漆黒の騎士倒した</code></td><td>Black Knight defeated</td></tr>
    <tr><td>28</td><td><code>G_クリミア忠臣イベント</code></td><td>Crimean retainers event</td></tr>
    <tr><td>29</td><td><code>DBG_最初からやってる</code></td><td>Development marker, "playing from the start"</td></tr>
  </tbody></table>
</div>

## Room for more

  With 30 global flags, a chapter has 65 slots of its own before the table is full. The busiest chapter uses 58, so every vanilla chapter leaves at least 7 slots free. New chapter flags belong at the end of `Startup` so that older saves keep their slot meanings, and new story flags at the end of `startup.cmb`'s global list, each one taking a slot away from every chapter. <span class="confidence confidence--strong">strong</span>
