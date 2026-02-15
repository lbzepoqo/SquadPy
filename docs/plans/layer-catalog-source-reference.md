# SquadLayerList `layers.json` Reference

Canonical upstream source (actively maintained):
- Human-friendly: `https://github.com/fantinodavide/SquadLayerList/blob/main/layers.json`
- Raw fetch URL (used by `LayerCatalogService`): `https://raw.githubusercontent.com/fantinodavide/SquadLayerList/main/layers.json`

Optional local snapshot for offline analysis:
- `tests/fixtures/samples/layers/layers.json`

## Top-Level Shape

`layers.json` is an object with:
- `DefaultGameSettings` (object)
- `Maps` (array)
- `Units` (object keyed by unit id, for example `USMC_LO_CombinedArms`)
- `Roles` (array)
- `MeleeWeapons` (array of weapon class-name strings)

## Important Nested Shapes

`Maps[*]` fields:
- Layer identity: `Name`, `rawName`, `levelName`, `fName`, `gamemode`
- Map metadata: `mapId`, `mapName`, `mapSize`, `biome`, `minimapTexture`
- Team/faction metadata: `factions`, `teamConfigs`, `separatedFactionsList`
- Objective geometry: `objectives`, `minimapCornersPosition`, `mapTextureCorners`

`Maps[*].factions[*]` fields:
- `factionId`, `defaultUnit`, `availableOnTeams`, `types`

`Maps[*].teamConfigs.team{1,2}` fields:
- `defaultFactionUnit`, `index`, `playerPercent`, `tickets`
- `allowedAlliances`, `allowedFactionUnitTypes`
- `isAttackingTeam`, `isDefendingTeam`, `disabledVeh`

`Units[unit_id]` fields:
- Identity: `unitObjectName`, `factionID`, `shortName`, `type`, `displayName`
- Gameplay metadata: `alliance`, `actions`, `intelOnEnemy`, `hasBuddyRally`
- Composition: `roles` (role ids), `vehicles` (spawn/catalog data), `characteristics`

`Units[unit_id].vehicles[*]` fields:
- `name`, `rowName`, `type`, `vehType`, `spawnerSize`
- `count`, `delay`, `respawnTime`, `tags`, `icon`
- `classNames`, `spawnCommands`

`Roles[*]` fields:
- `rowName`, `displayName`, `inventory`

`Roles[*].inventory[*]` fields:
- `className`, `objectPath`, `slotIndex`, `itemIndex`
- `minimum_count_on_spawn`, `max_allowed_in_inventory`
- `cannot_rearm`, `isMelee`

## Reuse Guidance

This source is broader than layer-name lookups and can support:
- Map and faction validation/suggestion APIs
- Rotation/voting safety checks (team configs, alliances, objective metadata)
- Vehicle/role analytics and policy checks
- Melee/weapon classification beyond plugin-local token lists
