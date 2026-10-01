I want to create a game with this sequence:

You join a lobby with an opposing player (via code). The first player creates the lobby and the second player on a different computer enters this code in. Then, when both click the start button they enter the game.

The game starts off with the prompt "Describe your first pokemon", and a chat box appears (make it a cool background with a pokemon theme in the back). When they submit their entry, they are presented with another set of prompt and submission button but with the text "Describe your second pokemon".

Then, they are placed into battle with ficticious pokemon with ficticious moves and stats that are dependent on how ferocious the prompt was and the typing (same types from pokemon) which would be most likely given prompt. Then, the two players battle it out. 

THAT WAS THE GAMEPLAY NOW THE IMPLMENTATION:

1. I want a react front-end, tailwind for styling, and framer motion for animations, and a FastAPI backend which keeps track of current games as well. Players have unique authenticated identities to enable refreshes, and the URL contains the game ID. On entry, the backend verifies the player's identity and membership in the game; otherwise redirect to the lobby. Use the synchronization, deadline, and cleanup rules below.

### Player synchronization and single-worker backend

Run one authoritative FastAPI worker process for the initial low-traffic deployment. Keep game state, request deduplication records, and per-game locks in that process. All HTTP requests, WebSocket connections, generation callbacks, and timer tasks use the same game state. A process restart ends in-memory games; clients must receive a game-unavailable response and return to the lobby after reconnecting.

- **Atomic changes and turn resolution:** Serialize all game mutations with a per-game lock, including action submissions, ready acknowledgments, replacements, generation completion, expiration, and cleanup. Under that lock, validate the current phase and turn, record accepted actions, and transition to resolving exactly once when both actions are present. Apply each turn's random rolls, actions, HP changes, statuses, and result exactly once before publishing its committed state. Do not hold the lock while awaiting OpenAI calls or network sends; generation completions must recheck that the game and preparation attempt are still current before committing outputs.
- **Duplicate and stale requests:** Every mutation includes a unique request ID, game ID, and expected phase/turn or preparation attempt ID. Authenticate the submitting player. Record accepted request IDs and their outcomes for the game's lifetime. Repeating the same request ID with the same payload returns the original acknowledgment without executing it again; reusing it with a different payload is rejected. A second distinct action for the same player and turn is rejected. Stale requests are rejected with the current state so the client can resynchronize.
- **Authoritative snapshots and reconnects:** Use WebSockets to push committed state updates. Maintain a monotonically increasing state version per game. On initial connection, refresh, reconnect, or an explicit resynchronization request, send a complete snapshot with phase, turn, teams, active pokemon, HP/status, readiness, deadlines, and result. Include only the recipient's own pending action and submission acknowledgment; never expose the opponent's pending action or private replacement choice. Both clients receive identical public state. Clients discard older state versions and never calculate authoritative damage or advance phases locally. Reconnects retain the player's accepted action and do not reset deadlines.
- **Generation readiness:** Keep both clients in preparation while any of the four pokemon still needs validated stats, types/moves, or a usable sprite. Once all four are complete, publish a ready snapshot and require both clients to acknowledge that preparation attempt and ready version. Start the first turn exactly once after both acknowledgments. If generation exhausts its retries, publish the failed preparation state to both clients and clear loading; late generation callbacks cannot start that failed match.
- **Backend deadlines:** At the start of each action-selection phase, set a shared backend deadline 60 seconds ahead. At the start of a forced-replacement phase, set a separate shared 60-second deadline for the players who need replacements. Broadcast the deadline and server time so clients can estimate the countdown despite clock differences. The backend alone decides expiration, using a monotonic clock for enforcement. Under the game lock, check expiration before accepting a submission and recheck phase/turn when a timer fires. If exactly one required player has not submitted by the deadline, that player forfeits; if both required players have not submitted, end with a draw. A player who has already submitted does not time out. Start a new action deadline only after all required replacements are accepted. Battle action timers do not run during generation or readiness acknowledgment.
- **Disconnects and cleanup:** A disconnected player may reconnect under the same authenticated identity before the existing deadline; disconnecting does not pause the game. Publish a terminal state for normal results, timeouts, generation failure, or abandonment. Track each client's explicit acknowledgment of the terminal state version; sending a message alone does not count as delivery. Retain the complete terminal snapshot for five minutes after termination so refreshed or disconnected clients can recover the result even if both have acknowledged it. After that window, delete game/pokemon objects and deduplication records under the game lock. Expired game URLs return a game-expired response and redirect to the lobby. Abandon nonterminal lobby/preparation games after five minutes without meaningful preparation progress or player readiness changes; heartbeats and reconnects do not extend this window. Outstanding generation work must not recreate a deleted game.

### Generation validation and recursive retries

Apply the same recursive validation-and-retry flow to every OpenAI generation step for every pokemon: base stats, types/moves, and sprite specifications. Validate each response against its strict Pydantic schema and the step's additional backend constraints before accepting it or starting dependent generation steps.

If a response fails validation, recursively retry that generation step up to three times after the initial attempt (at most four attempts total). Each retry includes the original generation context, the immediately previous output, and the specific schema or backend validation errors explaining why that output was rejected. Include the applicable schema, constraints, and supported choices so the model can correct its response. Keep the retry counter scoped to that generation step; recursion must stop after the third retry.

If the third retry still fails, mark generation as failed and explicitly tell the requesting client which generation step failed with a safe, user-readable error message. Notify both clients that match preparation failed, and do not start the battle with incomplete or invalid pokemon. Preserve already validated outputs, clear the loading state, and let the players return to the lobby. Do not silently substitute a preset or accept invalid output.

2. When the user submits a description of their pokemon, and it obviously sends a backend request. I want it to create the pokemon's stats first from the description(HP, Attack, Defense, Sp. Attack, Sp. Defense, and Speed) and 0 IV and 0 EV (keep it constrained to that of real pokemons' stat range (e.g. no pokemon will have greater stats than that of the strongest real pokemon)), via a strutured ChatGPT response conforming to a pydantic class with those ints.

3. Then, request a structured OpenAI response for the pokemon's one or two types and exactly four moves. Use this simplified Pydantic v2 schema. The only move mechanics are power, accuracy, sleep, paralysis, poison, and self-healing. Name and type identify the move; category selects the physical/special damage stats. There is no PP, critical hit system, move-specific priority, stat-changing effect, or other move mechanic.

```python
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field

Percent = Annotated[int, Field(ge=0, le=100)]
PokemonType = Literal[
    "normal", "fire", "water", "electric", "grass", "ice", "fighting",
    "poison", "ground", "flying", "psychic", "bug", "rock", "ghost",
    "dragon", "dark", "steel", "fairy",
]

class Move(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=80)]
    type: PokemonType
    category: Literal["physical", "special", "status"]
    power: Annotated[int, Field(ge=0, le=150)]  # 0 means no damage
    accuracy: Annotated[int, Field(ge=1, le=100)]
    sleep_chance: Percent  # Opponent; 0 disables this effect
    paralysis_chance: Percent  # Opponent; 0 disables this effect
    poison_chance: Percent  # Opponent; 0 disables this effect
    healing_percent: Annotated[int, Field(ge=0, le=50)]  # User's max HP

class MoveOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    types: Annotated[list[PokemonType], Field(min_length=1, max_length=2)]
    moves: Annotated[list[Move], Field(min_length=4, max_length=4)]
```

Require every field in the structured response, using zero for disabled effects. Backend validation rejects duplicate creature types and no-op moves. Status-category moves must have zero power; physical/special moves must have positive power. At most one status chance may be nonzero. Healing moves are self-only status moves: power and all status chances must be zero. Other moves target the opposing active pokemon and may combine damage with one status chance. Require at least one damaging move per pokemon. The power cap of 150 and healing cap of 50% are initial game balance limits, not claims about the real move catalog.

Use these explicit simplified status rules:

- A move first passes one accuracy roll (a uniform backend integer from 1 to 100 must be at most accuracy). A miss applies neither damage nor status nor healing. Self-healing uses the same accuracy rule.
- Damage resolves first, then the status chance is rolled independently if the target remains conscious. A pokemon may have only one status at a time; a new status cannot replace an existing one. For this simplified game, status eligibility does not depend on pokemon type. Damage type immunity prevents that move's status effect too; pure status moves ignore damage type effectiveness.
- Sleep prevents the next two attempted move actions, then clears. Decrement the sleep counter only when that pokemon attempts a move; switching does not decrement it. Switching remains allowed while asleep.
- Paralysis halves effective Speed (floor, minimum 1) and gives a 25% chance to lose a selected move action. It lasts for the battle. Switching is not blocked.
- Poison removes `max(1, floor(max_hp / 8))` HP from each poisoned, conscious active pokemon after both actions resolve. Apply both poison ticks together so simultaneous final knockouts produce a draw. Benched pokemon take no poison damage.
- Statuses persist through switching. Healing restores `floor(max_hp * healing_percent / 100)` HP, capped at max HP, and does not cure status or revive fainted pokemon.
- Moves can be used indefinitely. No PP, critical hits, burn, freeze, recoil, multi-hit attacks, weather, abilities, items, or custom mechanic handlers are implemented.

4. Create each pokemon's sprite with a schema-driven pixel-art renderer. The flow is: player description and generated pokemon types -> structured OpenAI sprite specification -> backend validation -> deterministic sprite renderer -> transparent 64 x 64 PNG -> frontend display. Send OpenAI the renderer's supported parts, poses, palette roles, and compatibility rules so its response describes something the renderer can actually build. Sprite choices are cosmetic and do not change battle stats or moves.

### Sprite specification and rendering

Use a modular part library for the first version: hand-authored pixel masks for heads, bodies, ears, tails, limbs, eyes, and optional wings/horns. Each part has a stable ID, attachment anchors, region masks, compatible body families, and a layer order. Start with a small coherent library and expand it over time. Larger heads and compact bodies give the creatures a chibi battle appearance.

Free-text descriptions such as "large rounded fox head" express the idea, but the renderer needs supported IDs such as `fox_large_round`. OpenAI selects these IDs and palette colors; it does not invent drawing instructions or executable code. Expose the part catalog as enums in a strict Pydantic v2 schema (`extra="forbid"` on every model), with every field required. Use `none` for absent optional parts. An example specification is:

```json
{
  "schema_version": "1",
  "canvas": [64, 64],
  "silhouette": {
    "body_family": "biped",
    "head": "fox_large_round",
    "body": "compact_torso",
    "ears": "paired_tall_triangles",
    "tail": "single_fluffy_zigzag",
    "limbs": "short_paws",
    "eyes": "alert",
    "wings": "none",
    "horns": "none"
  },
  "pose": "front_three_quarter",
  "palette_rules": {
    "max_colors": 5,
    "base": "#3878C8",
    "highlight": "#8CC8F0",
    "accent": "#F0C840",
    "shadow": "#204878",
    "outline": "#282830"
  },
  "regions": [
    { "part": "head", "color": "base" },
    { "part": "ear_tips", "color": "accent" },
    { "part": "tail_tip", "color": "accent" },
    { "part": "belly", "color": "highlight" }
  ]
}
```

The example IDs must exist in the catalog before they can be selected. Fix the canvas to `[64, 64]`, `max_colors` to 5, and the initial pose to `front_three_quarter`. Colors must be six-digit hex values; region colors must reference one of the five palette roles. Transparency does not count as a color. All eyes, outlines, highlights, and shadows use this same palette. Unspecified fill regions default to `base`; the renderer assigns outline and shading roles through authored masks. Region overrides change fill masks without overwriting outlines. Reject duplicate region entries, nonexistent regions, unsupported IDs, and incompatible part combinations.

Render on the backend using Pillow and integer pixel coordinates:

1. Load the selected part masks and attach them using the body's predefined anchors. Each supported pose has its own authored anchors and masks; arbitrary rotations are outside the initial scope.
2. Composite in a fixed order: rear tail/wings, rear limbs, torso, head, front limbs, ears/horns, then facial details. The catalog supplies any part-specific layer exceptions.
3. Apply the palette and named region overrides. Use authored shadow/highlight masks and one-pixel outline masks, with no anti-aliasing, gradients, or smoothing.
4. Keep the full creature inside a four-pixel transparent margin, with a shared ground baseline. Validate every supported combination against this layout; never silently crop parts that extend outside it.
5. Export the transparent PNG. Save the validated specification and renderer/catalog version with the pokemon, and cache the image by their content hash. The same specification and renderer version must produce the same pixels for both players and after refreshes.

Display the PNG at an integer scale, such as 256 x 256, using CSS `image-rendering: pixelated`. The first version uses one static sprite per pokemon, with no separate back sprite or animation frames.

Apply the shared generation validation and recursive retry policy above to sprite specifications, including catalog compatibility and layout validation. Keep already validated stats and moves. Show a generation/loading state until all four pokemon have usable sprites, or clear it and notify the clients if generation exhausts its three retries.

Possible extensions: add quadruped, serpentine, and floating body families with their own compatible part sets; add region patterns such as spots or stripes using pre-authored masks; add a few bounded size variants with matching anchors. A procedural renderer based on ellipses and polygons would be another option, but a modular pixel-mask library is the initial approach because it provides direct control over silhouettes and consistent pixel art.

### Required version-1 sprite catalog

Implement catalog version `1` and renderer version `1` with exactly one body family, `biped`, and one pose, `front_three_quarter`. The choices below are the complete initial enums. Additional families and poses are future work. All coordinates use a 64-by-64 canvas, origin at the top left, positive x to the right and positive y downward. Bounds below are inclusive. They are authoring envelopes, not solid rectangles: artists must author recognizable pixel silhouettes inside them.

| Slot | Supported IDs | Required authored appearance | Canvas envelope |
| --- | --- | --- | --- |
| body | `compact_torso` | Rounded chibi torso, narrow shoulders, broad lower belly | x=22..42, y=30..51 |
| head | `fox_large_round`, `cat_round`, `lizard_round` | Large fox muzzle, short cat muzzle, or rounded reptile muzzle; no built-in ears or horns | x=17..46, y=14..34 |
| ears | `none`, `paired_tall_triangles`, `paired_round_ears`, `paired_short_fins` | Two tall pointed ears, two round ears, or two small reptile fins | x=16..46, y=6..22 |
| tail | `none`, `single_fluffy_zigzag`, `single_cat_curve`, `single_lizard_taper` | Bushy angular tail, hooked cat tail, or tapering reptile tail behind torso | x=39..58, y=29..51 |
| limbs | `short_paws`, `short_claws` | Two short arms and two feet; claws use accent pixels | x=18..46, y=35..55 |
| eyes | `alert`, `gentle`, `fierce` | Two asymmetric eyes for the three-quarter view, with distinct expressions | x=24..40, y=22..27 |
| wings | `none`, `paired_small_bat`, `paired_small_feather` | Compact paired membrane wings or rounded feather wings behind torso | x=7..56, y=27..43 |
| horns | `none`, `single_forehead_horn`, `paired_small_horns` | Small central horn or two short horns above forehead | x=23..39, y=8..19 |

The ground baseline is y=55. Both foot masks touch that baseline. Every opaque pixel must lie within x=4..59 and y=4..59. No part may be scaled, rotated, mirrored at runtime, or shifted to repair an invalid combination. Paired features and near/far differences are authored together. No separate mouth slot is exposed: muzzle and mouth pixels belong to each head's masks.

#### Anchors and mask asset contract

Store assets in `backend/app/assets/sprites/v1/`, with `catalog.json` and a directory per part ID. The catalog records slot, family, pose, attachment anchor, local origin, permitted region names, layer fragments, and asset filenames. Load and validate the catalog on backend startup; missing or malformed assets fail startup with an actionable diagnostic.

The body defines these fixed canvas anchors. Part coordinates are local: translate each pixel by `destination_anchor - local_origin`. Author each asset with its local origin at `(0, 0)`; negative local coordinates are allowed in the catalog representation. Store mask files as tightly bounded grayscale PNGs, with a catalog `mask_offset` mapping their top-left pixel to local coordinates. PNG mask values are exactly 0 or 255.

| Attachment | Destination anchor | Purpose |
| --- | --- | --- |
| body | (32, 41) | Torso origin |
| head | (32, 31) | Neck/head attachment |
| ears | (32, 17) | Paired ear roots |
| tail | (40, 44) | Tail root behind right hip |
| limbs | (32, 44) | Shared origin for authored arms and feet |
| wings | (32, 34) | Paired shoulder roots |
| horns | (32, 16) | Forehead attachment |
| eyes | (32, 24) | Paired facial details |

All three head variants use the same ear, horn, and eye anchors. These attachments are inherited from the body assembly, so selecting a different head never changes coordinates. Authors must ensure that every permitted combination connects correctly at those anchors.

Each visible fragment supplies an opaque occupancy mask and disjoint palette-role masks: `outline`, `shadow`, `highlight`, `accent`, and default `base`. Their union equals occupancy. Masks never paint outside occupancy. Named fill-region masks are disjoint subsets of the base fill mask; they cannot include outline, shadow, highlight, or authored accent pixels. A region override replaces that region's base role with the requested palette role. This makes the rule about preserving outlines and authored shading executable.

Use the following optional region names; expose only the regions present in the selected assembly:

- `head`: broad head fill, excluding muzzle and facial detail.
- `muzzle`: fox/cat muzzle or lizard snout fill.
- `belly`: central torso fill.
- `ear_tips`: distal fill of either triangular or round ears; absent for `none` and fins.
- `tail_tip`: distal fill of any visible tail.
- `paws`: foot fill in `short_paws`; absent in `short_claws`.
- `wing_membrane`: bat-wing interior; absent in feather wings.
- `wing_feathers`: feather-wing interior; absent in bat wings.
- `horns`: horn fill; absent when horns are `none`.

An empty `regions` list is valid. Reject an override for an absent region, even if that name exists elsewhere in the catalog. Paired features share one region entry covering both sides. Eye fragments use outline for pupils, highlight for glints, and base/accent for other eye pixels; they introduce no sixth color. Palette roles may share hex values, yielding at most five distinct opaque colors.

Use integer layer indices, composited from low to high: rear tail=10, wings=20, far arm/feet=30, torso=40, head=50, near arm/feet=60, ears=70, horns=80, eyes=90. Limbs are one selectable asset with separate far and near fragments. Within a layer, use catalog fragment order, never filesystem iteration order. The initial catalog has no layer exceptions. Paint each fragment's complete role-colored occupancy over earlier fragments; transparent pixels leave earlier layers intact.

#### Compatibility matrix

All parts below support only `biped` + `front_three_quarter` + `compact_torso`. `none` is accepted only in ears, tail, wings, and horns. Head, body, limbs, and eyes are mandatory. Compatibility is determined by this table plus the cross-slot rules beneath it; unspecified combinations are rejected.

| Head | Allowed ears | Allowed tails | Allowed limbs | Allowed eyes | Allowed wings | Allowed horns |
| --- | --- | --- | --- | --- | --- | --- |
| `fox_large_round` | `none`, `paired_tall_triangles` | `none`, `single_fluffy_zigzag` | `short_paws` | All three | `none`, `paired_small_feather` | `none`, `single_forehead_horn` |
| `cat_round` | `none`, `paired_tall_triangles`, `paired_round_ears` | `none`, `single_cat_curve` | `short_paws` | All three | `none`, `paired_small_bat`, `paired_small_feather` | `none`, `single_forehead_horn` |
| `lizard_round` | `none`, `paired_short_fins` | `none`, `single_lizard_taper` | `short_claws` | All three | `none`, `paired_small_bat` | `none`, `single_forehead_horn`, `paired_small_horns` |

- Wings and a visible tail may coexist; author masks to preserve both silhouettes.
- A single forehead horn may coexist with any permitted ears. Paired horns require ears=`none`.
- Pokemon type does not impose extra compatibility restrictions. For example, a fire creature may have a cat silhouette; colors and parts express the description cosmetically.
- The example specification above is a required valid fixture.

Enumerate every legal assembly in an offline catalog verification command. For each, verify bounds, baseline, attachments, palette limits, and that each selected visible part retains at least one visible pixel after compositing. Produce a labeled contact sheet covering every legal silhouette combination using one expression, plus all head/expression combinations. Review it visually for disconnected parts, erased features, and readability at native resolution and 4x nearest-neighbor scale. Ship the hand-authored PNG masks, catalog, verification command, and reviewed contact sheets together. Runtime validation rechecks compatibility and final bounds; it must never crop an invalid assembly or quietly replace a part.

We generate both pokemon for each player and render the battle with attack buttons at the bottom (showing power and accuracy), a switch button, and health bars. Attacks are displayed as text and HP changes without attack animations.

### Simultaneous action selection and turn resolution

Both players secretly select one action each turn: use a move or switch to their other conscious pokemon. The backend waits for both actions, locks them, and then resolves the turn. Submitting first grants no advantage; neither player can see the opponent's selection before committing.

1. Voluntary switching has the highest priority and consumes that player's entire turn: a player who switches cannot attack that turn. Switches resolve before all moves, so the opponent's move targets the newly active pokemon. If both switch, resolve both switches before proceeding.
2. If both players selected moves, the pokemon with higher effective Speed attacks first. Effective Speed includes the paralysis reduction. Determine the order once after switching and before either move executes; effects applied during resolution do not reorder that turn. Break equal-Speed ties with a fair backend random choice each turn. All moves have equal inherent priority.
3. Before each selected move, check whether its original user is still conscious and whether sleep/paralysis prevents acting. A pokemon knocked out by the first move cannot execute its selected move, and its replacement does not inherit that action.
4. Resolve end-of-turn poison after both actions, then process fainting. If a player has a conscious reserve, pause for a forced replacement before the next turn; forced replacement does not consume the next turn. If both need replacements, collect them privately and reveal together. A player loses when both pokemon have fainted; if both teams have fainted, declare a draw.
5. Start the next turn only after all required replacements are complete. Display the winner/loser (or draw) and offer play again or exit to lobby when the battle ends.

The backend stores each player's team and active pokemon ID separately. Each pokemon has its ID, base/battle stats, moves, current/max HP, status, and remaining sleep actions. Each battle stores its phase, turn number, state version, private pending actions, resolution order, deadlines, readiness acknowledgments, request deduplication records, terminal acknowledgments, and result. Replace `player_id_turn` with these simultaneous pending actions. Validate and deduplicate submissions using the synchronization rules above. Clients receive the same resolved public state but never the opponent's pending action. Retain and clean up completed games using the terminal acknowledgment and five-minute reconnect window above.

### Battle HP and attack damage

Treat the six AI-generated stats as **base stats**, not final battle stats. For simplicity, every pokemon has **IV = 0 and EV = 0 for every stat**. Use **Level = 50 for all pokemon** as the default match setting, stored on the backend. Use neutral natures (no nature multiplier). These are explicit game simplifications.

Calculate maximum HP using the requested formula:

```text
MaxHP = floor(0.01 * (2 * BaseHP + IV + floor(0.25 * EV)) * Level)
        + Level + 10

With IV = 0 and EV = 0:
MaxHP = floor((2 * BaseHP * Level) / 100) + Level + 10
```

At Level 50, this simplifies to `MaxHP = BaseHP + 60`. For example, a pokemon with base HP 80 starts with 140 HP. Start each battle with `current_hp = max_hp`. Keep current HP separate from the immutable base stats and clamp it to the integer range `[0, max_hp]` after damage or healing. At zero HP, the pokemon faints and cannot attack; its player must send out their other pokemon if it is still conscious. A player loses when both pokemon have fainted. Switching does not reset HP. Do not introduce species-specific HP exceptions for these fictitious pokemon.

Calculate the other five battle stats with zero IVs/EVs and a neutral nature:

```text
BattleStat = floor((2 * BaseStat * Level) / 100) + 5
```

Use those calculated Attack/Defense stats in the requested attack damage formula. Paralysis modifies Speed only:

```text
RawDamage = (((2 * Level / 5 + 2) * Power * (A / D)) / 50 + 2)
            * Modifier
```

- `Level` is the attacker's level.
- `Power` is the move's power field. Power-zero moves skip the damage formula.
- For physical moves, `A` is the attacker's effective Attack and `D` is the defender's effective Defense.
- For special moves, `A` is the attacker's effective Special Attack and `D` is the defender's effective Special Defense.
- Clamp `A` and `D` to at least 1 before division; there are no move-specific stat overrides.
- `Modifier = STAB * TypeEffectiveness * Random`. There are no critical hits or other damage modifiers.
- `STAB` is 1.5 if the move's type matches either of the attacker's types, otherwise 1.0.
- `TypeEffectiveness` is the product of the move's matchup multiplier against each defender type, using the standard 18-type chart. A type immunity makes this multiplier zero.
- `Random` is a backend-generated uniform integer from 85 through 100 inclusive, divided by 100. Roll once for each successful damaging move.


For this game's simplified rounding rule, evaluate the expression above using ordinary division and floor once at the end. A successful non-immune damaging move deals `max(1, floor(RawDamage))`. A miss or immune damaging move deals zero damage. Power-zero status/healing moves never run the damage formula. This follows the supplied formula without exact generation-specific cartridge rounding.

The backend calculates and applies every action, status, HP change, and fainting event, then sends both players the same updated battle state. The frontend displays the result and updates health bars with current and maximum HP; it never decides damage. Use the simplified healing and poison rules defined above.

## Implementation milestones and completion criteria

Completion means a working two-computer game, with the evidence below committed or recorded. Scaffolding, mock-only generation, or a locally functioning battle screen alone does not satisfy completion. Tests use injected clocks, controlled randomness, and a fake generation provider where needed; at least one complete acceptance match also uses the configured live OpenAI provider. Keep credentials and raw provider errors out of client responses and committed evidence.

### Milestone 1: runnable foundation and explicit contracts

- A clean checkout can install dependencies and start React and the single-worker FastAPI backend using documented commands. Commit dependency manifests and lockfiles, an environment-variable example, and instructions for two computers to reach the same backend. API keys remain backend-only.
- Before implementation depends on them, document exact base-stat bounds and any total-stat cap, description length limits, session/authentication behavior, lobby code format/expiry, and provider models/timeouts. No validator may rely on the undefined phrase "strongest real pokemon".
- Define backend enums and legal transitions for lobby, description collection/preparation, ready acknowledgment, action selection, resolving, forced replacement, and terminal state. Specify which fields and mutations are legal in each phase.
- Define request, acknowledgment, error, and recipient-filtered snapshot schemas shared with the frontend. Document routes, WebSocket authentication, game-unavailable/game-expired responses, and stable machine-readable error codes.
- Define a stable preparation-ready version: acknowledgment mutations may advance the game state version, but both players acknowledge the same immutable readiness token for that preparation attempt. Document reconnect behavior at this boundary.
- Define play again as creating a fresh lobby/game with fresh descriptions and state; the terminal game's retained result remains accessible during its retention window. The player may share the new lobby code with the same opponent.
- Backend startup rejects a missing provider configuration or invalid sprite catalog clearly. The application has usable loading, connection-loss, validation-error, and terminal screens.

### Milestone 2: identities, lobby, and description collection

- Two separate browser profiles on separate computers can create/join a lobby by code. Both see membership and start readiness; preparation begins exactly once after both request start.
- A third identity cannot occupy a full lobby. Invalid/expired codes give actionable errors. Repeated joins by the existing member do not create duplicate players. A player's simultaneous tabs share one identity and cannot submit two actions.
- Refresh preserves membership through the chosen authenticated session. Unauthorized HTTP requests and WebSocket connections cannot read or mutate a game's private state. Guessing a game URL or passing another player's ID does not establish membership.
- Each player submits first and second descriptions in sequence. Inputs obey documented length/whitespace limits. Lock accepted descriptions for their preparation attempt; repeat requests return their recorded outcome, while conflicting resubmissions are rejected.
- Neither battle action deadlines nor replacement deadlines run during description collection, generation, or readiness acknowledgment. Preparation abandonment remains enforced.

### Milestone 3: validated generation and sprites

- Each of four creatures completes stats, types/moves, sprite specification, and PNG rendering. Dependent steps consume only validated upstream outputs. Names/IDs, base stats, calculated stats, moves, sprite metadata, HP, and status are stored coherently for each creature.
- Strict schemas reject extra fields, missing fields, wrong types, invalid enums, out-of-range numbers, duplicate types, invalid move combinations, no-op moves, and teams whose creatures lack a damaging move. Integer fields reject booleans and coerced numeric strings.
- Test initial success, success on each permitted retry, and exhaustion at four total attempts for each generation step. Verify retries contain original context, the immediate previous output, validation errors, and supported choices. A step's retries never rerun successfully completed upstream steps.
- Specify and test bounded behavior for provider timeout, transport failure, rate limiting, refusal, and unusable responses; these failures cannot leave clients loading forever. Distinguish provider failures from schema correction retries in implementation and diagnostics.
- Failure of any creature publishes one failed terminal preparation result to both clients, identifies the failed step safely, clears loading, and prevents readiness from starting battle. Late completions and canceled work cannot mutate failed/deleted games.
- Ship every catalog asset specified above. Catalog verification passes every legal assembly and rejects representative illegal pairings, absent regions, duplicate regions, bad hex values, invalid masks, and out-of-bounds assets.
- Rendered PNGs are RGBA, exactly 64x64, transparent outside occupancy, within the four-pixel margin, and contain at most five opaque RGB values. Repeated rendering yields identical decoded pixels; the cache key includes the complete specification and renderer/catalog versions.
- Review the contact sheets visually. The frontend displays sprites at integer scale with pixelated rendering. Both players and refreshed clients receive the same sprite for a creature.
- Both clients remain in preparation until all four usable sprites exist. Duplicate and concurrent ready acknowledgments start turn 1 exactly once. A stale attempt/readiness token cannot start a battle.

### Milestone 4: battle engine correctness

Use fixture creatures and scripted random values to establish exact expected events and final state for these cases:

- Level-50 HP and other battle stats follow the specified formulas. HP starts full and remains within bounds. Switching preserves HP and status; fainted creatures cannot move, heal, or be selected as replacements.
- Physical and special moves select the correct attack/defense stats. STAB, single/dual typing, immunity, random endpoints 85/100, final flooring, and minimum non-immune damage produce exact expected damage. Verify the complete 18x18 chart against a documented authoritative reference.
- Accuracy succeeds at the threshold and fails just above it, including self-healing. Misses apply no effects. Power-zero moves skip damage calculation; immune damaging moves apply neither damage nor their attached status.
- Voluntary switches resolve before moves and consume the switcher's action. A move hits the newly active opponent. Both switches succeed independently. Illegal switches and invalid move IDs are rejected without changing state.
- Higher effective Speed acts first; paralysis flooring/minimum applies. Controlled tie randomness can choose either player. Submission order grants no priority. Mid-turn status changes do not reorder moves.
- A creature knocked out before its move cannot execute it; a replacement never inherits the canceled action. A surviving creature may still execute its selected move after the opponent's failed or skipped action.
- Sleep blocks exactly the next two attempted moves, clearing after the second. Switching does not consume sleep actions. Paralysis blocks at the 25% threshold and permits the next value. Existing status cannot be replaced; pure status moves ignore type effectiveness as specified.
- Healing rounds down, respects its 50% cap and max HP, does not cure status, and cannot revive. Poison ticks only on conscious active creatures, uses the minimum of one HP, and applies to both sides together.
- Cover one active fainting with a reserve, both actives fainting with reserves, one team exhausted, and both teams exhausted by simultaneous poison. Verify forced replacements, win/loss, and draw outcomes respectively.
- Forced replacements are private until all required choices arrive. They do not consume the next turn. If only one player needs replacement, the other is not required to submit and is not subject to that replacement timeout.
- Resolve a turn once, produce an ordered battle event log explaining hits, misses, skipped actions, damage, status, healing, poison, and fainting, and publish the committed snapshot. Rendering that log never re-applies effects.

### Milestone 5: concurrency, deadlines, reconnects, and cleanup

- Concurrent final action submissions produce exactly one resolution and one set of random rolls. Concurrent ready acknowledgments and replacement submissions likewise produce one transition. Use controlled scheduling to exercise these races.
- Repeating a request ID with identical payload returns its original acknowledgment; a different payload with that ID fails. A second distinct action for the same player/turn fails. Deduplication cannot leak another player's acknowledgment. Stale phase/turn/attempt requests return the current recipient-filtered snapshot.
- Snapshots include required public state and only the recipient's private pending choice. Test HTTP errors, initial WebSocket snapshots, push events, reconnects, and resync responses for opponent-action/replacement leakage. Public resolved state is identical for both recipients.
- Frontend ignores older snapshots and accepts the latest state after reconnect/resync. Refresh during preparation, pending action selection, forced replacement, and terminal display preserves accepted submissions and deadlines.
- With a controllable monotonic clock, test just before the deadline, exactly at it, and just after it. Define expiration as `now >= deadline`. A delayed timer cannot permit a late submission because submission validation checks expiration itself.
- One missing required submission forfeits; two missing required submissions draw. A player who already submitted does not time out. When only one replacement is required and missing, that player forfeits. Old timer callbacks cannot expire a newer turn or preparation attempt.
- Disconnects do not pause/reset deadlines. A reconnect before expiration can act; reconnecting afterward recovers the terminal result. Timer enforcement remains correct if the host wall clock changes.
- No game lock is held across provider requests or network sends. A slow/disconnected socket cannot block the opponent's state updates or deadline handling; use bounded sends/queues and resynchronization on recovery.
- Terminal acknowledgment is explicit and version-checked. Results remain recoverable for five minutes even after both acknowledge. Cleanup occurs only after the retention interval and removes state, locks when safe, deduplication records, and per-game tasks without disrupting other games. Cached image retention follows a documented separate policy.
- Test five-minute lobby/preparation abandonment, progress near the boundary, and heartbeats/reconnects that do not extend the window. A hung provider request cannot prevent abandonment. Outstanding callbacks never recreate deleted state.
- Restart the backend during a match: reconnecting clients receive game-unavailable and return to the lobby. A URL for a cleaned-up game receives game-expired; define a bounded tombstone mechanism if needed to distinguish these responses without retaining complete game objects.

### Milestone 6: end-to-end acceptance and delivery

- Run a complete real-provider match from lobby creation through four generated creatures, both ready acknowledgments, move and switch actions, a forced replacement, and a terminal result. Use additional deterministic end-to-end fixtures for results that cannot reliably be induced in that live match.
- Run browser acceptance scenarios for invalid lobby code, unauthorized game URL, generation failure, refresh after submitting an action, connection loss/recovery, action timeout, replacement timeout, draw, expired game, play again, and exit to lobby.
- Battle UI shows both active sprites, names/types, current/max HP, statuses, reserves, turn, connection state, countdown, and event log. Four move buttons show category, type, power, accuracy, and enabled status/healing effects. Switch choices show whether reserves are conscious.
- Accepted submissions visibly enter a waiting state and cannot be edited. Opponent choices stay hidden. Forced replacement presents only legal options. Results distinguish win, loss, draw, forfeit, preparation failure, and abandonment with a clear next action.
- Check layout and keyboard operation at 360px, 768px, and 1280px viewport widths. Controls have accessible labels, visible focus, usable contrast, and text equivalents for HP/status; information does not rely on color alone. Respect reduced-motion preferences.
- Verify a documented initial low-traffic target of five concurrent two-player games on the selected host. Concurrent generation respects a configured provider-concurrency limit, and active battle mutations/timeout enforcement continue while other games generate sprites. Record host configuration and observed latency instead of claiming unmeasured capacity.
- Run the relevant backend unit/integration tests, frontend build/type checks, catalog verification, and browser acceptance suite from a clean checkout. Record commands, outcomes, and any manual visual/live-provider checks. No unresolved correctness failures, private-state leaks, or loading deadlocks remain.
- Expand README with setup, environment configuration, single-worker launch/deployment, session behavior, provider retry/timeouts, cache policy, testing commands, known in-memory restart limitation, and the acceptance evidence location.
- Deliver source, sprite masks/catalog, automated tests, contact sheets, and a concise acceptance report mapping every milestone to evidence. Any deferred optional feature is clearly identified; required functionality above cannot be marked complete by substituting a future-work note.
