---
id: "skill-aether"
title: "Aether"
description: "A combined activation that applies the game's Sol and Luna behaviors"
games: ["path-of-radiance"]
section: "systems"
article_type: "system-reference"
tags: ["Skills","Combat"]
aliases: ["tellius_archive.html#/skill-aether"]
status: "published"
last_reviewed: "2026-10-13"
sources: ["tellius-archive-research"]
cms_collection: "systems"
source_path: "systems/skill-aether.md"
---
# Aether

*A combined activation that applies the game's Sol and Luna behaviors*

Aether is a combined combat skill: its mechanical identity is the union of [Luna's](./skill-luna.md) defensive reduction and [Sol's](./skill-sol.md) healing from damage dealt.

## Mental model

Treat Aether as an orchestrator of two existing effects, not as an unrelated formula that happens to resemble them. Luna changes the defensive input used for damage; Sol receives the resulting final HP loss and restores that amount to the attacker, capped by maximum HP.

## Example

An attacker at 10/30 HP has 24 Attack against 16 Defense. The Luna portion reduces the defensive term to 8, allowing 16 damage. If that damage is actually dealt, the Sol portion restores 16 HP and leaves the attacker at 26/30. A miss or zero-damage result cannot supply healing.

## Definition and presentation

The internal ID is `SID_SUNMOON` at table index 76; the name literally joins the internal Sun and Moon names. Its restriction list names Ike's two Hero classes, `JID_HERO` and `JID_HERO_G`. The multiple-blow visual presentation belongs to [Combat & Battle Animation](./combat-animation.md); animation should not be mistaken for the authoritative effect calculation.

## Open questions

The exact activation-chance derivation and every animation-state transition are not fully mapped.
