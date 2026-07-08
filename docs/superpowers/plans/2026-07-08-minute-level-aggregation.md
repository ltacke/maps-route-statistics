# Minute-Level Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade aggregation from hour-level to minute-level buckets for precise departure time recommendations with 5-minute sampling intervals.

**Architecture:** Extend `build_stats.py` to aggregate by weekday → hour → minute (3 levels instead of 2). Update `index.html` analytics functions to iterate over the new structure and display time-slots as "HH:MM" instead of "HH". Use sparse heatmap display for minute-level data visualization.

**Tech Stack:** Python 3.11+, vanilla JavaScript (ES6+), Chart.js, Papa Parse

## Global Constraints

- Python 3.11+ required
- No external dependencies beyond existing `requirements-dev.txt`
- Maintain backward-compatible CLI interface for `build_stats.py`
- JSON output must be valid UTF-8
- Frontend must work without build step (static HTML)
- All timestamps use ISO 8601 format with UTC timezone

---

## File Structure

**Modified files:**
- `scripts/build_stats.py` — Add minute-level aggregation logic
- `tests/test_build_stats.py` — Add tests for 3-level structure
- `index.html` — Update all analytics functions for minute-level data
- `data/stats.json` — Regenerated output (not version-controlled change)

**No new files created** — this is a refactor of existing aggregation.

---

### Task 1: Backend - Minute Extraction and 3-Level Aggregation

**Files:**
- Modify: `scripts/build_stats.py:29-64`
- Test: `tests/test_build_stats.py`

**Interfaces:**
- Consumes: CSV rows with `timestamp_utc` (ISO 8601 string)
- Produces: JSON structure `routes[route_id].by_weekday_hour[weekday][hour][minute] = {avg, min, max, count}`

- [ ] **Step 1: Write failing test for minute extraction**

```python
# Add to tests/test_build_stats.py

def test_minute_level_aggregation(tmp_path):
    """Verify 3-level aggregation: weekday -> hour -> minute."""
    csv_path = tmp_path / "route_history.csv"
    json_path = tmp_path / "stats.json"
    
    write_csv(csv_path, [
        {
            "route_id": "test", 
            "timestamp_utc": "2025-01-13T07:35:00+00:00",
            "weekday_local": "Monday", 
            "hour_local": "08",
            "origin_lat": 0, "origin_lng": 0, 
            "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 1800, 
            "static_duration_seconds": 1700,
            "travel_mode": "DRIVE", 
            "source": "google_routes_api",
        },
        {
            "route_id": "test", 
            "timestamp_utc": "2025-01-13T07:40:00+00:00",
            "weekday_local": "Monday", 
            "hour_local": "08",
            "origin_lat": 0, "origin_lng": 0, 
            "destination_lat": 0, "destination_lng": 0,
            "duration_seconds": 1900, 
            "static_duration_seconds": 1700,
            "travel_mode": "DRIVE", 
            "source": "google_routes_api",
        },
    ])
    
    from build_stats import build
    build(csv_path=csv_path, json_path=json_path)
    
    result = json.loads(json_path.read_text())
    monday_08 = result["routes"]["test"]["by_weekday_hour"]["Monday"]["08"]
    
    # Should have two separate minute buckets
    assert "35" in monday_08
    assert "40" in monday_08
    assert monday_08["35"]["avg"] == 1800
    assert monday_08["35"]["count"] == 1
    assert monday_08["40"]["avg"] == 1900
    assert monday_08["40"]["count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_build_stats.py::test_minute_level_aggregation -v`

Expected: FAIL with KeyError or assertion error (old structure has no minute level)

- [ ] **Step 3: Update build_stats.py to use 3-level aggregation**

Replace lines 29-64 in `scripts/build_stats.py`:

```python
def build(
    csv_path: Path = _DEFAULT_CSV,
    json_path: Path = _DEFAULT_JSON,
) -> None:
    """Liest csv_path und schreibt aggregierte stats nach json_path (atomar)."""
    routes: dict = collections.defaultdict(list)

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            route_id = row["route_id"]
            routes[route_id].append(row)

    output: dict = {
        "last_updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "routes": {},
    }

    for route_id, rows in routes.items():
        # Neuester Eintrag
        latest_row = max(rows, key=lambda r: dt.datetime.fromisoformat(r["timestamp_utc"]))

        # Aggregation pro Wochentag × Stunde × Minute
        by_weekday_hour_minute: dict = {}
        for row in rows:
            ts = dt.datetime.fromisoformat(row["timestamp_utc"])
            wd = ts.strftime("%A")  # "Monday"
            hr = str(ts.hour).zfill(2)  # "08"
            mm = str(ts.minute).zfill(2)  # "35"
            val = int(row["duration_seconds"])
            
            by_weekday_hour_minute.setdefault(wd, {}).setdefault(hr, {}).setdefault(mm, []).append(val)

        aggregated: dict = {}
        for wd, hours in by_weekday_hour_minute.items():
            aggregated[wd] = {}
            for hr, minutes in hours.items():
                aggregated[wd][hr] = {}
                for mm, values in minutes.items():
                    aggregated[wd][hr][mm] = {
                        "avg": round(mean(values)),
                        "min": min(values),
                        "max": max(values),
                        "count": len(values),
                    }

        output["routes"][route_id] = {
            "latest": {
                "timestamp_utc": latest_row["timestamp_utc"],
                "duration_seconds": int(latest_row["duration_seconds"]),
                "static_duration_seconds": int(latest_row["static_duration_seconds"]),
                "origin_lat": float(latest_row["origin_lat"]),
                "origin_lng": float(latest_row["origin_lng"]),
                "destination_lat": float(latest_row["destination_lat"]),
                "destination_lng": float(latest_row["destination_lng"]),
            },
            "by_weekday_hour": aggregated,
        }

    # Atomar schreiben: erst Temp-Datei, dann rename
    json_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=json_path.parent, suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        Path(tmp_path).replace(json_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_build_stats.py::test_minute_level_aggregation -v`

Expected: PASS

- [ ] **Step 5: Verify existing tests still pass**

Run: `pytest tests/test_build_stats.py -v`

Expected: All tests PASS (existing tests need updates for 3-level structure)

- [ ] **Step 6: Fix existing tests for 3-level structure**

Update line 64 in `tests/test_build_stats.py`:

```python
# Old:
assert route["by_weekday_hour"]["Monday"]["08"]["avg"] == 4500

# New (extract minute from timestamp):
assert route["by_weekday_hour"]["Monday"]["08"]["00"]["avg"] == 4500
```

Update line 94 in `tests/test_build_stats.py`:

```python
# Old:
cell = result["routes"]["r1"]["by_weekday_hour"]["Monday"]["08"]

# New:
cell = result["routes"]["r1"]["by_weekday_hour"]["Monday"]["08"]["00"]
```

Note: Both test fixtures use timestamps with minute=00, so access `["00"]` bucket.

- [ ] **Step 7: Run all tests again**

Run: `pytest tests/test_build_stats.py -v`

Expected: All tests PASS

- [ ] **Step 8: Regenerate stats.json with new structure**

Run: `python scripts/build_stats.py`

Expected: Output "stats.json aktualisiert."

Verify: `cat data/stats.json | jq '.routes.outbound.by_weekday_hour'` shows 3-level structure

- [ ] **Step 9: Commit backend changes**

```bash
git add scripts/build_stats.py tests/test_build_stats.py data/stats.json
git commit -m "feat: add minute-level aggregation to build_stats.py

- Aggregate by weekday -> hour -> minute (3 levels)
- Extract minute from timestamp_utc
- Update tests for new structure
- Regenerate stats.json with minute buckets"
```

---

### Task 2: Frontend - Update Analytics Functions for 3-Level Data

**Files:**
- Modify: `index.html:387-485` (analytics functions)

**Interfaces:**
- Consumes: `statsData.routes[routeId].by_weekday_hour[weekday][hour][minute] = {avg, min, max, count}`
- Produces: Functions return time-slots as "HH:MM" strings instead of "HH"

- [ ] **Step 1: Update analyzeBestTimes() for minute-level iteration**

Replace lines 387-407 in `index.html`:

```javascript
function analyzeBestTimes(routeData, routeId) {
  // Findet die beste Zeit pro Wochentag (nur relevante Stunden)
  const recommendations = {};
  for (const day of WEEKDAY_ORDER) {
    if (!routeData.by_weekday_hour[day]) continue;
    let bestSlot = null;
    let bestTime = Infinity;
    let bestCount = 0;
    
    for (const [hour, minutes] of Object.entries(routeData.by_weekday_hour[day])) {
      // Nur relevante Stunden berücksichtigen
      if (!isRelevantHour(hour, routeId)) continue;
      
      for (const [minute, data] of Object.entries(minutes)) {
        const timeSlot = `${hour}:${minute}`;
        if (data.avg < bestTime) {
          bestTime = data.avg;
          bestSlot = timeSlot;
          bestCount = data.count;
        }
      }
    }
    
    if (bestSlot) {
      recommendations[day] = { 
        timeSlot: bestSlot,  // "08:35"
        duration: bestTime, 
        count: bestCount 
      };
    }
  }
  return recommendations;
}
```

- [ ] **Step 2: Update analyzeWorstTimes() for minute-level iteration**

Replace lines 409-428 in `index.html`:

```javascript
function analyzeWorstTimes(routeData, routeId) {
  const worst = {};
  for (const day of WEEKDAY_ORDER) {
    if (!routeData.by_weekday_hour[day]) continue;
    let worstSlot = null;
    let worstTime = -Infinity;
    
    for (const [hour, minutes] of Object.entries(routeData.by_weekday_hour[day])) {
      // Nur relevante Stunden berücksichtigen
      if (!isRelevantHour(hour, routeId)) continue;
      
      for (const [minute, data] of Object.entries(minutes)) {
        const timeSlot = `${hour}:${minute}`;
        if (data.avg > worstTime) {
          worstTime = data.avg;
          worstSlot = timeSlot;
        }
      }
    }
    
    if (worstSlot) {
      worst[day] = { timeSlot: worstSlot, duration: worstTime };
    }
  }
  return worst;
}
```

- [ ] **Step 3: Update compareTodayVsAverage() to extract minute from timestamp**

Replace lines 477-485 in `index.html`:

```javascript
function compareTodayVsAverage(latest, byWeekdayHour) {
  if (!latest) return null;
  const ts = new Date(latest.timestamp_utc);
  const day = ts.toLocaleDateString('en-US', { weekday: 'long' });
  const hour = String(ts.getHours()).padStart(2, '0');
  const minute = String(ts.getMinutes()).padStart(2, '0');

  const avgData = byWeekdayHour[day]?.[hour]?.[minute];
  if (!avgData) return null;

  return {
    current: latest.duration_seconds,
    average: avgData.avg,
    diff: latest.duration_seconds - avgData.avg,
    count: avgData.count,
  };
}
```

- [ ] **Step 4: Test in browser - load index.html**

Run: `python -m http.server 8080`

Open: http://localhost:8080

Expected: Page loads without JavaScript errors (check browser console)

- [ ] **Step 5: Commit analytics function updates**

```bash
git add index.html
git commit -m "feat: update analytics functions for minute-level data

- analyzeBestTimes returns timeSlot as HH:MM
- analyzeWorstTimes returns timeSlot as HH:MM
- compareTodayVsAverage extracts minute from timestamp
- 3-level iteration over weekday/hour/minute"
```

---

### Task 3: Frontend - Update Recommendation & Ranking Display

**Files:**
- Modify: `index.html:600-700` (approximate range for rendering functions)

**Interfaces:**
- Consumes: `recommendations[day].timeSlot` as "HH:MM" string
- Produces: HTML displaying "08:35 Uhr" instead of "08 Uhr"

- [ ] **Step 1: Find and update recommendation rendering code**

Search for text "Uhr" in `index.html` to locate display logic:

Run: `grep -n "Uhr" index.html`

Identify lines that format hour-only output (likely around line 600-650).

- [ ] **Step 2: Update recommendation widget HTML generation**

Find the code block that generates recommendation HTML (search for "recommendations-outbound"):

Replace the rendering loop to use `timeSlot` instead of `hour`:

```javascript
// Old pattern (example):
html += `<div>${WEEKDAY_DE[day]}: <strong>${rec.hour} Uhr</strong> (${secToMin(rec.duration)} min, n=${rec.count})</div>`;

// New pattern:
html += `<div>${WEEKDAY_DE[day]}: <strong>${rec.timeSlot} Uhr</strong> (${secToMin(rec.duration)} min, n=${rec.count})</div>`;
```

Note: Exact line numbers depend on current file structure. Search for `recommendations-outbound` and `recommendations-return` to find rendering code.

- [ ] **Step 3: Update ranking (best/worst times) display**

Find the code block for `ranking-outbound` and `ranking-return`:

```javascript
// Old pattern (example):
html += `<div>🏆 ${WEEKDAY_DE[day]} ${time.hour} Uhr: ${secToMin(time.duration)} min</div>`;

// New pattern:
html += `<div>🏆 ${WEEKDAY_DE[day]} ${time.timeSlot} Uhr: ${secToMin(time.duration)} min</div>`;
```

- [ ] **Step 4: Test in browser - verify display changes**

Run: `python -m http.server 8080`

Open: http://localhost:8080

Expected: 
- Recommendation widget shows "Mo: 08:35 Uhr" (not "Mo: 08 Uhr")
- Ranking shows "🏆 Mo 08:35 Uhr" format

- [ ] **Step 5: Commit display updates**

```bash
git add index.html
git commit -m "feat: display time recommendations as HH:MM format

- Recommendation widget shows 08:35 Uhr
- Best/worst rankings show minute-level precision
- Updated all Uhr-formatted outputs"
```

---

### Task 4: Frontend - Sparse Heatmap Rendering

**Files:**
- Modify: `index.html:700-900` (heatmap rendering section)

**Interfaces:**
- Consumes: `routeData.by_weekday_hour[weekday][hour][minute]`
- Produces: HTML table with sparse columns (only time-slots with data)

- [ ] **Step 1: Find heatmap rendering code**

Search for "heatmap-container" in `index.html`:

Run: `grep -n "heatmap-container" index.html`

Identify the function that builds the heatmap table (likely a `renderHeatmap()` or inline code).

- [ ] **Step 2: Write new sparse heatmap rendering function**

Add before the existing heatmap code:

```javascript
function renderSparseHeatmap(routeData, containerId) {
  // Collect all time-slots with data
  const timeSlots = new Set();
  for (const day of WEEKDAY_ORDER) {
    if (!routeData.by_weekday_hour[day]) continue;
    for (const [hour, minutes] of Object.entries(routeData.by_weekday_hour[day])) {
      for (const minute of Object.keys(minutes)) {
        timeSlots.add(`${hour}:${minute}`);
      }
    }
  }
  
  const sortedSlots = Array.from(timeSlots).sort();
  
  if (sortedSlots.length === 0) {
    document.getElementById(containerId).innerHTML = 
      '<p style="color:#57606a;font-size:13px">Noch keine Aggregationsdaten vorhanden.</p>';
    return;
  }
  
  // Find min/max for color scaling
  let minVal = Infinity, maxVal = -Infinity;
  for (const day of WEEKDAY_ORDER) {
    if (!routeData.by_weekday_hour[day]) continue;
    for (const [hour, minutes] of Object.entries(routeData.by_weekday_hour[day])) {
      for (const data of Object.values(minutes)) {
        if (data.avg < minVal) minVal = data.avg;
        if (data.avg > maxVal) maxVal = data.avg;
      }
    }
  }
  
  // Build table
  let html = '<table class="heatmap"><thead><tr><th>Tag</th>';
  sortedSlots.forEach(slot => {
    html += `<th>${slot}</th>`;
  });
  html += '</tr></thead><tbody>';
  
  for (const day of WEEKDAY_ORDER) {
    html += `<tr><th>${WEEKDAY_DE[day]}</th>`;
    for (const slot of sortedSlots) {
      const [hour, minute] = slot.split(':');
      const data = routeData.by_weekday_hour[day]?.[hour]?.[minute];
      
      if (data) {
        const color = heatColor(data.avg, minVal, maxVal);
        const minutes = secToMin(data.avg);
        html += `<td style="background-color:${color}" title="${minutes} min (n=${data.count})">${minutes}</td>`;
      } else {
        html += '<td style="background-color:#e5e7eb"></td>';
      }
    }
    html += '</tr>';
  }
  
  html += '</tbody></table>';
  document.getElementById(containerId).innerHTML = html;
}
```

- [ ] **Step 3: Replace heatmap rendering calls**

Find where heatmap is rendered (search for "heatmap-container-outbound"):

```javascript
// Old call (example):
renderHeatmap(statsData.routes.outbound, 'heatmap-container-outbound');

// New call:
renderSparseHeatmap(statsData.routes.outbound, 'heatmap-container-outbound');
renderSparseHeatmap(statsData.routes.return, 'heatmap-container-return');
```

- [ ] **Step 4: Test in browser - verify sparse heatmap**

Run: `python -m http.server 8080`

Open: http://localhost:8080

Expected:
- Heatmap shows only columns with data (e.g., "06:05", "06:10", "06:15")
- No empty columns
- Table is scrollable horizontally if needed
- Hovering shows tooltip with minute-level stats

- [ ] **Step 5: Commit heatmap changes**

```bash
git add index.html
git commit -m "feat: implement sparse heatmap for minute-level data

- renderSparseHeatmap() shows only time-slots with data
- Columns display as HH:MM format
- Auto-scales color range per route
- Horizontal scroll for wide tables"
```

---

### Task 5: Frontend - Update Time-Savings Calculator

**Files:**
- Modify: `index.html:180-227` (calculator UI and logic)

**Interfaces:**
- Consumes: `routeData.by_weekday_hour[weekday][hour][minute]`
- Produces: Combined dropdown with "HH:MM" options

- [ ] **Step 1: Update calculator dropdown population**

Find the dropdown population code (search for "calc-hour-outbound"):

Replace hour-only dropdown with combined time-slot dropdown:

```javascript
// Old: Separate hour and minute dropdowns (if exists)
// New: Single combined dropdown

function populateTimeSlotDropdown(selectId, routeData) {
  const select = document.getElementById(selectId);
  select.innerHTML = '';
  
  const timeSlots = new Set();
  for (const day of WEEKDAY_ORDER) {
    if (!routeData.by_weekday_hour[day]) continue;
    for (const [hour, minutes] of Object.entries(routeData.by_weekday_hour[day])) {
      for (const minute of Object.keys(minutes)) {
        timeSlots.add(`${hour}:${minute}`);
      }
    }
  }
  
  Array.from(timeSlots).sort().forEach(slot => {
    const option = document.createElement('option');
    option.value = slot;
    option.textContent = slot;
    select.appendChild(option);
  });
}

// Call after data loads:
populateTimeSlotDropdown('calc-time-outbound', statsData.routes.outbound);
populateTimeSlotDropdown('calc-time-return', statsData.routes.return);
```

- [ ] **Step 2: Update calculator HTML structure**

Replace lines 180-227 in `index.html` (calculator section):

```html
<!-- Replace separate hour/minute dropdowns with single time dropdown -->
<div>
  <label style="font-size:12px;color:#57606a;display:block;margin-bottom:4px">Wochentag</label>
  <select id="calc-day-outbound" style="width:100%;padding:6px;border:1px solid #e5e7eb;border-radius:4px;font-size:13px">
    <option value="Monday">Montag</option>
    <option value="Tuesday">Dienstag</option>
    <option value="Wednesday">Mittwoch</option>
    <option value="Thursday">Donnerstag</option>
    <option value="Friday">Freitag</option>
  </select>
</div>
<div>
  <label style="font-size:12px;color:#57606a;display:block;margin-bottom:4px">Uhrzeit</label>
  <select id="calc-time-outbound" style="width:100%;padding:6px;border:1px solid #e5e7eb;border-radius:4px;font-size:13px">
    <!-- Dynamically populated -->
  </select>
</div>
```

Repeat for return direction (`calc-day-return`, `calc-time-return`).

- [ ] **Step 3: Update calculateSavings() function**

Find `calculateSavings()` function and update to use combined time-slot:

```javascript
function calculateSavings(routeId) {
  const day = document.getElementById(`calc-day-${routeId}`).value;
  const timeSlot = document.getElementById(`calc-time-${routeId}`).value;
  const resultDiv = document.getElementById(`calc-result-${routeId}`);
  
  const routeData = statsData.routes[routeId];
  const [hour, minute] = timeSlot.split(':');
  const selectedData = routeData.by_weekday_hour[day]?.[hour]?.[minute];
  
  if (!selectedData) {
    resultDiv.innerHTML = '<p style="color:#dc2626">Keine Daten für diese Zeit verfügbar.</p>';
    return;
  }
  
  // Find best time for comparison
  const recommendations = analyzeBestTimes(routeData, routeId);
  const bestForDay = recommendations[day];
  
  if (!bestForDay) {
    resultDiv.innerHTML = '<p style="color:#dc2626">Keine Vergleichsdaten verfügbar.</p>';
    return;
  }
  
  const selectedDuration = selectedData.avg;
  const bestDuration = bestForDay.duration;
  const savings = selectedDuration - bestDuration;
  const savingsMin = secToMin(Math.abs(savings));
  
  let html = `<p><strong>${timeSlot} Uhr:</strong> ${secToMin(selectedDuration)} min</p>`;
  html += `<p><strong>Optimal (${bestForDay.timeSlot} Uhr):</strong> ${secToMin(bestDuration)} min</p>`;
  
  if (savings > 0) {
    html += `<p style="color:#16a34a"><strong>Zeitersparnis:</strong> ${savingsMin} min früher abfahren!</p>`;
  } else if (savings < 0) {
    html += `<p style="color:#d97706"><strong>Zeitverlust:</strong> ${savingsMin} min länger als optimal</p>`;
  } else {
    html += `<p style="color:#16a34a"><strong>Optimal!</strong> Du fährst zur besten Zeit.</p>`;
  }
  
  resultDiv.innerHTML = html;
}
```

- [ ] **Step 4: Test calculator in browser**

Run: `python -m http.server 8080`

Open: http://localhost:8080

Expected:
- Time dropdown shows "08:35", "08:40", "08:45" etc.
- Calculation compares selected time vs. optimal time
- Shows minute-level precision in output

- [ ] **Step 5: Commit calculator updates**

```bash
git add index.html
git commit -m "feat: upgrade time-savings calculator to minute-level

- Combined time dropdown with HH:MM format
- Compare selected vs optimal time-slot
- Display minute-level precision in results"
```

---

### Task 6: Frontend - Format Detection and Error Handling

**Files:**
- Modify: `index.html` (data loading section)

**Interfaces:**
- Consumes: `statsData.routes[routeId].by_weekday_hour`
- Produces: Error message if old format detected

- [ ] **Step 1: Add format detection function**

Add near the top of the script section (after `statsData` declaration):

```javascript
function isNewFormat(statsData) {
  if (!statsData.routes || Object.keys(statsData.routes).length === 0) {
    return true;  // Empty data is valid new format
  }
  
  const firstRoute = Object.values(statsData.routes)[0];
  if (!firstRoute.by_weekday_hour) return true;
  
  const firstDay = Object.values(firstRoute.by_weekday_hour)[0];
  if (!firstDay) return true;
  
  const firstHour = Object.values(firstDay)[0];
  if (!firstHour) return true;
  
  // New format: firstHour is object with minute keys (no 'avg' property)
  // Old format: firstHour has {avg, min, max, count}
  return typeof firstHour === 'object' && !('avg' in firstHour);
}
```

- [ ] **Step 2: Add error display on format mismatch**

Find the data loading section (search for `fetch('data/stats.json')`):

Add format check after data loads:

```javascript
fetch('data/stats.json')
  .then(r => r.json())
  .then(data => {
    if (!isNewFormat(data)) {
      document.getElementById('loading').style.display = 'none';
      document.getElementById('error').textContent = 
        'Alte Datenstruktur erkannt. Bitte führe aus: python scripts/build_stats.py';
      document.getElementById('error').style.display = 'block';
      return;
    }
    
    statsData = data;
    // ... rest of loading logic
  });
```

- [ ] **Step 3: Test error handling with old format**

Create temporary old-format JSON:

```bash
cat > data/stats-old.json << 'EOF'
{
  "last_updated": "2026-07-08T10:00:00+00:00",
  "routes": {
    "test": {
      "by_weekday_hour": {
        "Monday": {
          "08": {"avg": 1800, "min": 1700, "max": 1900, "count": 5}
        }
      }
    }
  }
}
EOF
```

Temporarily modify `index.html` to load `stats-old.json`:

Expected: Error message displays: "Alte Datenstruktur erkannt. Bitte führe aus: python scripts/build_stats.py"

- [ ] **Step 4: Restore normal loading and clean up**

```bash
rm data/stats-old.json
```

Restore `index.html` to load `data/stats.json`.

- [ ] **Step 5: Commit error handling**

```bash
git add index.html
git commit -m "feat: add format detection and error handling

- isNewFormat() detects old 2-level structure
- Show error message if old format detected
- Prevent rendering with incompatible data"
```

---

### Task 7: Integration Test and Documentation

**Files:**
- Modify: `CLAUDE.md` (update architecture description)
- Test: Full pipeline end-to-end

**Interfaces:**
- Validates: Complete data flow from CSV → JSON → rendered HTML

- [ ] **Step 1: Run full pipeline test**

```bash
# Generate fresh data
python scripts/build_stats.py

# Verify JSON structure
cat data/stats.json | jq '.routes.outbound.by_weekday_hour' | head -30
```

Expected: 3-level structure visible (weekday → hour → minute → stats)

- [ ] **Step 2: Manual frontend test checklist**

Run: `python -m http.server 8080`

Open: http://localhost:8080

Test each feature:
- [ ] Recommendation widget shows "HH:MM Uhr" format
- [ ] Best/Worst rankings show minute-level precision
- [ ] "Heute vs. Durchschnitt" section works (if data available)
- [ ] Heatmap displays sparse columns (only slots with data)
- [ ] Time-savings calculator has "HH:MM" dropdowns
- [ ] Calculator shows minute-level comparison
- [ ] No JavaScript errors in console

- [ ] **Step 3: Run backend test suite**

```bash
pytest tests/test_build_stats.py -v
```

Expected: All tests PASS

- [ ] **Step 4: Update CLAUDE.md with new aggregation details**

Replace the "Stats Rebuild Trigger" section around line 80:

```markdown
### Stats Aggregation

`build_stats.py` aggregates by `weekday × hour × minute` (3 levels):
- Extracts minute from `timestamp_utc` (ISO 8601)
- Groups measurements by route_id → weekday → hour → minute
- Outputs JSON: `stats.routes[id].by_weekday_hour[day][hour][minute] = {avg, min, max, count}`

**Why minute-level?** With 5-minute sampling intervals, hour-level buckets lose precision. 
Early-hour measurements (08:05) and late-hour (08:55) differ significantly but landed in 
the same "08" bucket. Minute-level enables precise recommendations like "leave at 08:35".

**Sparse representation:** Frontend displays only time-slots with data (no empty columns).

### Stats Rebuild Trigger

`fetch_route.py` calls `build_stats()` after every successful fetch. This keeps `stats.json` 
always in sync with the CSV, avoiding manual rebuild steps.
```

- [ ] **Step 5: Final commit and cleanup**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for minute-level aggregation

- Document 3-level aggregation structure
- Explain rationale for minute-level buckets
- Add sparse representation note"
```

- [ ] **Step 6: Verify git log**

```bash
git log --oneline -10
```

Expected: 7 commits for this feature (1 per task)

---

## Self-Review Checklist

**Spec coverage:**
- [x] Backend minute extraction (Task 1)
- [x] 3-level aggregation logic (Task 1)
- [x] Analytics functions updated (Task 2)
- [x] Display format "HH:MM Uhr" (Task 3)
- [x] Sparse heatmap rendering (Task 4)
- [x] Time-savings calculator upgrade (Task 5)
- [x] Format detection and error handling (Task 6)
- [x] Integration test and docs (Task 7)

**Placeholder scan:**
- No "TBD" or "TODO" in plan
- All code blocks complete
- All function signatures specified

**Type consistency:**
- `timeSlot` used consistently as "HH:MM" string
- `by_weekday_hour` key name preserved (3-level structure)
- All timestamps remain ISO 8601 format

**Task boundaries:**
- Each task has independent test cycle
- Commits are atomic and describe deliverable
- No cross-task dependencies that break isolation
