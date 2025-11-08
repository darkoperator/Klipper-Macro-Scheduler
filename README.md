# Klipper Macro Scheduler
<img width="1233" height="481" alt="{36147343-6C81-40DA-83BC-F08D9152A818}" src="https://github.com/user-attachments/assets/76fe5443-5955-4535-9dae-963dd17f14ec" />

A powerful scheduling system for Klipper 3D printers that allows you to schedule macros to run at specific times, intervals, or using cron expressions.

## Features

- **Multiple Schedule Types**: Once, Daily, Weekly, Interval, and Cron
- **Flexible Scheduling**: Simple time-based or complex cron expressions
- **Macro Parameters**: Pass parameters to scheduled macros
- **Persistent Storage**: Schedules survive reboots
- **Web UI**: Easy-to-use interface for managing schedules
- **Status Tracking**: See next run times and execution history
- **Auto-Start**: Schedules resume automatically after Moonraker restarts

## Installation Steps

### Prerequisites

- Klipper firmware installed
- Moonraker API server running
- Web browser access to your printer
- Mainsail
- Python 3.8+ (preinstalled on standard Klipper images)

### Git Installation

```Bash
# SSH into your printer
ssh pi@your-printer-ip
# Clone Repo in to macro_scheduler folder
git clone https://github.com/darkoperator/Klipper-Macro-Scheduler.git macro_scheduler

# Run installer
cd macro_scheduler/
python install.py
```
The installer copies the Moonraker component, web UI, and KlipperScreen panels, and appends the required entries to `moonraker.conf` and `KlipperScreen.conf` when they are missing (backups are created automatically).
### Manual Installation



### Step 1: Install the Moonraker Component

```bash
# SSH into your printer
ssh pi@your-printer-ip

# Navigate to Moonraker components directory
cd ~/moonraker/moonraker/components/

# Create the component file
nano macro_scheduler.py
```

Copy the entire component code from `macro_scheduler.py` and paste it into the file.

Save with `Ctrl+X`, `Y`, `Enter`.

### Step 2: Install the Web UI

```bash
# Copy the UI to Mainsail directory
cd ~
nano ~/mainsail/scheduler.html
```

Copy the entire UI code from `scheduler_ui.html` and paste it into the file.

Save with `Ctrl+X`, `Y`, `Enter`.

## Configure Moonraker

```bash
# Edit moonraker.conf
nano ~/printer_data/config/moonraker.conf
```

Add this section:

```ini
[macro_scheduler]
# This enables the macro scheduler component
```

### Enable Auto-Updates (Optional but Recommended)

Add this to your `moonraker.conf`:

```ini
[update_manager macro_scheduler]
type: git_repo
path: ~/macro_scheduler
origin: https://github.com/darkoperator/klipper-macro-scheduler.git
primary_branch: main
managed_services: moonraker
install_script: install.sh
```

### Restart Moonraker

```bash
sudo systemctl restart moonraker
```

Check the logs to confirm it loaded:

```bash
tail -f ~/printer_data/logs/moonraker.log | grep -i scheduler
```

You should see:
```
Macro Scheduler Component Initialized
Macro Scheduler is ready
```

## Access the UI

Open your browser and navigate to:
```
http://your-printer-ip/scheduler.html
```

## KlipperScreen Panel

`install.py` automatically deploys two KlipperScreen panels and patches your configuration files:

- `Macro Scheduler` lists existing schedules and lets you enable/disable/delete them.
- `Macro Scheduler Editor` provides the touch-friendly creation form (date picker, hour/minute toggles, AM/PM buttons, weekday selectors).

After running the installer:

1. Restart KlipperScreen (`sudo systemctl restart KlipperScreen`) or reboot the display so it loads the new panels.
2. If no menu entries exist yet, the installer appends the following to `KlipperScreen.conf`:
   ```ini
   [menu __main macro_scheduler]
   name: Macro Scheduler
   panel: macro_scheduler
   icon: clock

   [menu __main macro_scheduler_editor]
   name: Macro Scheduler Editor
   panel: macro_scheduler_editor
   icon: clock
   ```
3. The editor panel opens with blank fields each time you tap **New**, and the weekly schedule view supports selecting multiple weekdays via highlighted toggle buttons.

## Schedule Types

### 1. Once

Execute a macro one time at a specific date and time.

**Use Cases:**
- Start a print at a specific time
- Preheat bed before you arrive
- One-time maintenance task

**Example:**
- **Name:** Morning Preheat
- **Type:** Once
- **DateTime:** 2025-10-13 07:00
- **Macro:** PREHEAT_BED
- **Parameters:** `{"TEMP": 60}`

### 2. Daily

Execute a macro every day at a specific time.

**Use Cases:**
- Daily bed preheat
- Nightly shutdown
- Regular maintenance reminders

**Example:**
- **Name:** Daily Warmup
- **Type:** Daily
- **Time:** 08:00
- **Macro:** MORNING_ROUTINE

### 3. Weekly (Custom Days)

Execute a macro on specific days of the week at a specific time.

**Day Numbering:**
- Monday = 0
- Tuesday = 1
- Wednesday = 2
- Thursday = 3
- Friday = 4
- Saturday = 5
- Sunday = 6

**Use Cases:**
- Weekday-only operations
- Weekend maintenance
- Business hours schedules

**Example:**
- **Name:** Weekday Preheat
- **Type:** Weekly
- **Days:** Monday, Tuesday, Wednesday, Thursday, Friday (0-4)
- **Time:** 07:00
- **Macro:** PREHEAT_BED

### 4. Interval

Execute a macro repeatedly at fixed intervals (in minutes).

**Use Cases:**
- Periodic bed mesh calibration
- Regular temperature checks
- Recurring status reports

**Example:**
- **Name:** Hourly Status
- **Type:** Interval
- **Interval:** 60 minutes
- **Macro:** STATUS_CHECK

**Note:** Interval schedules start immediately upon creation and repeat continuously.

### 5. Cron Expression (Advanced)

Use cron-style expressions for complex scheduling patterns.

**Format:** `minute hour day month weekday`

**Field Values:**
- **minute**: 0-59
- **hour**: 0-23 (24-hour format)
- **day**: 1-31
- **month**: 1-12
- **weekday**: 0-6 (0 = Sunday, 1 = Monday, etc.)

**Special Characters:**
- `*` = Any value (every minute/hour/day)
- `*/N` = Every N units (e.g., `*/5` = every 5 minutes)
- `,` = List separator (e.g., `1,3,5` = Monday, Wednesday, Friday)

**Common Examples:**

| Expression | Description |
|------------|-------------|
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `30 14 * * 1,3,5` | Monday, Wednesday, Friday at 2:30 PM |
| `0 */3 * * *` | Every 3 hours |
| `0 0 * * *` | Every day at midnight |
| `0 12 * * 0` | Every Sunday at noon |
| `15 8 1 * *` | First day of every month at 8:15 AM |
| `0 9-17 * * 1-5` | Every hour from 9 AM to 5 PM on weekdays |
| `*/30 * * * *` | Every 30 minutes |

**Use Cases:**
- Complex business hours schedules
- Multi-time-per-day operations
- Irregular maintenance schedules

## Sample Macros

### Example 1: Neopixel Color Control

Add to `printer.cfg`:

```ini
[neopixel my_neopixel]
pin: PA8
chain_count: 8
color_order: GRB
initial_RED: 0.0
initial_GREEN: 0.0
initial_BLUE: 0.0

[gcode_macro SET_NEOPIXEL_COLOR]
description: Set neopixel color and intensity
gcode:
    {% set RED = params.RED|default(0)|float %}
    {% set GREEN = params.GREEN|default(0)|float %}
    {% set BLUE = params.BLUE|default(0)|float %}
    {% set INTENSITY = params.INTENSITY|default(1.0)|float %}
    
    # Scale colors by intensity (0.0-1.0)
    {% set r = RED * INTENSITY %}
    {% set g = GREEN * INTENSITY %}
    {% set b = BLUE * INTENSITY %}
    
    SET_LED LED=my_neopixel RED={r} GREEN={g} BLUE={b}
    M117 LED: R{RED} G{GREEN} B{BLUE} @{INTENSITY*100}%
```

**Schedule Examples:**

**Morning Wake-Up (Warm White):**
- **Name:** Morning Lights
- **Type:** Daily
- **Time:** 07:00
- **Macro:** SET_NEOPIXEL_COLOR
- **Parameters:**
```json
{
  "RED": 1.0,
  "GREEN": 0.8,
  "BLUE": 0.5,
  "INTENSITY": 0.8
}
```

**Evening Ambient (Cool Blue):**
- **Name:** Evening Mode
- **Type:** Daily
- **Time:** 20:00
- **Macro:** SET_NEOPIXEL_COLOR
- **Parameters:**
```json
{
  "RED": 0.0,
  "GREEN": 0.3,
  "BLUE": 1.0,
  "INTENSITY": 0.3
}
```

**Rainbow Cycle (Cron - Every 4 hours):**
- **Type:** Cron
- **Expression:** `0 */4 * * *`

### Example 2: Schedule a Print Job

Add to `printer.cfg`:

```ini
[gcode_macro SCHEDULE_PRINT]
description: Start printing a specified file
gcode:
    {% set FILENAME = params.FILE|default("")|string %}
    
    {% if FILENAME == "" %}
        RESPOND MSG="Error: No file specified. Use FILE parameter"
        M117 No file specified
    {% else %}
        # Home if not homed
        {% if printer.toolhead.homed_axes != "xyz" %}
            G28
        {% endif %}
        
        # Heat and start print
        M117 Starting scheduled print: {FILENAME}
        RESPOND MSG="Starting print: {FILENAME}"
        
        # Start the print
        SDCARD_PRINT_FILE FILENAME="{FILENAME}"
    {% endif %}

[gcode_macro SCHEDULED_PRINT_WITH_PREP]
description: Print with full preparation sequence
gcode:
    {% set FILENAME = params.FILE|default("")|string %}
    {% set BED_TEMP = params.BED_TEMP|default(60)|float %}
    {% set EXTRUDER_TEMP = params.EXTRUDER_TEMP|default(210)|float %}
    
    {% if FILENAME == "" %}
        RESPOND MSG="Error: No file specified"
    {% else %}
        M117 Preparing scheduled print
        
        # Home
        G28
        
        # Heat bed and wait
        M190 S{BED_TEMP}
        
        # Heat extruder and wait
        M109 S{EXTRUDER_TEMP}
        
        # Prime nozzle
        G1 Z2.0 F3000
        G1 X10 Y10 F5000
        G1 Z0.3 F3000
        G1 X100 E15 F1000
        G1 Z2.0 F3000
        
        # Start print
        M117 Starting: {FILENAME}
        SDCARD_PRINT_FILE FILENAME="{FILENAME}"
    {% endif %}
```

**Schedule Examples:**

**Overnight Print (Simple):**
- **Name:** Overnight Print
- **Type:** Once
- **DateTime:** 2025-10-13 22:00
- **Macro:** SCHEDULE_PRINT
- **Parameters:**
```json
{
  "FILE": "test_cube.gcode"
}
```

**Weekend Batch Print (With Prep):**
- **Name:** Saturday Morning Print
- **Type:** Weekly
- **Days:** Saturday (5)
- **Time:** 08:00
- **Macro:** SCHEDULED_PRINT_WITH_PREP
- **Parameters:**
```json
{
  "FILE": "benchy.gcode",
  "BED_TEMP": 60,
  "EXTRUDER_TEMP": 210
}
```

**Daily Test Print (Cron):**
- **Type:** Cron
- **Expression:** `0 2 * * *` (Every day at 2:00 AM)
- **Macro:** SCHEDULED_PRINT_WITH_PREP
- **Parameters:**
```json
{
  "FILE": "calibration_cube.gcode",
  "BED_TEMP": 60,
  "EXTRUDER_TEMP": 200
}
```

### Example 3: Temperature Management

```ini
[gcode_macro PREHEAT_BED]
description: Preheat bed to specified temperature
gcode:
    {% set TEMP = params.TEMP|default(60)|float %}
    M140 S{TEMP}
    M117 Preheating bed to {TEMP}C
    RESPOND MSG="Bed preheating to {TEMP}C"

[gcode_macro COOLDOWN]
description: Turn off all heaters
gcode:
    M104 S0  ; Turn off extruder
    M140 S0  ; Turn off bed
    M106 S0  ; Turn off part fan
    M117 Cooldown complete
    RESPOND MSG="All heaters off"
```

**Schedule:**

**Morning Preheat:**
- **Type:** Daily
- **Time:** 07:00
- **Macro:** PREHEAT_BED
- **Parameters:** `{"TEMP": 60}`

**Nightly Cooldown:**
- **Type:** Daily
- **Time:** 23:00
- **Macro:** COOLDOWN

## Using the Web UI

### Adding a Schedule

1. Click "Add Schedule" button
2. Fill in the form:
   - **Schedule Name**: Descriptive name
   - **Macro**: Select from dropdown
   - **Schedule Type**: Choose one of the 5 types
   - **Type-specific fields**: Fill based on selected type
   - **Parameters**: Optional JSON object with macro parameters
3. Click "Add Schedule"

### Managing Schedules

- **Enable/Disable**: Toggle the button to pause/resume a schedule
- **Delete**: Remove a schedule permanently
- **Next Run**: View when the schedule will execute next

### Parameter Format

Parameters must be valid JSON:

```json
{
  "PARAM1": "value",
  "PARAM2": 123,
  "PARAM3": 45.6
}
```

**Examples:**

Simple:
```json
{"TEMP": 60}
```

Multiple parameters:
```json
{
  "BED_TEMP": 60,
  "EXTRUDER_TEMP": 210,
  "SPEED": 100
}
```

Complex:
```json
{
  "FILE": "test.gcode",
  "RED": 1.0,
  "GREEN": 0.5,
  "BLUE": 0.0,
  "INTENSITY": 0.8
}
```

## API Reference

### List Schedules
```
GET /server/macro_scheduler/schedules
```

### Add Schedule
```
POST /server/macro_scheduler/add
Body: {
  "name": "Schedule Name",
  "macro": "MACRO_NAME",
  "schedule_type": "once|daily|weekly|interval|cron",
  "params": {},
  ...type-specific fields
}
```

### Delete Schedule
```
POST /server/macro_scheduler/delete
Body: {"id": 1}
```

### Toggle Schedule
```
POST /server/macro_scheduler/toggle
Body: {"id": 1}
```

### Get Text Format (for macros)
```
GET /server/macro_scheduler/list_text
```

## Troubleshooting

### Component Not Loading

**Check logs:**
```bash
tail -f ~/printer_data/logs/moonraker.log | grep -i scheduler
```

**Verify component exists:**
```bash
ls -la ~/moonraker/moonraker/components/macro_scheduler.py
```

**Check moonraker.conf:**
```bash
cat ~/printer_data/config/moonraker.conf | grep -A2 "\[macro_scheduler\]"
```

### UI Not Loading

**Verify file exists:**
```bash
ls -la ~/mainsail/scheduler.html
```

**Check browser console (F12)** for JavaScript errors.

### Schedule Not Executing

1. Check if schedule is enabled (green badge)
2. Verify next run time is in the future
3. Check Moonraker logs during scheduled time
4. Verify macro exists in Klipper configuration

### Macros Not Listed

The macro dropdown fetches from Klipper. If macros don't appear:

1. Ensure macros are defined in `printer.cfg`
2. Restart Klipper
3. Refresh the scheduler UI

## Database Location

Schedules are stored in:
```
~/printer_data/database/moonraker-sql.db
```

**View schedules in database:**
```bash
sqlite3 ~/printer_data/database/moonraker-sql.db \
  "SELECT * FROM namespace_store WHERE namespace='macro_scheduler';"
```

## Backup and Restore

### Backup

```bash
# Backup component
cp ~/moonraker/moonraker/components/macro_scheduler.py \
   ~/macro_scheduler_backup.py

# Backup UI
cp ~/mainsail/scheduler.html ~/scheduler_backup.html

# Backup database (includes schedules)
cp ~/printer_data/database/moonraker-sql.db \
   ~/moonraker-db-backup.db
```

### Restore

```bash
# Restore component
cp ~/macro_scheduler_backup.py \
   ~/moonraker/moonraker/components/macro_scheduler.py

# Restore UI
cp ~/scheduler_backup.html ~/mainsail/scheduler.html

# Restart
sudo systemctl restart moonraker
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is licensed under the GNU GPLv3 License.

## Credits

- **Klipper** by Kevin O'Connor
- **Moonraker** by Eric Callahan (Arksine)
- **Mainsail** by meteyou

## Support

- **Issues**: [GitHub Issues](https://github.com/darkoperator/klipper-macro-scheduler/issues)
- **Discord**: [Klipper Discord](https://discord.gg/klipper)

## Changelog

### v1.0.0 (2025-10-12)
- Initial release
- Support for 5 schedule types
- Web UI interface
- Persistent storage
- Macro parameter support

---

**Made with ❤️ for the Klipper community**
