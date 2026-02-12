# HelloWorldApplet APDU Reference

## AIDs

| Identifier  | AID (hex)                | Length |
|-------------|--------------------------|--------|
| Package     | `D000CAFE0001`       | 6 bytes |
| Applet      | `D000CAFE000101`     | 7 bytes |

## SELECT

Before sending any command, select the applet:

```
>> 00 A4 04 00 07 D000CAFE000101
<< 9000
```

The applet returns no data on SELECT (just SW 9000).

## Commands

### INS 01 — Hello

Returns "Hello World!" and increments the persistent counter.

| Field | Value   | Notes |
|-------|---------|-------|
| CLA   | `00`    |       |
| INS   | `01`    |       |
| P1    | `00`    |       |
| P2    | `00`    |       |
| Lc    | absent  | No command data |
| Le    | `0C`    | 12 bytes expected |

**Response** (success):

```
48 65 6C 6C 6F 20 57 6F 72 6C 64 21  9000
H  e  l  l  o     W  o  r  l  d  !
```

12 data bytes followed by SW 9000.

**Side effect**: The persistent counter increments by 1.

### INS 02 — Get Counter

Returns the current value of the persistent counter as a 2-byte big-endian unsigned short.

| Field | Value   | Notes |
|-------|---------|-------|
| CLA   | `00`    |       |
| INS   | `02`    |       |
| P1    | `00`    |       |
| P2    | `00`    |       |
| Lc    | absent  | No command data |
| Le    | `02`    | 2 bytes expected |

**Response** (success):

```
00 05  9000       (example: counter = 5)
```

2 data bytes (big-endian short) followed by SW 9000.

The counter starts at 0 after installation and increments by 1 with each INS 01 command. Range: 0x0000 to 0x7FFF (Java `short`, 0–32767). Overflow wraps to -32768 (0x8000).

### Unsupported INS

Any INS other than 01 or 02 returns:

```
6D00
```

SW 6D00 = INS not supported (ISO 7816-4).

## Status Words

| SW     | Meaning |
|--------|---------|
| `9000` | Success |
| `6D00` | INS not supported |

## Example Session

```
# Select applet
>> 00 A4 04 00 07 D000CAFE000101
<< 9000

# Check counter (should be 0 after fresh install)
>> 00 02 00 00 02
<< 0000 9000

# Say hello (counter becomes 1)
>> 00 01 00 00 0C
<< 48656C6C6F20576F726C6421 9000

# Say hello again (counter becomes 2)
>> 00 01 00 00 0C
<< 48656C6C6F20576F726C6421 9000

# Read counter
>> 00 02 00 00 02
<< 0002 9000
```

---

# GP Amendment H — ELF Upgrade Support

## Overview

GlobalPlatform Card Specification v2.3.1 Amendment H defines a mechanism for upgrading the Executable Load File (ELF) on a card — replacing applet code without deleting applet instances. Instance data is migrated through an explicit save/restore protocol defined by the `org.globalplatform.upgrade` API (package AID `A00000015107`).

## How This Applet Implements Amendment H

The applet implements the `OnUpgradeListener` interface from `org.globalplatform.upgrade`. This requires four callback methods that the card's OPEN invokes during the upgrade lifecycle:

### `onSave()` — Saving Phase

Called on the **old** applet instance. Serializes instance data into an `Element` container:

```java
public Element onSave() {
    return UpgradeManager.createElement(
            Element.TYPE_SIMPLE, Element.SIZE_SHORT, (short) 0)
        .write(counter);
}
```

Creates an Element with 2 bytes of primitive storage (one `short`), zero object references. Writes the `counter` value. The OPEN holds this Element across the deletion/reload boundary.

### `onCleanup()` — Cleanup Sequence

Called on the **old** applet instance after saving. For cleanup operations needed before deletion (e.g., releasing shared interface objects). Must not modify migrated data. Must be idempotent (safe to re-run after power loss). `Applet.uninstall()` is **not** called during upgrades.

```java
public void onCleanup() {
    // Nothing to clean up.
}
```

### `onRestore(Element root)` — Restore Phase

Called on the **new** applet instance (after `install()`) with the Element from `onSave()`. Deserializes the saved data back into the new instance's fields:

```java
public void onRestore(Element root) {
    root.initRead();        // Reset read pointers (required for power-loss recovery)
    counter = root.readShort();
}
```

`initRead()` must always be called before any `readXXX()` — if the Restore Phase is resumed after a power loss, read pointers need to be reset.

### `onConsolidate()` — Consolidation

Called on the **new** applet instance after **all** instances in the package have been restored. Used for cross-instance initialization (e.g., obtaining SIO references to sibling applets). Not needed here.

```java
public void onConsolidate() {
    // No cross-instance dependencies.
}
```

## Element Serialization Format

The `counter` field is serialized as a single `Element`:

| Field | Type | Size | Element method |
|-------|------|------|----------------|
| `counter` | `short` | 2 bytes | `write(short)` / `readShort()` |

Total: `primitiveDataSize = Element.SIZE_SHORT` (2 bytes), `objectCount = 0`.

Primitive data and object references are stored **separately** by the Element for security — object references cannot be forged from primitive data. Since this applet has no object fields to migrate, `objectCount` is 0.

## Upgrade Lifecycle (Card-Side)

The full sequence managed by the card's OPEN:

1. **Initiation** — host sends `MANAGE ELF UPGRADE [start]` to the Security Domain
2. **Saving Phase** — OPEN calls `onSave()` on each old instance implementing `OnUpgradeListener`. If any throws, the **entire upgrade aborts**.
3. **Cleanup Sequence** — OPEN calls `onCleanup()` on each old instance. Exceptions silently ignored.
4. **Deletion** — old package and instances are deleted. Saved Elements are preserved.
5. **Loading** — new ELF is loaded via standard LOAD commands.
6. **Restore Phase** — OPEN creates new instances (calls `install()`), then calls `onRestore(root)` on each. If any throws, restore is aborted and recovery begins.
7. **Consolidation** — OPEN calls `onConsolidate()` on each new instance. Exceptions silently ignored.
8. **Completion** — saved Elements are garbage collected.

## Build Dependencies

The applet links against:

| Package | AID | Export source |
|---------|-----|---------------|
| `org.globalplatform.upgrade` v1.1 | `A00000015107` | `globalplatform-exports/org.globalplatform.upgrade-1.1/` |

The card must have the `org.globalplatform.upgrade` package available on-card. Card support for Amendment H is indicated by Tag `89` value `01` in the Card Recognition Data.

The `org.globalplatform.upgrade` package is **separate** from the base `org.globalplatform` package (`A00000015100`) — they have independent AIDs and versioning.

## Requirements for Amendment H Compatibility

1. **Implements `OnUpgradeListener`** — the applet class implements all four callbacks
2. **Stable AIDs** — package AID (`D000CAFE0001`) and applet AID (`D000CAFE000101`) remain the same across versions
3. **Version field** — `build.xml` sets `version="1.0"`, incremented for each upgrade (e.g., `1.1`, `2.0`)
4. **Idempotent callbacks** — `onCleanup()` and `onRestore()` can safely re-run after power loss
5. **No transactions in callbacks** — the OPEN aborts any open transaction on return from any callback
6. **Card support** — the card must support Amendment H and have the upgrade API package on-card

## Upgrade Rules

When modifying the applet for a new version:

- **Safe changes**: modifying method bodies, adding new methods, adding new static fields, adding new INS handlers
- **Extending saved state**: add new fields to the Element in `onSave()` — use `UpgradeManager.getPreviousPackageVersion()` in `onRestore()` to handle version differences
- **Removing fields**: stop writing them in `onSave()`, but handle their absence in `onRestore()` if upgrading from an older version
- **Key constraint**: `onRestore()` must be able to read exactly what `onSave()` wrote — same types, same order

## Test Procedure

### 1. Build and install v1.0

```bash
JAVA_HOME=/usr/lib/jvm/java-11-openjdk ant clean build
gp --install HelloWorldApplet.cap
```

### 2. Accumulate state

```
>> 00 A4 04 00 07 D000CAFE000101    # Select
<< 9000
>> 00 01 00 00 0C                   # Hello (counter=1)
<< 48656C6C6F20576F726C6421 9000
>> 00 01 00 00 0C                   # Hello (counter=2)
<< 48656C6C6F20576F726C6421 9000
>> 00 01 00 00 0C                   # Hello (counter=3)
<< 48656C6C6F20576F726C6421 9000
>> 00 02 00 00 02                   # Get counter
<< 0003 9000                        # Confirmed: 3
```

### 3. Build v1.1

Bump the version in `build.xml` to `version="1.1"`, make any code change, rebuild:

```bash
JAVA_HOME=/usr/lib/jvm/java-11-openjdk ant clean build
```

### 4. Perform ELF upgrade

```bash
gp --upgrade HelloWorldApplet.cap
```

The card's OPEN will call `onSave()` on the old instance, delete the old ELF, load the new ELF, call `install()` then `onRestore()` on the new instance.

### 5. Verify state preservation

```
>> 00 A4 04 00 07 D000CAFE000101    # Select (same AID)
<< 9000
>> 00 02 00 00 02                   # Get counter
<< 0003 9000                        # Still 3 — migrated via onSave/onRestore
>> 00 01 00 00 0C                   # Hello (counter=4)
<< 48656C6C6F20576F726C6421 9000
>> 00 02 00 00 02                   # Get counter
<< 0004 9000                        # Continues from 3
```

### Interpreting Results

| Counter after upgrade | Meaning |
|-----------------------|---------|
| Retained (e.g., 3)   | Amendment H upgrade succeeded — `onSave()`/`onRestore()` migrated the counter |
| Reset to 0           | `onRestore()` was not called — card may not support Amendment H, or upgrade was done as delete+reinstall |
| Error on SELECT      | Upgrade failed — applet instance was lost |
