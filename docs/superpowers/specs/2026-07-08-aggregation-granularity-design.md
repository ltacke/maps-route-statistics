# Aggregation Granularity Design: Minute-Level Precision

**Date:** 2026-07-08  
**Status:** Approved  
**Goal:** Upgrade aggregation from hour-level to minute-level buckets to enable precise departure time recommendations with 5-minute sampling intervals.

## Problem Statement

Current aggregation groups data by `weekday × hour`, which loses precision when sampling at 5-minute intervals:
- 12 measurements per hour get averaged together
- Early-hour measurements (08:05) and late-hour measurements (08:55) land in the same bucket
- Analytics features (recommendations, rankings) can only suggest hour-level precision ("leave at 8am" instead of "leave at 8:35am")

With 5-minute intervals capturing asymmetric traffic patterns, we need minute-level insights.

## Design Decision: Minute-Bucket Aggregation

### Data Model Changes

**Current structure (2 levels):**
```json
{
  "routes": {
    "outbound": {
      "by_weekday_hour": {
        "Monday": {
          "08": {"avg": 1820, "min": 1780, "max": 1860, "count": 12}
        }
      }
    }
  }
}
```

**New structure (3 levels):**
```json
{
  "routes": {
    "outbound": {
      "by_weekday_hour": {
        "Monday": {
          "08": {
            "35": {"avg": 1820, "min": 1780, "max": 1860, "count": 8},
            "40": {"avg": 1950, "min": 1900, "max": 2010, "count": 7},
            "45": {"avg": 1880, "min": 1850, "max": 1920, "count": 6}
          }
        }
      }
    }
  }
}
```

**Key name stays `by_weekday_hour`** to minimize breaking changes. The structure simply adds one more nesting level for minutes.

### Backend Implementation (build_stats.py)

**Minute extraction:**
```python
from datetime import datetime

ts = datetime.fromisoformat(row["timestamp_utc"])
wd = ts.strftime("%A")  # "Monday"
hr = str(ts.hour).zfill(2)  # "08"
mm = str(ts.minute).zfill(2)  # "35"

by_weekday_hour_minute[wd][hr][mm].append(duration_seconds)
```

**Aggregation loop:**
```python
aggregated[wd] = {}
for hr, minutes in by_weekday_hour_minute[wd].items():
    aggregated[wd][hr] = {}
    for mm, values in minutes.items():
        aggregated[wd][hr][mm] = {
            "avg": round(mean(values)),
            "min": min(values),
            "max": max(values),
            "count": len(values),
        }
```

### Frontend Implementation (index.html)

#### 1. Data Access Pattern Update

All analytics functions iterate over 3 levels instead of 2:

```javascript
// Before:
for (const [hour, data] of Object.entries(routeData.by_weekday_hour[day])) {
  if (data.avg < bestTime) { ... }
}

// After:
for (const [hour, minutes] of Object.entries(routeData.by_weekday_hour[day])) {
  for (const [minute, data] of Object.entries(minutes)) {
    const timeSlot = `${hour}:${minute}`;  // "08:35"
    if (data.avg < bestTime) {
      bestTime = data.avg;
      bestSlot = timeSlot;
    }
  }
}
```

**Affected functions:**
- `analyzeBestTimes()` → returns `{day: {timeSlot: "08:35", duration: 1820, count: 8}}`
- `analyzeWorstTimes()` → analog
- `compareTodayVsAverage()` → extracts minute from `latest.timestamp_utc`
- `calculateReliability()` → stays hour-level (stdDev over full hour still valid)

#### 2. Heatmap: Sparse Display

**Approach:** Only render time-slots that have data (no empty columns).

```javascript
// Collect all hour:minute combinations with data
const timeSlots = new Set();
for (const day of WEEKDAY_ORDER) {
  for (const [hour, minutes] of Object.entries(routeData.by_weekday_hour[day])) {
    for (const minute of Object.keys(minutes)) {
      timeSlots.add(`${hour}:${minute}`);
    }
  }
}
const sortedSlots = Array.from(timeSlots).sort();  // ["06:05", "06:10", ..., "09:55"]

// Render table: rows = weekdays, cols = sortedSlots
// Cell is colored if data[day][hour][minute] exists, gray otherwise
```

**Result:** ~48 columns (4-hour window × 12 slots/hour) instead of 60 fixed columns.

#### 3. Recommendation Widget

**Output format change:**
```html
<!-- Before -->
<div>Mo: <strong>08 Uhr</strong> (29 min, n=12)</div>

<!-- After -->
<div>Mo: <strong>08:35 Uhr</strong> (28 min, n=8)</div>
```

#### 4. Time-Savings Calculator

**Dropdown enhancement:** Add minute-level selection.

```html
<!-- Option 1: Separate dropdowns -->
<select id="calc-hour-outbound">...</select>
<select id="calc-minute-outbound">
  <!-- Dynamically populated based on selected hour -->
</select>

<!-- Option 2: Combined dropdown (simpler UX) -->
<select id="calc-time-outbound">
  <option value="08:35">08:35</option>
  <option value="08:40">08:40</option>
  <option value="08:45">08:45</option>
</select>
```

**Recommendation:** Option 2 (combined) for simplicity.

## Migration Strategy: Clean Break

**Justification:** Only 6 data points collected so far, no historical data loss concern.

### Deployment Steps

1. Update `build_stats.py` to generate new 3-level structure
2. Run `python scripts/build_stats.py` manually to regenerate `stats.json`
3. Update `index.html` to parse 3-level structure
4. Commit both files together

### Fallback Logic (Optional)

Frontend can detect old format and show warning:

```javascript
function isNewFormat(statsData) {
  const firstRoute = Object.values(statsData.routes)[0];
  const firstDay = Object.values(firstRoute.by_weekday_hour)[0];
  const firstHour = Object.values(firstDay)[0];
  
  // New format: firstHour is object with minute keys
  // Old format: firstHour has {avg, min, max, count}
  return typeof firstHour === 'object' && !('avg' in firstHour);
}

if (!isNewFormat(statsData)) {
  showError('Old data format detected. Please run: python scripts/build_stats.py');
  return;
}
```

**Decision:** Implement this as safety check even though current deployment is clean break.

## Testing Requirements

### Backend Tests (test_build_stats.py)

1. **Minute extraction:** Verify `timestamp_utc` → minute parsing
2. **3-level aggregation:** Fixture with multiple measurements at different minutes
3. **Stats correctness:** avg/min/max/count per minute-bucket
4. **JSON schema:** Validate output structure

### Frontend Tests (Manual)

1. **Data loading:** Verify new format loads without errors
2. **Heatmap rendering:** Check sparse display with sample data
3. **Recommendations:** Verify "08:35" format in output
4. **Time calculator:** Test minute-level selection

### Integration Test

1. Run full pipeline: `fetch_route.py` → CSV → `build_stats.py` → JSON
2. Load `index.html` and verify all 8 analytics features render correctly

## Performance Considerations

### JSON Size Impact

- **Current:** ~2 KB (7 rows × 2 routes × minimal aggregation)
- **Projected (1 month data):** ~150 KB (5 days × 14 hours × 12 minutes × 2 routes × ~20 bytes/bucket)
- **Projected (3 months data):** ~450 KB

**Mitigation:** None needed initially. If size exceeds 1 MB:
- Enable gzip compression on GitHub Pages
- Consider splitting by route (`stats-outbound.json`, `stats-return.json`)

### Frontend Performance

- **Parse time:** Negligible (<50ms for 500 KB JSON)
- **Render time:** Heatmap sparse display keeps DOM nodes reasonable (~300 cells vs. 60 × 60 = 3,600)

## Alternatives Considered

### Option A: 5-Minute Slot Aggregation
- **Structure:** `weekday × hour × 5-min-slot` (e.g., "Monday 08:35")
- **Rejected:** Over-engineered (288 slots/day), slow statistical maturity

### Option C: Quarter-Hour Buckets
- **Structure:** `weekday × hour × quarter` (00-14, 15-29, 30-44, 45-59)
- **Rejected:** Loses precision (15-min windows), not worth the custom logic

## Success Metrics

- [ ] Recommendations show minute-level precision (e.g., "08:35" instead of "08")
- [ ] Heatmap displays sparse time-slots without horizontal overflow
- [ ] Time-savings calculator allows minute-level comparison
- [ ] JSON size stays under 500 KB after 3 months of data collection
- [ ] Page load time stays under 2 seconds on 3G

## Future Enhancements (Out of Scope)

- **Dynamic time windows:** Show only morning/evening slots based on selected route
- **Confidence intervals:** Display error bars when count < threshold
- **Trend detection:** Highlight time-slots with improving/worsening traffic
- **API endpoint:** Replace static JSON with query-based API for filtering
