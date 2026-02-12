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

GlobalPlatform Amendment H defines a mechanism for upgrading the Executable Load File (ELF) on a card — replacing applet code without deleting the applet instance or its persistent data. This is the on-card equivalent of updating a program while preserving its saved files.

## What This Applet Provides

The persistent `counter` field (a Java `short` stored in EEPROM) serves as observable state that should survive an ELF upgrade. If the counter retains its value after a code upgrade, Amendment H is working. If it resets to zero, the card performed a full delete-and-reinstall.

## Requirements for Amendment H Compatibility

The applet satisfies the following requirements:

1. **Stable AIDs** — the package AID (`D000CAFE0001`) and applet AID (`D000CAFE000101`) remain the same across versions
2. **Version field** — `build.xml` sets `version="1.0"`, incremented for each upgrade (e.g., `1.1`, `2.0`)
3. **Stable class layout** — the `counter` field must remain at the same position in the class across versions so the JCVM maps existing instance data to the upgraded code
4. **Card support** — the card's OS and GlobalPlatform implementation must support Amendment H (not all cards do)

## Upgrade Rules

When modifying the applet for an upgrade:

- **Safe changes**: modifying method bodies, adding new methods, adding new static fields, adding new instructions
- **Unsafe changes**: removing or reordering instance fields, changing field types, renaming the class — these will corrupt or lose persistent data
- **Adding instance fields**: new fields may be appended (card-dependent), but existing field order must be preserved

## Test Procedure

### 1. Build and install v1.0

```bash
JAVA_HOME=/usr/lib/jvm/java-11-openjdk ant clean build
```

Install `HelloWorldApplet.cap` onto the card using GlobalPlatformPro or equivalent:

```bash
gp --install HelloWorldApplet.cap
```

### 2. Accumulate state

```
>> 00 A4 04 00 07 D000CAFE000101    # Select
<< 9000
>> 00 01 00 00 0C                        # Hello (counter=1)
<< 48656C6C6F20576F726C6421 9000
>> 00 01 00 00 0C                        # Hello (counter=2)
<< 48656C6C6F20576F726C6421 9000
>> 00 01 00 00 0C                        # Hello (counter=3)
<< 48656C6C6F20576F726C6421 9000
>> 00 02 00 00 02                        # Get counter
<< 0003 9000                             # Confirmed: 3
```

### 3. Build v1.1

Bump the version in `build.xml`:

```xml
version="1.1"
```

Make any code change (e.g., modify the greeting text). Then rebuild:

```bash
JAVA_HOME=/usr/lib/jvm/java-11-openjdk ant clean build
```

### 4. Perform ELF upgrade

Use GlobalPlatformPro with the `--upgrade` flag (or equivalent for your tool):

```bash
gp --upgrade HelloWorldApplet.cap
```

This replaces the load file but keeps the applet instance and its EEPROM data.

### 5. Verify state preservation

```
>> 00 A4 04 00 07 D000CAFE000101    # Select (same AID)
<< 9000
>> 00 02 00 00 02                        # Get counter
<< 0003 9000                             # Should still be 3
>> 00 01 00 00 0C                        # Hello (counter=4)
<< 48656C6C6F20576F726C6421 9000
>> 00 02 00 00 02                        # Get counter
<< 0004 9000                             # Continues from 3
```

### Interpreting Results

| Counter after upgrade | Meaning |
|-----------------------|---------|
| Retained (e.g., 3)   | Amendment H upgrade succeeded — instance data preserved |
| Reset to 0           | Card did a full delete-and-reinstall — Amendment H not supported or not used |
| Error on SELECT      | Upgrade failed — applet instance was lost |
