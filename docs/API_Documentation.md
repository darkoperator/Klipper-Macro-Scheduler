# Macro Scheduler API Reference

This document describes the REST API endpoints exposed by the Macro Scheduler Moonraker component.

**Base URL:** `http://your-printer-ip:7125`

All endpoints return JSON responses in the Moonraker standard format:
```json
{
  "result": { ... }
}
```

Errors return:
```json
{
  "error": {
    "code": 400,
    "message": "Error description"
  }
}
```

---

## Endpoints Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/server/macro_scheduler/schedules` | List all schedules |
| POST | `/server/macro_scheduler/add` | Create a new schedule |
| POST | `/server/macro_scheduler/delete` | Delete a schedule |
| POST | `/server/macro_scheduler/toggle` | Enable/disable a schedule |
| GET | `/server/macro_scheduler/list_text` | Get text format for display |

---

## List Schedules

Get all configured schedules.

**Endpoint:** `GET /server/macro_scheduler/schedules`

**Parameters:** None

**Response:**
```json
{
  "result": {
    "schedules": [
      {
        "id": 1,
        "name": "Morning Preheat",
        "macro": "PREHEAT_BED",
        "schedule_type": "daily",
        "params": {
          "TEMP": 60
        },
        "enabled": true,
        "time": "07:00",
        "next_run": "2025-10-13T07:00:00"
      }
    ]
  }
}
```

**Schedule Object Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique schedule identifier |
| `name` | string | User-friendly schedule name |
| `macro` | string | Klipper macro to execute |
| `schedule_type` | string | Type: `once`, `daily`, `weekly`, `interval`, `cron` |
| `params` | object | Parameters to pass to macro |
| `enabled` | boolean | Whether schedule is active |
| `next_run` | string | ISO 8601 datetime of next execution |

**Type-Specific Fields:**

- **once:** `datetime` (ISO 8601 string)
- **daily:** `time` (HH:MM format)
- **weekly:** `time` (HH:MM), `days` (array of integers 0-6)
- **interval:** `interval_minutes` (integer)
- **cron:** `cron_expression` (string)

**Example Request:**
```bash
curl http://localhost:7125/server/macro_scheduler/schedules
```

**Example Response:**
```json
{
  "result": {
    "schedules": [
      {
        "id": 1,
        "name": "Morning Preheat",
        "macro": "PREHEAT_BED",
        "schedule_type": "daily",
        "params": {"TEMP": 60},
        "enabled": true,
        "time": "07:00",
        "next_run": "2025-10-13T07:00:00"
      },
      {
        "id": 2,
        "name": "Status Check",
        "macro": "STATUS_REPORT",
        "schedule_type": "interval",
        "params": {},
        "enabled": true,
        "interval_minutes": 60,
        "next_run": "2025-10-13T08:30:00"
      },
      {
        "id": 3,
        "name": "Weekly Maintenance",
        "macro": "MAINTENANCE_REMINDER",
        "schedule_type": "weekly",
        "params": {},
        "enabled": true,
        "time": "10:00",
        "days": [5, 6],
        "next_run": "2025-10-13T10:00:00"
      }
    ]
  }
}
```

---

## Add Schedule

Create a new schedule.

**Endpoint:** `POST /server/macro_scheduler/add`

**Content-Type:** `application/json`

**Common Request Body:**
```json
{
  "name": "Schedule Name",
  "macro": "MACRO_NAME",
  "schedule_type": "once|daily|weekly|interval|cron",
  "params": {}
}
```

### Schedule Type: Once

Execute one time at a specific date/time.

**Additional Fields:**
```json
{
  "datetime": "2025-10-13T14:30:00"
}
```

**Complete Example:**
```json
{
  "name": "Afternoon Print",
  "macro": "START_PRINT",
  "schedule_type": "once",
  "datetime": "2025-10-13T14:30:00",
  "params": {
    "FILE": "test_cube.gcode"
  }
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:7125/server/macro_scheduler/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Afternoon Print",
    "macro": "START_PRINT",
    "schedule_type": "once",
    "datetime": "2025-10-13T14:30:00",
    "params": {"FILE": "test.gcode"}
  }'
```

### Schedule Type: Daily

Execute every day at a specific time.

**Additional Fields:**
```json
{
  "time": "07:00"
}
```

**Complete Example:**
```json
{
  "name": "Morning Preheat",
  "macro": "PREHEAT_BED",
  "schedule_type": "daily",
  "time": "07:00",
  "params": {
    "TEMP": 60
  }
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:7125/server/macro_scheduler/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Morning Preheat",
    "macro": "PREHEAT_BED",
    "schedule_type": "daily",
    "time": "07:00",
    "params": {"TEMP": 60}
  }'
```

### Schedule Type: Weekly

Execute on specific days of the week at a specific time.

**Additional Fields:**
```json
{
  "time": "09:00",
  "days": [0, 1, 2, 3, 4]
}
```

**Day Values:**
- 0 = Monday
- 1 = Tuesday
- 2 = Wednesday
- 3 = Thursday
- 4 = Friday
- 5 = Saturday
- 6 = Sunday

**Complete Example:**
```json
{
  "name": "Weekday Maintenance",
  "macro": "RUN_MAINTENANCE",
  "schedule_type": "weekly",
  "time": "09:00",
  "days": [0, 1, 2, 3, 4],
  "params": {}
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:7125/server/macro_scheduler/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Weekend Check",
    "macro": "WEEKEND_STATUS",
    "schedule_type": "weekly",
    "time": "10:00",
    "days": [5, 6],
    "params": {}
  }'
```

### Schedule Type: Interval

Execute repeatedly at fixed intervals (in minutes).

**Additional Fields:**
```json
{
  "interval_minutes": 60
}
```

**Complete Example:**
```json
{
  "name": "Hourly Status",
  "macro": "STATUS_CHECK",
  "schedule_type": "interval",
  "interval_minutes": 60,
  "params": {}
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:7125/server/macro_scheduler/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Every 3 Hours",
    "macro": "PERIODIC_CHECK",
    "schedule_type": "interval",
    "interval_minutes": 180,
    "params": {}
  }'
```

**Note:** Interval schedules execute immediately upon creation, then repeat at the specified interval.

### Schedule Type: Cron

Execute based on cron expression.

**Additional Fields:**
```json
{
  "cron_expression": "0 9 * * 1"
}
```

**Cron Format:** `minute hour day month weekday`

**Complete Example:**
```json
{
  "name": "Monday Morning",
  "macro": "WEEKLY_REPORT",
  "schedule_type": "cron",
  "cron_expression": "0 9 * * 1",
  "params": {}
}
```

**Common Cron Expressions:**

| Expression | Description |
|------------|-------------|
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `30 14 * * 1,3,5` | Mon, Wed, Fri at 2:30 PM |
| `0 */3 * * *` | Every 3 hours |
| `0 0 * * *` | Daily at midnight |
| `15 8 1 * *` | 1st of month at 8:15 AM |

**cURL Example:**
```bash
curl -X POST http://localhost:7125/server/macro_scheduler/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Every Monday",
    "macro": "MONDAY_ROUTINE",
    "schedule_type": "cron",
    "cron_expression": "0 9 * * 1",
    "params": {}
  }'
```

**Success Response:**
```json
{
  "result": {
    "schedule": {
      "id": 4,
      "name": "Morning Preheat",
      "macro": "PREHEAT_BED",
      "schedule_type": "daily",
      "params": {"TEMP": 60},
      "enabled": true,
      "time": "07:00",
      "next_run": "2025-10-13T07:00:00"
    }
  }
}
```

**Error Response:**
```json
{
  "error": {
    "code": 400,
    "message": "Invalid schedule type"
  }
}
```

---

## Delete Schedule

Delete an existing schedule.

**Endpoint:** `POST /server/macro_scheduler/delete`

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "id": 1
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | integer | Yes | Schedule ID to delete |

**Example Request:**
```bash
curl -X POST http://localhost:7125/server/macro_scheduler/delete \
  -H "Content-Type: application/json" \
  -d '{"id": 1}'
```

**Success Response:**
```json
{
  "result": {
    "deleted": 1
  }
}
```

**Error Response (Not Found):**
```json
{
  "error": {
    "code": 404,
    "message": "Schedule 1 not found"
  }
}
```

---

## Toggle Schedule

Enable or disable a schedule without deleting it.

**Endpoint:** `POST /server/macro_scheduler/toggle`

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "id": 1
}
```

**Parameters:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | integer | Yes | Schedule ID to toggle |

**Example Request:**
```bash
curl -X POST http://localhost:7125/server/macro_scheduler/toggle \
  -H "Content-Type: application/json" \
  -d '{"id": 1}'
```

**Success Response:**
```json
{
  "result": {
    "schedule": {
      "id": 1,
      "name": "Morning Preheat",
      "macro": "PREHEAT_BED",
      "schedule_type": "daily",
      "params": {"TEMP": 60},
      "enabled": false,
      "time": "07:00",
      "next_run": "2025-10-13T07:00:00"
    }
  }
}
```

**Note:** The `enabled` field will be toggled. If it was `true`, it becomes `false`, and vice versa.

**Error Response (Not Found):**
```json
{
  "error": {
    "code": 404,
    "message": "Schedule 1 not found"
  }
}
```

---

## List Text Format

Get schedules in human-readable text format (useful for displaying in Klipper macros or console).

**Endpoint:** `GET /server/macro_scheduler/list_text`

**Parameters:** None

**Response:**
```json
{
  "result": {
    "text": "=== Scheduled Macros ===\n\n[1] Morning Preheat\n    Macro: PREHEAT_BED\n    Type: DAILY\n    Status: ✓ ACTIVE\n    Next run: 2025-10-13T07:00:00\n\n[2] Status Check\n    Macro: STATUS_CHECK\n    Type: INTERVAL\n    Status: ✓ ACTIVE\n    Next run: 2025-10-13T08:30:00\n\nTotal: 2/2 active"
  }
}
```

**Example Request:**
```bash
curl http://localhost:7125/server/macro_scheduler/list_text
```

**Use Case:**

This endpoint is designed for use with shell commands in Klipper macros:

```ini
[gcode_shell_command get_schedules]
command: curl -s http://localhost:7125/server/macro_scheduler/list_text | grep -o '"text":"[^"]*"' | cut -d'"' -f4 | sed 's/\\n/\n/g'
timeout: 5.0
verbose: True

[gcode_macro LIST_SCHEDULES]
description: Display all scheduled macros
gcode:
    RUN_SHELL_COMMAND CMD=get_schedules
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 400 | Bad Request - Invalid parameters or malformed JSON |
| 404 | Not Found - Schedule ID doesn't exist |
| 500 | Internal Server Error - Component error |

---

## Python Examples

### Using `requests` library:

```python
import requests

BASE_URL = "http://localhost:7125"

# List schedules
response = requests.get(f"{BASE_URL}/server/macro_scheduler/schedules")
schedules = response.json()["result"]["schedules"]
print(f"Found {len(schedules)} schedules")

# Add schedule
new_schedule = {
    "name": "Test Schedule",
    "macro": "TEST_MACRO",
    "schedule_type": "daily",
    "time": "10:00",
    "params": {}
}
response = requests.post(
    f"{BASE_URL}/server/macro_scheduler/add",
    json=new_schedule
)
schedule_id = response.json()["result"]["schedule"]["id"]
print(f"Created schedule ID: {schedule_id}")

# Toggle schedule
requests.post(
    f"{BASE_URL}/server/macro_scheduler/toggle",
    json={"id": schedule_id}
)
print("Schedule toggled")

# Delete schedule
requests.post(
    f"{BASE_URL}/server/macro_scheduler/delete",
    json={"id": schedule_id}
)
print("Schedule deleted")
```

---

## JavaScript Examples

### Using `fetch` API:

```javascript
const BASE_URL = 'http://localhost:7125';

// List schedules
async function listSchedules() {
    const response = await fetch(`${BASE_URL}/server/macro_scheduler/schedules`);
    const data = await response.json();
    return data.result.schedules;
}

// Add schedule
async function addSchedule(schedule) {
    const response = await fetch(`${BASE_URL}/server/macro_scheduler/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(schedule)
    });
    const data = await response.json();
    return data.result.schedule;
}

// Toggle schedule
async function toggleSchedule(id) {
    const response = await fetch(`${BASE_URL}/server/macro_scheduler/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
    });
    return await response.json();
}

// Delete schedule
async function deleteSchedule(id) {
    const response = await fetch(`${BASE_URL}/server/macro_scheduler/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id })
    });
    return await response.json();
}

// Usage
const schedules = await listSchedules();
console.log('Schedules:', schedules);

const newSchedule = await addSchedule({
    name: 'Morning Warmup',
    macro: 'PREHEAT_BED',
    schedule_type: 'daily',
    time: '07:00',
    params: { TEMP: 60 }
});
console.log('Created:', newSchedule);
```

---

## Webhook Events

The scheduler component sends notification events when macros execute:

**Event:** `macro_scheduler:executed`

**Payload:**
```json
{
    "schedule": "Morning Preheat",
    "macro": "PREHEAT_BED TEMP=60",
    "time": "2025-10-13T07:00:00"
}
```

To receive these events, subscribe to Moonraker websocket notifications. See [Moonraker documentation](https://moonraker.readthedocs.io/en/latest/web_api/#websocket-api) for details.

---

## Rate Limiting

There are no rate limits on these endpoints, but be considerate:
- Don't poll for updates faster than once per second
- Use websocket notifications for real-time updates instead of polling

---

## Authentication

If Moonraker requires authentication (configured with `[authorization]`), you must include a valid API key or trusted connection.

**Using API Key:**
```bash
curl -H "X-Api-Key: your-api-key-here" \
  http://localhost:7125/server/macro_scheduler/schedules
```

---

## Versioning

API version is tied to the component version. Check the component logs for version information:

```bash
grep "Macro Scheduler" ~/printer_data/logs/moonraker.log
```

---

## Support

For issues or questions:
- **GitHub Issues**: [Report bugs](https://github.com/YOUR-USERNAME/klipper-macro-scheduler/issues)
- **Klipper Discourse**: [Community support](https://klipper.discourse.group/)
- **Documentation**: [Full docs](https://github.com/YOUR-USERNAME/klipper-macro-scheduler)
