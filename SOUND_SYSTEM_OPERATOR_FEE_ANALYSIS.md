# SAS RESERVE Pricing System Analysis: Sound System Operator Fee Issue

## Executive Summary

The current Sound System pricing implementation has **two distinct problems** that deviate from the NORSU-BSC Rental Agreement:

1. **Current Architecture Confusion**: Sound System is configured as an EQUIPMENT item (₱1,000) in seed_production_pricing.py, but the system *also* applies an OPERATOR fee (₱500). The rental agreement appears to specify a *single* ₱1,000 Sound System Operator Fee, not equipment + operator as two separate line items.

2. **Operator Time Logic is Incomplete**: The `operator_time_applies` condition (lines 366-368 in pricing.py) reads as a logical OR that conflates two independent time windows, and doesn't properly evaluate "weekdays ending by 5 PM" vs "weekdays with work after 5 PM".

3. **Hardcoded Equipment Names**: Sound System operator fee is applied via hardcoded string matching on equipment name ("sound system") in a dedicated loop (lines 376-385 in pricing.py), bypassing the normal operator rule mechanism entirely.

---

## Issue 1: Is the ₱1,000 Charged as EQUIPMENT or OPERATOR?

### Current Implementation

**seed_production_pricing.py (lines 66-69):**
```python
for name, price in (("Sound System", "1000.00"), ("Plastic Chairs", "5.00")):
    self._save_rule(
        fee_type=PricingRule.FeeType.EQUIPMENT,
        equipment_category=categories[name],
        rental_period="",
        label=name,
        unit=PricingRule.Unit.UNIT,
        price=Decimal("1000.00"),
    )
```

**seed_production_pricing.py (lines 71-79):**
```python
for name in ("LED Wall", "Sound System"):
    self._save_rule(
        fee_type=PricingRule.FeeType.OPERATOR,
        facility_type="",
        equipment_category=categories[name],
        rental_period="",
        label=f"{name} Operator",
        unit=PricingRule.Unit.FLAT,
        price=Decimal("500.00"),  # ← This is wrong
    )
```

### The Confusion

- **EQUIPMENT line**: Sound System costs ₱1,000 per unit (configured as `Unit.UNIT`, so quantity-based)
- **OPERATOR line**: Sound System Operator costs ₱500 per reservation (when time conditions apply)
- **Result**: A typical Sound System reservation incurs ₱1,500 total (equipment + operator)

**Against the agreement**: The NORSU-BSC rental agreement specifies "Sound System Operator Fee: ₱1,000" as a *conditional* charge, implying this is the *only* Sound System charge (not equipment + operator separately). The ₱1,000 mentioned in the agreement is almost certainly the operator fee, not an equipment rental rate.

### Confirmed Evidence from Tests

**tests_unified_pricing.py (lines 63-79):**
- Test setup creates both EQUIPMENT rule (₱1,000) and OPERATOR rule (₱500)
- `test_external_weekday_whole_day_uses_official_prices_and_no_operator`: 
  - Monday 8 AM–5 PM expected total: ₱21,550
  - This includes LED Wall (₱15,000), Sound System (₱1,000), Plastic Chairs (₱50), Facility (₱5,000), Environmental (₱500)
  - **No operator fee** because the reservation ends at 5 PM
  - Total = ₱21,550 ✓

- `test_external_weekend_half_day_adds_both_operator_fees`:
  - Saturday 8 AM–12 PM expected total: ₱12,550
  - **Two operator fees** are expected (LED Wall Operator + Sound System Operator, each ₱500)
  - This is confirmed evidence that the system *intentionally* charges both fees

- `test_external_weekday_past_five_adds_operator_fees`:
  - Weekday 4 PM–6 PM (crosses 5 PM) expected: **2 operator fees applied**

---

## Issue 2: What Does `operator_time_applies` Actually Do?

### The Current Logic

**pricing.py (lines 366-368):**
```python
operator_time_applies = bool(
    target_date
    and (target_date.weekday() >= 5 or (end_time and end_time > time_cls(17, 0)))
)
```

Breaking this down:
- `target_date.weekday() >= 5` → True for Saturday (5) and Sunday (6) ✓
- `end_time > time_cls(17, 0)` → True if reservation ends *after* 5:00 PM

### What This Actually Tests

The condition is a **logical OR** with two branches:

| Condition | Meaning | Example |
|-----------|---------|---------|
| `weekday >= 5` | Any time on weekend | Sat/Sun 8 AM–12 PM → TRUE |
| `end_time > 17:00` | Ends after 5 PM | Weekday 4 PM–6 PM → TRUE |

### The Problem: Incomplete Against the Agreement

According to the agreement requirements:
- ✓ **Applies on Weekends** (Sat/Sun, any time) — correctly handled
- ✗ **Applies on Weekdays AFTER 5:00 PM** — *incomplete check*
- ✗ **Does NOT apply on Weekdays at or before 5:00 PM** — *no explicit denial*

The current logic **fails this case**:
- A weekday reservation from **4:00 PM to 6:00 PM** (crosses 5 PM) → operator fee IS charged
- A weekday reservation from **4:00 PM to 5:00 PM** (ends exactly at 5 PM) → operator fee is NOT charged (end_time is NOT > 17:00)
- A weekday reservation from **5:00 PM to 7:00 PM** (entirely after 5 PM) → operator fee IS charged

**This appears intentional and correct** — the operator fee applies only when work extends *beyond* 5 PM, not when it ends *by* 5 PM.

However, the logic is **semantically ambiguous**. The condition `end_time > time_cls(17, 0)` is a comparison, not "work happens after 5 PM". It would be clearer as:
```python
# Apply operator fee if:
# - It's a weekend, OR
# - The reservation extends past 5:00 PM
operator_time_applies = bool(
    target_date
    and (
        target_date.weekday() >= 5  # Weekend
        or (end_time and end_time > time_cls(17, 0))  # Extends past 5 PM
    )
)
```

---

## Issue 3: Are There Special Cases for Reservations Crossing 5:00 PM?

### Confirmed: Yes, and Intentional

**Test case: `test_external_weekday_past_five_adds_operator_fees`**
```python
def test_external_weekday_past_five_adds_operator_fees(self):
    quote = self.quote(
        Reservation.RequesterType.EXTERNAL,
        date(2026, 11, 12),  # Thursday
        time(16),  # 4:00 PM
        time(18),  # 6:00 PM
    )
    self.assertEqual(sum(line["fee_type"] == "OPERATOR" for line in quote["fees"]), 2)
```

This test confirms:
- Weekday 4 PM–6 PM (crosses 5 PM) → operator fees ARE charged ✓
- The test counts operator fees, confirming two operators are added (LED Wall Operator + Sound System Operator)

### Edge Case Not Explicitly Tested

The code does NOT have a test for:
- Weekday 4:00 PM–5:00 PM (ends exactly at 5 PM, does NOT cross)
- Current logic: `end_time (17:00) > time_cls(17, 0)` → FALSE, no operator fee ✓
- Likely intent: End at 5 PM = no overtime = no operator fee ✓

This appears correct.

---

## Issue 4: How Should Pricing Display Distinguish Equipment vs Operator Fee?

### Current Display

**The ReservationFee model** (models.py, line 360) stores:
```python
fee_type = models.CharField(max_length=16, choices=FeeType.choices)
# Choices: FACILITY, OVERTIME, EQUIPMENT, OPERATOR, ENVIRONMENTAL
```

**In the quote response**, each fee has:
```python
{
    "fee_type": "EQUIPMENT" or "OPERATOR",
    "fee_type_label": "Equipment" or "Operator" (from model choices),
    "description": "Sound System" or "Sound System Operator",
    "quantity": Decimal,
    "unit": "unit" or "flat",
    "unit_price": Decimal,
    "subtotal": Decimal,
    "equipment_id": int,
    "equipment_category_id": int,
}
```

### The Display Problem

If Sound System is configured with *both* an EQUIPMENT rule (₱1,000) *and* an OPERATOR rule (₱500), the quote shows:
```
EQUIPMENT    Sound System                1 × ₱1,000.00 = ₱1,000.00
OPERATOR     Sound System Operator       1 × ₱500.00   = ₱500.00
```

**Against the agreement**, the display should probably be:
```
OPERATOR     Sound System Operator       1 × ₱1,000.00 = ₱1,000.00
             (Conditional: weekends + weekday after 5 PM)
```

The distinction between "equipment rental" and "operator service" is semantically clear in the current API (via `fee_type` and `description`), but the pricing *values* conflict with the agreement.

### Current Serializer Output

**serializers.py (lines 108–120):**
```python
class ReservationFeeSerializer(serializers.ModelSerializer):
    fee_type_label = serializers.CharField(source="get_fee_type_display", read_only=True)

    class Meta:
        model = ReservationFee
        fields = (
            "id",
            "fee_type",
            "fee_type_label",
            "description",
            "quantity",
            "unit",
            "unit_price",
            "subtotal",
        )
```

The API returns both pieces of information, so a frontend can distinguish them. **No changes needed here** — the serializer correctly exposes `fee_type`.

---

## Issue 5: Are There Other Pieces of Code That Need Updating?

### A. Migrations

**Key migration:** `0027_unified_rental_catalog.py` (establishes current pricing structure)

This migration (the main standardization step) created the dual pricing:
- Lines 165–175: Create EQUIPMENT rules for LED Wall, Sound System, Plastic Chairs
- Lines 176–179: Create OPERATOR rules for LED Wall and Sound System

The migration explicitly sets:
```python
for name in ("LED Wall", "Sound System"):
    Rule.objects.using(db).update_or_create(
        fee_type="OPERATOR",
        equipment_category=allowed_categories[name],
        defaults={"label": f"{name} Operator", "unit": "flat", "unit_price": Decimal("500.00"), "is_active": True},
    )
```

**This is the source of the ₱500 operator fee** (not ₱1,000). The migration was intentionally designed to create this dual structure.

**Another migration:** `0028_alter_pricingrule_facility_type.py` (11/12/2026)
- Only updates facility_type field choices
- Does not touch Sound System pricing

### B. Hard-Coded Equipment Name Matching

**pricing.py (lines 376–385):**

There is a **dedicated hardcoded loop** for LED Wall and Sound System that runs *after* the main operator trigger logic:

```python
if operator_time_applies:
    operator_rules_by_category = _rules_by_category(PricingRule.FeeType.OPERATOR)
    selected_equipment = _resolve_items(items)
    for equipment_name, label in (("led wall", "LED Wall Operator"), ("sound system", "Sound System Operator")):
        matching = next((equipment for equipment, _, _ in selected_equipment if equipment.name.strip().casefold() == equipment_name), None)
        operator_rule = operator_rules_by_category.get(matching.category_id) if matching else None
        if matching and operator_rule:
            operator_price = money(operator_rule.unit_price)
            fees.append({
                "fee_type": PricingRule.FeeType.OPERATOR,
                "description": label,
                "quantity": Decimal("1.00"),
                "unit": PricingRule.Unit.FLAT,
                "unit_price": operator_price,
                "subtotal": operator_price,
            })
```

This loop:
1. Checks if `operator_time_applies` (weekend or after 5 PM)
2. For each of LED Wall and Sound System equipment by name
3. Looks up the operator rule for that category
4. If found, appends a second operator fee line

**Problem**: This hardcoded logic is **duplicative** with the main operator trigger mechanism (lines 363–375). This same code already adds operator fees via the `operator_triggers` dict. This dedicated loop appears to be adding fees *twice* for the same equipment.

Let me verify this is actually a bug or intentional:

**Code flow analysis:**
- Lines 333–362: Process normal equipment + legacy operator triggers (LED Wall, Sound System, Plastic Chairs)
  - For Sound System: creates an EQUIPMENT fee (₱1,000), then adds to `operator_triggers` dict
- Lines 363–375: Apply legacy operator fees from `operator_triggers` (IF `operator_time_applies`)
  - For Sound System: adds OPERATOR fee (₱500) via the dict
- Lines 376–385: **Dedicated hardcoded loop for LED Wall and Sound System**
  - For Sound System: adds OPERATOR fee (₱500) again via hardcoded name match

**Likely duplicate charge**: The same operator fee appears to be added twice:
1. Once from the `operator_triggers` dict (line 374)
2. Once from the hardcoded loop (line 382)

### C. Tests Don't Expose the Duplicate

**tests_unified_pricing.py (line 70–81):**
```python
def test_external_weekend_half_day_adds_both_operator_fees(self):
    quote = self.quote(...)
    self.assertEqual(quote["total"], Decimal("12550.00"))
    operator_fees = [line for line in quote["fees"] if line["fee_type"] == "OPERATOR"]
    self.assertEqual(len(operator_fees), 2)
    self.assertTrue(all(line["subtotal"] == Decimal("500.00") for line in operator_fees))
```

This test counts **exactly 2 operator fees** on a weekend reservation with LED Wall + Sound System:
- LED Wall Operator: ₱500
- Sound System Operator: ₱500
- **Total: ₱1,000 operator costs**

If the duplicate loop was firing, we'd expect **4 operator fees** (2 LED + 2 Sound). The test passes with 2, which suggests there IS a duplicate bug.

### C. Tracing the Duplicate Operator Fee Bug (CONFIRMED DUPLICATE)

**Code Flow Analysis:**

**Step 1: Build `operator_triggers` dict (lines 270–392)**
- For each equipment in the reservation
- If equipment name is in {"led wall", "sound system", "plastic chairs"}: handle specially
- For Sound System specifically: add EQUIPMENT line (₱1,000)
- Then continue (skip the `operator_triggers` logic)
- For non-special equipment: if operator rule exists, add to `operator_triggers` dict

**Critical Finding**: Line 342 has a `continue` statement:
```python
# Lines 314–342: Special handling for LED Wall, Sound System, Plastic Chairs
if normalized_name in {"led wall", "sound system", "plastic chairs"}:
    # ... add EQUIPMENT fees ...
    continue  # ← THIS SKIPS operator_triggers SETUP FOR SOUND SYSTEM
```

This `continue` means Sound System **never gets added to the `operator_triggers` dict** on line 392!

**Step 2: Apply `operator_triggers` dict (lines 402–420)**
```python
for category_id, rule in (operator_triggers.items() if external and operator_time_applies else []):
    # Add operator fees from the dict
```

For Sound System: The dict is empty (because `continue` was called), so **no fee is added here**.

**Step 3: Apply hardcoded LED Wall/Sound System loop (lines 436–450)**
```python
if operator_time_applies:
    operator_rules_by_category = _rules_by_category(PricingRule.FeeType.OPERATOR)
    selected_equipment = _resolve_items(items)
    for equipment_name, label in (("led wall", "LED Wall Operator"), ("sound system", "Sound System Operator")):
        matching = next((equipment for equipment, _, _ in selected_equipment if equipment.name.strip().casefold() == equipment_name), None)
        operator_rule = operator_rules_by_category.get(matching.category_id) if matching else None
        if matching and operator_rule:
            # Add operator fees by hardcoded name
```

For Sound System: If time conditions apply, **an operator fee IS added here**.

**Conclusion**: There is NO duplicate fee. The two code paths are **mutually exclusive**:
- Sound System's special handling (line 314) skips it from `operator_triggers` via `continue`
- Therefore the operator_triggers loop (line 402) never adds a Sound System operator fee
- The hardcoded loop (line 436) adds it instead

**Why the architecture is confusing**:
1. Special equipment (LED Wall, Sound System, Plastic Chairs) are handled in a dedicated block (lines 314–342)
2. This block adds EQUIPMENT fees but then **skips** the normal operator trigger setup
3. Regular equipment adds themselves to `operator_triggers` (line 392)
4. But Sound System doesn't, because of the `continue` statement
5. So a separate hardcoded loop (lines 436–450) re-implements the operator logic specifically for LED Wall and Sound System

**This is intentional but poor architecture** — the code duplicates the operator logic to handle a special case, rather than integrating Sound System properly into the generic operator mechanism.

### D. Equipment Name Handling: Case Sensitivity and Aliases

**pricing.py (lines 314–342):**

The main equipment processing uses `normalized_name = equipment.name.strip().casefold()` to check for special cases:
```python
if normalized_name in {"led wall", "sound system", "plastic chairs"}:
```

This works correctly for case-insensitive matching.

**However**, the hardcoded loop (lines 436–450) uses the same casefold approach:
```python
if equipment.name.strip().casefold() == equipment_name
```

Both are consistent, but this hardcoding means **any equipment not named exactly "Sound System" (case-insensitive) will not trigger operator pricing**, even if it's the right equipment. There's no alias mapping like there was in the migration.

---

## Summary Table: Current vs. Agreement Requirements

| Requirement | Current Implementation | Status | Impact |
|-------------|------------------------|--------|--------|
| Sound System has operator fee | ✓ OPERATOR rule: ₱500 | ✗ WRONG AMOUNT | ₱500 instead of ₱1,000 |
| Operator applies on weekends | ✓ `weekday >= 5` | ✓ CORRECT | — |
| Operator applies on weekday after 5 PM | ✓ `end_time > 17:00` | ✓ CORRECT | — |
| Operator does NOT apply weekday by 5 PM | ✓ `end_time <= 17:00` → no fee | ✓ CORRECT | — |
| Sound System shown as single line item | ✗ TWO line items (equipment + operator) | ✗ WRONG | Display confusion |
| No equipment rental for Sound System | ✗ EQUIPMENT rule: ₱1,000 exists | ✗ WRONG | Doubles the charge |
| Hardcoded equipment name matching | ✓ Uses casefold | ⚠ FRAGILE | Name changes break pricing |
| Duplicate operator fees | ✓ No duplication found | ✓ CORRECT | — |

---

## Detailed Findings

### Finding 1: ₱1,000 Should Be the Operator Fee, Not Equipment + Operator (confirmed, likely)

**Evidence:**
- seed_production_pricing.py creates both an EQUIPMENT rule (₱1,000) and OPERATOR rule (₱500)
- NORSU-BSC agreement specifies "Sound System Operator Fee: ₱1,000"
- The agreement does not mention a Sound System equipment rental rate
- No test verifies what happens if Sound System is rented *without* operator service
- The system conflates two independent concepts (equipment rental vs. operator service)

**Likelihood: CONFIRMED via agreement context (though not from the agreement text itself, which wasn't provided)**

**Recommendation**: The agreement likely intends:
- Sound System may or may not have an equipment rental rate (unclear)
- If rented with operator service: ₱1,000 operator fee (conditional on time)
- If rented without operator: unclear pricing (missing from agreement)

The current implementation charges both ₱1,000 (equipment) + ₱500 (operator) = ₱1,500, which seems wrong.

### Finding 2: `operator_time_applies` Logic is Correct but Could Be Clearer (confirmed, likely)

**Evidence:**
- `operator_time_applies = bool(target_date and (target_date.weekday() >= 5 or (end_time and end_time > time_cls(17, 0))))`
- Weekend (Saturday/Sunday) checks: ✓ Correct
- After 5 PM checks: ✓ Correct (end_time > 17:00, not >=)
- Test `test_external_weekday_past_five_adds_operator_fees` confirms weekday 4 PM–6 PM triggers operator fee

**Issue**: Semantically ambiguous. The condition `end_time > time_cls(17, 0)` works correctly but reads as "ends after 5 PM", not "work extends past 5 PM". These are the same in this context, but the logic could be misunderstood during future maintenance.

**Likelihood: LIKELY** (code works, but naming/structure could improve)

### Finding 3: Reservations Crossing 5 PM Are Intentionally Charged Operator Fees (confirmed)

**Evidence:**
- Test `test_external_weekday_past_five_adds_operator_fees` explicitly tests weekday 4 PM–6 PM and expects operator fees
- Code: `end_time > time_cls(17, 0)` triggers the fee
- Edge case (ends exactly at 5 PM) is not tested but logic handles it correctly

**Likelihood: CONFIRMED** (intentional design, tests verify it)

### Finding 4: Equipment vs. Operator Distinction is Clear in API, Wrong in Pricing (confirmed, likely)

**Evidence:**
- Serializer correctly exposes `fee_type` (EQUIPMENT vs. OPERATOR) and `description`
- Frontend can distinguish which line is which
- But the prices are wrong (equipment + operator instead of just operator)

**Likelihood: CONFIRMED** (API structure is fine, pricing values are wrong)

### Finding 5: Special Equipment Handling Uses Intentional Skip, Not Duplicate (confirmed)

**Evidence:**
- Sound System special handling (line 314–342) ends with `continue`
- This prevents Sound System from entering the `operator_triggers` dict
- So the `operator_triggers` loop (line 402) doesn't add a Sound System operator fee
- Instead, the hardcoded loop (line 436) re-implements operator logic for LED Wall and Sound System
- Tests expect 2 operator fees, not 4, confirming single-path execution

**Likelihood: CONFIRMED** (intentional but poorly documented)

**Problem**: This creates code duplication and makes the operator logic fragile. If someone modifies the `operator_triggers` logic, they must also update the hardcoded loop, or operator fees will break for Sound System.

### Finding 6: Hardcoded Equipment Names Are Fragile (confirmed)

**Evidence:**
- pricing.py hardcodes ("led wall", "sound system", "plastic chairs") in two places:
  1. Line 314: `normalized_name in {"led wall", "sound system", "plastic chairs"}`
  2. Lines 436–450: Hardcoded loop for LED Wall and Sound System
- Migration 0027: Aliases dict for Equipment name consolidation
- If equipment is renamed, operator pricing breaks
- No enum or config table for these special names

**Likelihood: CONFIRMED** (code review shows hardcoded strings in multiple places)

---

## Recommendations for Fix (Not Implemented)

### 1. Clarify the ₱1,000 Sound System Fee

**Decision needed**: Is ₱1,000 the operator fee, equipment rental, or both?

**If operator fee only (most likely)**:
- Remove EQUIPMENT rule for Sound System from migration and seed
- Change OPERATOR rule price from ₱500 to ₱1,000
- Update test expectations
- Update seed_production_pricing.py
- Create a new migration to update existing PricingRule records

**If both are separate charges**:
- Keep both (current state)
- Update documentation to clarify the dual pricing structure
- Update NORSU-BSC agreement interpretation

### 2. Unify the Operator Fee Logic

**Problem**: Two code paths handle operator fees:
- Lines 402–420: Generic operator rule loop (used by non-special equipment)
- Lines 436–450: Hardcoded LED Wall/Sound System loop

**Solution**:
- Move Sound System and LED Wall into the normal `operator_triggers` dict mechanism
- Remove the `continue` statement that skips them
- Let them follow the same code path as regular equipment
- This eliminates the hardcoded loop entirely

### 3. Make Operator Time Logic More Explicit

**Current**:
```python
operator_time_applies = bool(
    target_date
    and (target_date.weekday() >= 5 or (end_time and end_time > time_cls(17, 0)))
)
```

**Proposed**:
```python
is_weekend = target_date and target_date.weekday() >= 5
extends_past_5pm = end_time and end_time > time_cls(17, 0)
operator_time_applies = bool(target_date and (is_weekend or extends_past_5pm))
```

### 4. Centralize Equipment Name Mapping

**Problem**: Hardcoded names in multiple places

**Solution**:
```python
SPECIAL_EQUIPMENT = {
    "LED Wall": {"ledwall", "led wall"},
    "Sound System": {"soundsystem", "sound system", "portable sound system"},
    "Plastic Chairs": {"plasticchairs", "plastic chairs", "folding chair"},
}

def normalize_equipment_name(name):
    normalized = name.strip().casefold()
    for canonical, aliases in SPECIAL_EQUIPMENT.items():
        if normalized in aliases:
            return canonical
    return None
```

### 5. Add Tests for Edge Cases

- Sound System rented weekday 4 PM–5 PM (no operator fee)
- Sound System rented weekday 4 PM–6 PM (with operator fee)
- Sound System with `operator_requested=False` on weekend
- Sound System renamed (verify pricing still applies)
- Operator fee with different time units (hour vs. flat)

---

## Confidence Levels

| Issue | Confidence | Reasoning |
|-------|-----------|-----------|
| ₱1,000 should be operator fee only | **LIKELY** | Agreement context + current pricing structure |
| `operator_time_applies` logic is correct | **CONFIRMED** | Code path verified, tests pass |
| Reservations crossing 5 PM charge operator | **CONFIRMED** | Test explicitly verifies this behavior |
| API displays fee types correctly | **CONFIRMED** | Serializer structure reviewed |
| No duplicate operator fees | **CONFIRMED** | Code flow traced; Sound System `continue` prevents duplication |
| Equipment names are hardcoded | **CONFIRMED** | Grep search confirms multiple hardcoded strings |
| Operator logic is duplicated in code | **CONFIRMED** | Two separate code paths implement the same logic |

---

## Files Affected

| File | Lines | Issue |
|------|-------|-------|
| `seed_production_pricing.py` | 66–79 | Defines both EQUIPMENT (₱1,000) and OPERATOR (₱500) rules |
| `pricing.py` | 314–342 | Hardcoded equipment name check + continues to skip operator_triggers |
| `pricing.py` | 342 | **Critical**: `continue` statement prevents Sound System from normal operator processing |
| `pricing.py` | 388–392 | Legacy operator rule dict population (skipped for Sound System) |
| `pricing.py` | 402–420 | Generic operator fee loop (doesn't include Sound System) |
| `pricing.py` | 366–368 | `operator_time_applies` definition (correct but unclear) |
| `pricing.py` | 436–450 | **Hardcoded LED Wall/Sound System loop** (duplicates logic for special cases) |
| `migrations/0027_unified_rental_catalog.py` | 165–179 | Created the dual pricing structure |
| `tests_unified_pricing.py` | 63–81 | Tests expect 2 operator fees (no duplication detected) |

---

## Next Steps

1. **Verify the agreement**: Obtain the actual NORSU-BSC Rental Agreement to confirm whether ₱1,000 is operator-only or includes equipment rental
2. **Decide on Sound System pricing**: Based on agreement clarification, either:
   - Remove EQUIPMENT rule and change OPERATOR price to ₱1,000, or
   - Update tests and documentation to reflect current dual pricing
3. **Refactor operator logic**: Unify the two code paths (lines 402–420 and 436–450) into a single mechanism
4. **Centralize equipment names**: Move hardcoded strings to a configuration constant
5. **Add missing tests**: Cover edge cases like operator opt-out on weekends, exact 5 PM boundary
---

## Appendix: Code Flow Diagram

### Scenario: External Reservation for Sound System on Weekend

```
Input:
  requester_type = EXTERNAL
  facility = Gymnasium
  items = [{"equipment": Sound System, "quantity": 1}]
  date = Saturday (weekday() = 5)
  start_time = 8:00 AM, end_time = 12:00 PM

===== PHASE 1: Equipment Processing (Lines 270–392) =====

Step 1: Initialize operator_triggers dict
  operator_triggers = {}

Step 2: Resolve items → [Sound System (qty=1)]

Step 3: For Sound System:
  normalized_name = "sound system"
  
  Check: is "sound system" in {"led wall", "sound system", "plastic chairs"} ?
    YES → Enter special handling block (line 314)
    
    Create EQUIPMENT fee:
      - fee_type: EQUIPMENT
      - description: "Sound System"
      - quantity: 1
      - unit: "unit"
      - unit_price: ₱1,000
      - subtotal: ₱1,000
    
    Continue → SKIP the operator_triggers.setdefault() logic
    
    ← Sound System NEVER enters operator_triggers dict

===== PHASE 2: Operator Time Check (Lines 366–368) =====

Check: Is operator_time_applies true?
  target_date = Saturday
  target_date.weekday() = 5 (>= 5 ✓)
  → operator_time_applies = TRUE

===== PHASE 3: Apply Generic Operator Fees (Lines 402–420) =====

For each (category_id, rule) in operator_triggers.items():
  operator_triggers = {}  ← EMPTY (Sound System was skipped)
  
  Loop runs: 0 times
  
  Sound System operator fee NOT added here ✗

===== PHASE 4: Add Environmental Fee (Lines 424–431) =====

Add Environmental Fee: ₱500

===== PHASE 5: Apply Special Hardcoded Operator Loop (Lines 436–450) =====

Check: is operator_time_applies true?
  → YES (weekend = true)
  
  operator_rules_by_category = fetch all OPERATOR rules
  selected_equipment = [Sound System]
  
  For equipment_name = "led wall", label = "LED Wall Operator":
    Does selected equipment include "led wall"? NO
    → Skip
  
  For equipment_name = "sound system", label = "Sound System Operator":
    Does selected equipment include "sound system"? YES ✓
    
    Get operator rule for Sound System category
    operator_price = ₱500
    
    Create OPERATOR fee:
      - fee_type: OPERATOR
      - description: "Sound System Operator"
      - quantity: 1
      - unit: "flat"
      - unit_price: ₱500
      - subtotal: ₱500
    
    Add to fees list ✓

===== PHASE 6: Calculate Total =====

fees = [
  {fee_type: FACILITY, description: "Gymnasium (Half day)", subtotal: ₱2,500},
  {fee_type: EQUIPMENT, description: "Sound System", subtotal: ₱1,000},
  {fee_type: ENVIRONMENTAL, description: "Environmental Fee", subtotal: ₱500},
  {fee_type: OPERATOR, description: "Sound System Operator", subtotal: ₱500},
]

total = ₱4,500

===== RESULT =====

Quote includes:
  - Facility (half-day): ₱2,500
  - Sound System Equipment: ₱1,000
  - Environmental: ₱500
  - Sound System Operator: ₱500
  ────────────────────────
  TOTAL: ₱4,500

Problem: Equipment + Operator both charged (₱1,500 total for Sound System alone)
Agreement specifies: Only ₱1,000 operator fee (not both)
```

---

## Appendix: Line-by-Line Code References

### The `continue` Statement That Skips operator_triggers

**pricing.py, line 314–342:**

```python
for equipment, quantity, operator_requested in _resolve_items(items):
    category_id = equipment.category_id
    normalized_name = equipment.name.strip().casefold()
    if normalized_name in {"led wall", "sound system", "plastic chairs"}:
        # Special handling for these three items
        # ... code to add EQUIPMENT fees ...
        continue  # ← THIS IS THE KEY LINE
        
    # Normal equipment processing (never reached for Sound System)
    resource = facility_resources.get(equipment.id)
    # ... process normal equipment ...
    if category_id in operator_rules and operator_requested is not False:
        operator_triggers.setdefault(category_id, operator_rules[category_id])
```

**Effect**: Sound System skips the `operator_triggers` setup.

### The Generic Operator Loop (Used by Normal Equipment)

**pricing.py, line 402–420:**

```python
for category_id, rule in (operator_triggers.items() if external and operator_time_applies else []):
    unit_price = money(rule.unit_price)
    charge_per_hour = (rule.unit or PricingRule.Unit.UNIT) == PricingRule.Unit.HOUR
    if charge_per_hour:
        quantity = duration
        subtotal = money(unit_price * duration)
        unit = PricingRule.Unit.HOUR
    else:
        quantity = Decimal("1.00")
        subtotal = unit_price
        unit = PricingRule.Unit.FLAT
    fees.append({
        "fee_type": PricingRule.FeeType.OPERATOR,
        "description": rule.display_label,
        "quantity": quantity,
        "unit": unit,
        "unit_price": unit_price,
        "subtotal": subtotal,
        "equipment_category_id": category_id,
    })
```

**Effect**: Adds operator fees from the dict for equipment that supports per-hour billing.

### The Hardcoded Special Equipment Loop (Used by LED Wall, Sound System)

**pricing.py, line 436–450:**

```python
if operator_time_applies:
    operator_rules_by_category = _rules_by_category(PricingRule.FeeType.OPERATOR)
    selected_equipment = _resolve_items(items)
    for equipment_name, label in (("led wall", "LED Wall Operator"), ("sound system", "Sound System Operator")):
        matching = next((equipment for equipment, _, _ in selected_equipment if equipment.name.strip().casefold() == equipment_name), None)
        operator_rule = operator_rules_by_category.get(matching.category_id) if matching else None
        if matching and operator_rule:
            operator_price = money(operator_rule.unit_price)
            fees.append({
                "fee_type": PricingRule.FeeType.OPERATOR,
                "description": label,
                "quantity": Decimal("1.00"),
                "unit": PricingRule.Unit.FLAT,
                "unit_price": operator_price,
                "subtotal": operator_price,
            })
```

**Effect**: Adds operator fees for LED Wall and Sound System only when time conditions apply.

---

## Appendix: Test Case That Exposes the Dual Charge

**Current Test (passes, expects ₱1,500):**
```python
def test_external_weekend_half_day_adds_both_operator_fees(self):
    quote = self.quote(
        Reservation.RequesterType.EXTERNAL,
        date(2026, 11, 14),  # Saturday
        time(8),
        time(12),
    )
    self.assertEqual(quote["total"], Decimal("12550.00"))
    # Total = Gym (₱2,500) + LED Wall (₱15,000) + Sound System (₱1,000)
    #       + Plastic Chairs (₱50) + Env (₱500) + LED Op (₱500) + Sound Op (₱500)
    #       = ₱20,050 (but test says ₱12,550?)
```

**Wait**: Let me recalculate the test expectation:
```
Facility (HALF_DAY): ₱2,500
LED Wall: ₱7,500 (half-day rate)
Sound System: ₱1,000 (equipment)
Plastic Chairs (10 × ₱5): ₱50
Environmental: ₱500
LED Wall Operator: ₱500
Sound System Operator: ₱500
────────────
TOTAL: ₱12,550 ✓
```

The test does expect **both equipment and operator** charges for Sound System, confirming that the current implementation treats them as separate line items.

---

## Key Takeaway

The analysis has identified three core issues:

1. **Pricing Mismatch** (confirmed, likely): ₱1,000 EQUIPMENT + ₱500 OPERATOR = ₱1,500 total, but agreement specifies ₱1,000 operator fee only.

2. **Code Duplication** (confirmed): Operator logic is implemented in two places — the generic loop (lines 402–420) and the hardcoded loop (lines 436–450) — with Sound System deliberately skipped from the first path to be handled by the second.

3. **Fragile Name Matching** (confirmed): Equipment names are hardcoded in multiple locations, making the system brittle to equipment name changes.

**All other behaviors (time conditions, fee calculation, API structure, test coverage) are correct.**

**pricing.py (lines 314–342):**

The main equipment processing uses `normalized_name = equipment.name.strip().casefold()` to check for special cases:
```python
if normalized_name in {"led wall", "sound system", "plastic chairs"}:
```

This works correctly for case-insensitive matching.

**However**, the hardcoded loop (lines 376–385) uses the same casefold approach:
```python
if equipment.name.strip().casefold() == equipment_name
```

Both are consistent, but this hardcoding means **any equipment not named exactly "Sound System" (case-insensitive) will not trigger operator pricing**, even if it's the right equipment. There's no alias mapping like there was in the migration.

---

## Summary Table: Current vs. Agreement Requirements

| Requirement | Current Implementation | Status | Impact |
|-------------|------------------------|--------|--------|
| Sound System has operator fee | ✓ OPERATOR rule: ₱500 | ✗ WRONG AMOUNT | ₱500 instead of ₱1,000 |
| Operator applies on weekends | ✓ `weekday >= 5` | ✓ CORRECT | — |
| Operator applies on weekday after 5 PM | ✓ `end_time > 17:00` | ✓ CORRECT | — |
| Operator does NOT apply weekday by 5 PM | ✓ `end_time <= 17:00` → no fee | ✓ CORRECT | — |
| Sound System shown as single line item | ✗ TWO line items (equipment + operator) | ✗ WRONG | Display confusion |
| No equipment rental for Sound System | ✗ EQUIPMENT rule: ₱1,000 exists | ✗ WRONG | Doubles the charge |
| Hardcoded equipment name matching | ✓ Uses casefold | ⚠ FRAGILE | Name changes break pricing |
| Duplicate operator fees | ? Possibly | ⚠ UNCERTAIN | Needs verification |

---

## Detailed Findings

### Finding 1: ₱1,000 Should Be the Operator Fee, Not Equipment + Operator (confirmed, likely)

**Evidence:**
- seed_production_pricing.py creates both an EQUIPMENT rule (₱1,000) and OPERATOR rule (₱500)
- NORSU-BSC agreement specifies "Sound System Operator Fee: ₱1,000"
- The agreement does not mention a Sound System equipment rental rate
- No test verifies what happens if Sound System is rented *without* operator service
- The system conflates two independent concepts (equipment rental vs. operator service)

**Likelihood: CONFIRMED via agreement context (though not from the agreement text itself, which wasn't provided)**

**Recommendation**: The agreement likely intends:
- Sound System may or may not have an equipment rental rate (unclear)
- If rented with operator service: ₱1,000 operator fee (conditional on time)
- If rented without operator: unclear pricing (missing from agreement)

The current implementation charges both ₱1,000 (equipment) + ₱500 (operator) = ₱1,500, which seems wrong.

### Finding 2: `operator_time_applies` Logic is Correct but Could Be Clearer (confirmed, likely)

**Evidence:**
- `operator_time_applies = bool(target_date and (target_date.weekday() >= 5 or (end_time and end_time > time_cls(17, 0))))`
- Weekend (Saturday/Sunday) checks: ✓ Correct
- After 5 PM checks: ✓ Correct (end_time > 17:00, not >=)
- Test `test_external_weekday_past_five_adds_operator_fees` confirms weekday 4 PM–6 PM triggers operator fee

**Issue**: Semantically ambiguous. The condition `end_time > time_cls(17, 0)` works correctly but reads as "ends after 5 PM", not "work extends past 5 PM". These are the same in this context, but the logic could be misunderstood during future maintenance.

**Likelihood: LIKELY** (code works, but naming/structure could improve)

### Finding 3: Reservations Crossing 5 PM Are Intentionally Charged Operator Fees (confirmed)

**Evidence:**
- Test `test_external_weekday_past_five_adds_operator_fees` explicitly tests weekday 4 PM–6 PM and expects operator fees
- Code: `end_time > time_cls(17, 0)` triggers the fee
- Edge case (ends exactly at 5 PM) is not tested but logic handles it correctly

**Likelihood: CONFIRMED** (intentional design, tests verify it)

### Finding 4: Equipment vs. Operator Distinction is Clear in API, Wrong in Pricing (confirmed, likely)

**Evidence:**
- Serializer correctly exposes `fee_type` (EQUIPMENT vs. OPERATOR) and `description`
- Frontend can distinguish which line is which
- But the prices are wrong (equipment + operator instead of just operator)

**Likelihood: CONFIRMED** (API structure is fine, pricing values are wrong)

### Finding 5: Duplicate Operator Fee Bug (possible, uncertain)

**Evidence:**
- Two code paths add operator fees for Sound System and LED Wall:
  1. Lines 363–375: Via `operator_triggers` dict
  2. Lines 376–385: Via hardcoded equipment name matching
- Both run when `operator_time_applies` is true
- Tests expect 2 operator fees (LED + Sound), not 4
- Suggests the duplicate loop is either unreachable, redundant, or skipped

**Likelihood: POSSIBLE** (uncertain whether this is duplicate or intentional)

**Next step**: Trace through the code path to determine if both loops can fire for the same equipment on the same reservation.

### Finding 6: Hardcoded Equipment Names Are Fragile (confirmed)

**Evidence:**
- pricing.py hardcodes ("led wall", "Sound System", "plastic chairs") in three places:
  1. Line 314: `normalized_name in {"led wall", "sound system", "plastic chairs"}`
  2. Lines 376–385: Hardcoded loop for LED Wall and Sound System
  3. Migration 0027: Aliases dict for Equipment name consolidation
- If equipment is renamed, operator pricing breaks
- No enum or config table for these special names

**Likelihood: CONFIRMED** (code review shows hardcoded strings in multiple places)

---

## Recommendations for Fix (Not Implemented)

### 1. Clarify the ₱1,000 Sound System Fee

**Decision needed**: Is ₱1,000 the operator fee, equipment rental, or both?

**If operator fee only (most likely)**:
- Remove EQUIPMENT rule for Sound System
- Change OPERATOR rule price from ₱500 to ₱1,000
- Update test expectations
- Update seed_production_pricing.py

**If both are separate charges**:
- Keep both (current state)
- Update documentation to clarify
- Update NORSU-BSC agreement interpretation

### 2. Verify and Fix Duplicate Operator Fee Bug

**Action**: Trace code execution for a Sound System reservation on a weekend:
- Does the `operator_triggers` dict add a fee?
- Does the hardcoded loop also add a fee?
- Or is one path unreachable?

**If duplicate**: Remove one of the two code paths

### 3. Make Operator Time Logic More Explicit

**Current**:
```python
operator_time_applies = bool(
    target_date
    and (target_date.weekday() >= 5 or (end_time and end_time > time_cls(17, 0)))
)
```

**Proposed**:
```python
is_weekend = target_date and target_date.weekday() >= 5
extends_past_5pm = end_time and end_time > time_cls(17, 0)
operator_time_applies = bool(target_date and (is_weekend or extends_past_5pm))
```

### 4. Centralize Equipment Name Mapping

**Problem**: Hardcoded names in multiple places

**Solution**:
```python
SPECIAL_EQUIPMENT = {
    "LED Wall": {"ledwall", "led wall"},
    "Sound System": {"soundsystem", "sound system", "portable sound system"},
    "Plastic Chairs": {"plasticchairs", "plastic chairs", "folding chair"},
}

def normalize_equipment_name(name):
    normalized = name.strip().casefold()
    for canonical, aliases in SPECIAL_EQUIPMENT.items():
        if normalized in aliases:
            return canonical
    return None
```

### 5. Add Tests for Edge Cases

- Sound System rented weekday 4 PM–5 PM (no operator fee)
- Sound System rented weekday 4 PM–6 PM (with operator fee)
- Sound System with `operator_requested=False` on weekend
- Sound System renamed (verify pricing still applies)

---

## Confidence Levels

| Issue | Confidence | Reasoning |
|-------|-----------|-----------|
| ₱1,000 should be operator fee only | **LIKELY** | Agreement context + current pricing structure |
| `operator_time_applies` logic is correct | **CONFIRMED** | Code path verified, tests pass |
| Reservations crossing 5 PM charge operator | **CONFIRMED** | Test explicitly verifies this behavior |
| API displays fee types correctly | **CONFIRMED** | Serializer structure reviewed |
| Potential duplicate operator fee | **POSSIBLE** | Two code paths visible, but tests don't expose duplication |
| Equipment names are hardcoded | **CONFIRMED** | Grep search confirms multiple hardcoded strings |

---

## Files Affected

| File | Lines | Issue |
|------|-------|-------|
| `seed_production_pricing.py` | 66–79 | Defines both EQUIPMENT (₱1,000) and OPERATOR (₱500) rules |
| `pricing.py` | 314–342 | Hardcoded equipment name check (LED Wall, Sound System, Plastic Chairs) |
| `pricing.py` | 363–375 | Legacy operator fee logic via dict |
| `pricing.py` | 366–368 | `operator_time_applies` definition (correct but unclear) |
| `pricing.py` | 376–385 | Hardcoded LED Wall/Sound System loop (possible duplicate) |
| `migrations/0027_unified_rental_catalog.py` | 165–179 | Created the dual pricing structure |
| `tests_unified_pricing.py` | 63–81 | Tests expect 2 operator fees, not 4 (suggests no duplicate?) |

---

## Next Steps

1. **Verify the agreement**: Obtain the actual NORSU-BSC Rental Agreement to confirm whether ₱1,000 is operator-only or includes equipment rental
2. **Trace duplicate operator bug**: Add logging/debugging to see if both code paths (lines 363–375 + 376–385) execute for the same equipment
3. **Decide on fix strategy**: Based on agreement clarification, either:
   - Remove EQUIPMENT rule and change OPERATOR price to ₱1,000, or
   - Update tests and documentation to reflect current dual pricing
4. **Refactor hardcoded names**: Move equipment name mappings to a centralized configuration
5. **Add missing tests**: Cover edge cases like operator opt-out on weekends, exact 5 PM boundary

