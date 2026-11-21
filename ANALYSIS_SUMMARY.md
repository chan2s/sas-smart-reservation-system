# Sound System Operator Fee Issue — Analysis Summary

## Overview

A comprehensive analysis of the GSO RESERVE pricing system has identified **three distinct issues** with Sound System operator fee handling that deviate from the NORSU-BSC Rental Agreement:

1. **Pricing Mismatch**: System charges ₱1,500 (equipment ₱1,000 + operator ₱500), but agreement specifies ₱1,000 operator fee only
2. **Code Duplication**: Operator logic is split across two code paths, with Sound System deliberately skipped from the generic path
3. **Fragile Name Matching**: Equipment names hardcoded in multiple locations

---

## Key Findings

| Finding | Status | Severity | Impact |
|---------|--------|----------|--------|
| ₱1,000 should be operator fee only, not equipment + operator | **LIKELY** | HIGH | Overcharges external organizations by ₱500 per Sound System reservation |
| `operator_time_applies` logic is semantically ambiguous but functionally correct | **CONFIRMED** | LOW | Works correctly but could confuse future maintenance |
| Weekend and after-5 PM time conditions are correct | **CONFIRMED** | N/A | No changes needed |
| Special equipment handling uses intentional skip, not accidental duplicate | **CONFIRMED** | MEDIUM | Creates code duplication and fragility |
| Equipment names are hardcoded in pricing.py and migrations | **CONFIRMED** | MEDIUM | Equipment renames break operator fee logic |
| API properly distinguishes equipment vs operator fees | **CONFIRMED** | N/A | Display structure is correct |

---

## Issue Breakdown

### 1. Pricing Mismatch (HIGH SEVERITY)

**Current Behavior:**
- EQUIPMENT rule: Sound System costs ₱1,000 per unit
- OPERATOR rule: Sound System Operator costs ₱500 per reservation (when time conditions apply)
- **Total: ₱1,500** for a Sound System reservation that qualifies for operator service

**Agreement Requirement:**
- "Sound System Operator Fee: ₱1,000 (conditional)"
- No mention of separate equipment rental

**Code Locations:**
- `seed_production_pricing.py` lines 66–79: Creates both rules
- `migrations/0027_unified_rental_catalog.py` lines 165–179: Establishes the dual structure

**Test Evidence:**
- `tests_unified_pricing.py::test_external_weekend_half_day_adds_both_operator_fees` expects ₱12,550 for weekend half-day with LED Wall, Sound System, Plastic Chairs

**Resolution Required:**
- **Option A (most likely)**: Remove EQUIPMENT rule, change OPERATOR price from ₱500 to ₱1,000
- **Option B**: Keep current structure, update documentation and agreement interpretation

---

### 2. Code Duplication (MEDIUM SEVERITY)

**Current Architecture:**

The system has two separate code paths that both implement operator fee logic:

**Path 1 (Generic Operator Loop):**
- Lines 402–420 in `pricing.py`
- Iterates over `operator_triggers` dict
- Adds operator fees for any equipment with an operator rule
- **Sound System never reaches this path** due to `continue` statement on line 342

**Path 2 (Hardcoded Special Equipment Loop):**
- Lines 436–450 in `pricing.py`
- Explicitly loops through ("led wall", "sound system")
- Hardcoded equipment name matching
- **Only used for LED Wall and Sound System**

**Why This Exists:**
- Lines 314–342: Sound System special handling ends with `continue`
- This skips Sound System from the normal `operator_triggers` dict setup (line 392)
- So Sound System needs its own operator logic (lines 436–450)

**Problem:**
- If someone changes the generic operator logic (lines 402–420), Sound System breaks unless the hardcoded loop is also updated
- There's duplicate logic that should be unified
- Tests don't catch this because the two paths never run for the same equipment

**Test Case Not Covered:**
- Sound System with `operator_requested=False` on a weekend
- Current behavior: Unknown (would hardcoded loop override the flag?)
- Expected behavior: No operator fee (requester opted out)

**Resolution Required:**
- Unify the operator logic by removing the `continue` statement
- Let Sound System flow through the generic operator path like other equipment
- Delete the hardcoded loop (lines 436–450)

---

### 3. Fragile Name Matching (MEDIUM SEVERITY)

**Current Implementation:**
- Hardcoded strings: "led wall", "sound system", "plastic chairs"
- Case-insensitive matching via `equipment.name.strip().casefold()`
- Appears in two locations:
  1. `pricing.py` line 314: Special equipment check
  2. `pricing.py` line 442: Hardcoded operator loop

**Problem:**
- If Sound System equipment is renamed to "Portable Sound System" or "Sound Equipment"
- Operator fees stop applying (equipment not recognized)
- No alias mapping exists (unlike in the migration consolidation)

**Resolution Required:**
- Centralize equipment name mapping in a configuration constant
- Use database category IDs instead of string matching where possible
- Map aliases for equipment renames

---

## Time Logic Verification (CORRECT)

The `operator_time_applies` condition is **functionally correct** but could be clearer:

```python
# Current (works correctly)
operator_time_applies = bool(
    target_date
    and (target_date.weekday() >= 5 or (end_time and end_time > time_cls(17, 0)))
)
```

**Verified Behaviors:**
- ✓ Weekend (Saturday/Sunday): Operator fee applies
- ✓ Weekday before 5 PM: No operator fee (end_time <= 17:00)
- ✓ Weekday crossing 5 PM (4 PM–6 PM): Operator fee applies (end_time > 17:00)
- ✓ Weekday after 5 PM (5 PM–7 PM): Operator fee applies (end_time > 17:00)

**Test Coverage:**
- `test_external_weekend_half_day_adds_both_operator_fees`: Verifies weekend
- `test_external_weekday_whole_day_uses_official_prices_and_no_operator`: Verifies weekday ending at 5 PM
- `test_external_weekday_past_five_adds_operator_fees`: Verifies weekday crossing 5 PM

---

## Files Requiring Review

### Primary Files (Changes Needed)

1. **seed_production_pricing.py** (backend/reservations/management/commands/)
   - Lines 66–79: EQUIPMENT and OPERATOR rule creation
   - Decision: Remove EQUIPMENT rule or clarify dual pricing

2. **pricing.py** (backend/reservations/services/)
   - Lines 314–342: Special equipment handling (contains `continue` statement)
   - Lines 366–368: `operator_time_applies` definition (semantics only, works correctly)
   - Lines 402–420: Generic operator fee loop
   - Lines 436–450: Hardcoded LED Wall/Sound System loop (for deletion or unification)

3. **migrations/0027_unified_rental_catalog.py** (backend/reservations/migrations/)
   - Lines 165–179: Creates both EQUIPMENT and OPERATOR rules
   - Will need updated forward() function or new migration depending on resolution

### Test Files (Tests Need Updating)

1. **tests_unified_pricing.py** (backend/reservations/)
   - Lines 63–81: Tests assume dual pricing (₱1,500 total)
   - Needs new tests for edge cases:
     - Exact 5 PM boundary (no operator fee)
     - operator_requested=False on weekend
     - Equipment name variations

### Reference Files (For Understanding)

1. **models.py** (lines 320–380): PricingRule and ReservationFee model definitions
2. **serializers.py** (lines 108–120): ReservationFeeSerializer (API structure is correct)
3. **views.py** (lines 40–43, 540–556): Quote API endpoints that call pricing service

---

## Recommended Action Plan

### Phase 1: Clarification (Required First)
1. Obtain and review the actual NORSU-BSC Rental Agreement document
2. Confirm: Is ₱1,000 the operator fee only, or equipment + operator combined?
3. Document the decision in a design specification

### Phase 2: Fix Pricing (If ₱1,000 is operator-only)
1. Create a new migration to mark old EQUIPMENT rule as inactive
2. Update OPERATOR rule price from ₱500 to ₱1,000
3. Update seed_production_pricing.py to reflect new pricing
4. Update test expectations to ₱11,550 instead of ₱12,550

### Phase 3: Refactor Code Logic (Regardless of Pricing Decision)
1. Remove `continue` statement from line 342
2. Unify operator logic by deleting hardcoded loop (lines 436–450)
3. Add new tests for missing edge cases
4. Move hardcoded equipment names to centralized configuration

### Phase 4: Improve Code Quality
1. Add inline documentation explaining why LED Wall and Sound System need special handling
2. Add tests for equipment name variations
3. Consider using equipment category IDs instead of name matching

---

## Confidence Summary

| Issue | Confidence | Evidence |
|-------|-----------|----------|
| ₱1,000 should be operator fee | LIKELY | Agreement context, current dual pricing structure |
| operator_time_applies logic is correct | CONFIRMED | Code trace + test verification |
| Weekend conditions work correctly | CONFIRMED | Test case passes |
| After-5 PM conditions work correctly | CONFIRMED | Test case passes |
| Code duplication exists | CONFIRMED | Two separate code paths identified |
| Equipment names are hardcoded | CONFIRMED | String grep finds multiple locations |
| No actual duplicate fees charged | CONFIRMED | Tests expect 2 fees, not 4 |

---

## Related Documentation

See `SOUND_SYSTEM_OPERATOR_FEE_ANALYSIS.md` for:
- Detailed code flow diagrams
- Line-by-line code references
- Complete test case analysis
- Detailed findings with confidence levels
- Appendices with code examples and execution flows

---

Generated: Analysis of GSO RESERVE pricing system for Sound System operator fee compliance
