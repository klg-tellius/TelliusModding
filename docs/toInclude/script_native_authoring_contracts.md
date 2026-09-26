# Script authoring contracts

The author-facing function reference now has named positional arguments and behavioral descriptions for all 497 catalogued names. It omits native addresses, registration tables, evidence labels, call-site dumps and research methodology. Shared helpers retain their loading requirement and actual return behavior.

Core corrections for the archive: unit arguments are numeric handles, not memory addresses; Check distinguishes base-conversation eligibility from playback; NetuzoSet takes outcome/effect flags rather than damage; UnitGet/UnitSet have different supported field sets; SetSight ignores its second argument in US FE9; SetFog changes rendering fog, not cursor position or gameplay visibility. CreateNoticeLFrame takes screen geometry, not colors. RectMove centers at (304,240), and rectangle scaling setters use percentages while RectGet returns a truncated scale factor. Document per-call frame/millisecond units instead of assuming a single convention.

Use research/SCRIPT_NATIVE_CONTRACTS.md for the detailed contracts and remaining limits. The app tutorial preserves .fe9s syntax and executable examples; do not copy compiler/editor mechanics into the game-only archive.
