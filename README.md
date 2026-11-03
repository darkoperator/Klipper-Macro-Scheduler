# Klipper Macro Scheduler
<img width="1233" height="481" alt="{36147343-6C81-40DA-83BC-F08D9152A818}" src="https://github.com/user-attachments/assets/76fe5443-5955-4535-9dae-963dd17f14ec" />

A powerful scheduling system for Klipper 3D printers that allows you to schedule macros to run at specific times, intervals, or using cron expressions.

## Features

- **Multiple Schedule Types**: Once, Daily, Weekly, Interval, and Cron
- **Flexible Scheduling**: Simple time-based or complex cron expressions
- **Macro Parameters**: Pass parameters to scheduled macros
- **Persistent Storage**: Schedules survive reboots
- **Web UI**: Easy-to-use interface for managing schedules
- **KlipperScreen Panels**: Touch-friendly viewer and editor panels install automatically
- **One-Command Install**: `install.py` links the component, UI, and panels, and backs up any config it changes
- **Legacy OS Ready**: Installer runs on Raspberry Pi OS Bullseye (Python 3.8) through Debian Trixie
- **Status Tracking**: See next run times and the result of the last run
- **Safe Defaults**: Runs missed while the printer was off are skipped, and schedules skip while printing, unless you opt in per schedule
- **Auto-Start**: Schedules resume automatically after Moonraker restarts

## Installation Steps

### Prerequisites

- Klipper firmware installed
- Moonraker API server running
- Web browser access to your printer
- Mainsail or Fluidd
- (Optional) KlipperScreen 0.3+ if you want native touchscreen panels
- Python 3.8+ (works on Raspberry Pi OS Bullseye) through Python 3.12 (Debian Trixie)

### Recommended: Automated Install via `install.py`

```Bash
# SSH into your printer
ssh pi@your-printer-ip
# Clone Repo in to macro_scheduler folder
git clone https://github.com/darkoperator/Klipper-Macro-Scheduler.git macro_scheduler

# Run installer
cd macro_scheduler/
python3 install.py
```
The installer links the Moonraker component, web UI, and KlipperScreen panels to this folder, so later updates take effect after a service restart. It also adds any missing entries to `moonraker.conf` and `KlipperScreen.conf`, backing up each file it changes. It finds Mainsail and Fluidd automatically, and is safe to run again.

Moonraker's Update Manager pulls updates with `git pull` but never runs install scripts. So the installer adds a Git `post-merge` hook to this folder that runs it again after each update, with the same paths, once per printer instance. If you already have a `post-merge` hook, the installer leaves it alone and prints the line to add. The hook doesn't run when Moonraker recovers or rolls back the repo, or when it runs in debug mode; the next normal update catches up.

Preview the changes first with `python3 install.py --dry-run`.

If your folders aren't in the default locations, or you run several printers on one host, run it once per instance and set the paths:

```Bash
python3 install.py --config-dir ~/printer_2_data/config
python3 install.py --moonraker-dir ~/moonraker --klipperscreen-dir ~/KlipperScreen --web-dir ~/mainsail
```

> **Upgrading from v0.1.x?** Run `python3 install.py` once after updating. Later updates run it for you. Earlier versions copied their files, and Moonraker doesn't run install scripts, so an update alone leaves the old copies in use. See the [v0.2.0 changelog](#v020-2026-11-02) for the behavior changes.

### Manual Installation (Only if the Installer Cannot Be Used)



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
```
Update Manager can only restart Moonraker for this section. After an update that changes the panels, restart KlipperScreen yourself: `sudo systemctl restart KlipperScreen`.

Moonraker deletes extra files from Mainsail and Fluidd when it updates them. To keep the page, the installer adds it to `persistent_files` in that client's `[update_manager ...]` section, including sections in included files. If you later add such a section, or installed by hand, add this to it, or run the installer again:

```ini
persistent_files: scheduler.html
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
Macro Scheduler 0.2.1 Component Initialized
Macro Scheduler is ready
```

## Access the UI

Open your browser and navigate to:
```
http://your-printer-ip/scheduler.html
```
Pages served by Mainsail or Fluidd use the same origin automatically. If Moonraker is on another port of the same host, append `?api_base=http://printer-hostname:7125`. For safety, `api_base` is ignored if it names a different host, unless you opened the page from a local file.

If Moonraker requires authorization, add your device to `trusted_clients` in the `[authorization]` section of `moonraker.conf`. The page doesn't log in.

## KlipperScreen Panel

`install.py` links two KlipperScreen panels and adds a menu entry:

- `Macro Scheduler` lists existing schedules with their next run and last result, and lets you enable, disable, or delete them.
- The editor panel, opened with **New**, is the creation form. It follows KlipperScreen's 24-hour time setting.

After running the installer:

1. Restart KlipperScreen (`sudo systemctl restart KlipperScreen`) or reboot the display so it loads the new panels.
2. If no menu entry exists yet, the installer appends the following to `KlipperScreen.conf`:
   ```ini
   [menu __main macro_scheduler]
   name: Macro Scheduler
   panel: macro_scheduler
   icon: clock
   ```
   A `macro_scheduler_editor` entry from an earlier version still works, and can be removed.
3. The editor panel opens with blank fields each time you tap **New**, and the weekly schedule view supports selecting multiple weekdays via highlighted toggle buttons.

## Missed Runs and Printing

Each schedule has two safety settings:

| Setting | Default | Effect |
|---------|---------|--------|
| `missed_run_policy` | `skip` | A run more than 2 minutes late, for example because the Pi was off, is recorded as `missed` and not run. With `run`, it runs as soon as Klipper is available. |
| `skip_if_printing` | `true` | A run due while the printer is printing or paused is recorded as `skipped`. Turn this off for macros meant to run during a print, such as lights. |

Runs that fail are recorded as `failed` and aren't retried. If Moonraker restarts during a macro, the run is recorded as `interrupted` and isn't repeated.

Times are the printer's local time. A daily run in the hour skipped by a daylight saving change comes due when the clock jumps, so it's usually recorded as `missed`.

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

**Note:** The first run is one interval after the schedule is created.

### 5. Cron Expression (Advanced)

Use cron-style expressions for complex scheduling patterns.

**Format:** `minute hour day month weekday`

**Field Values:**
- **minute**: 0-59
- **hour**: 0-23 (24-hour format)
- **day**: 1-31
- **month**: 1-12
- **weekday**: 0-7 (0 and 7 = Sunday, 1 = Monday, etc.)

**Special Characters:**
- `*` = Any value (every minute/hour/day)
- `*/N` = Every N units (e.g., `*/5` = every 5 minutes)
- `,` = List separator (e.g., `1,3,5` = Monday, Wednesday, Friday)
- `-` = Range (e.g., `1-5` = Monday to Friday)
- `a-b/N` = Every N units within a range

If both day and weekday are restricted, the schedule runs when either matches, as in standard cron. Month and weekday names aren't supported. Invalid expressions are rejected when you add them.

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
   - **Macro**: Select from dropdown. This must be a single command name; pass any arguments as parameters.
   - **Schedule Type**: Choose one of the 5 types
   - **Type-specific fields**: Fill based on selected type. Dates use a calendar, and hours and minutes use dropdowns, so there's no need to type them.
   - **Parameters**: Optional JSON object with macro parameters
   - **If a Run Is Missed** and **Skip while printing**: See [Missed Runs and Printing](#missed-runs-and-printing)
3. Click "Add Schedule"

### Managing Schedules

- **Enable/Disable**: Toggle the button to pause/resume a schedule
- **Delete**: Remove a schedule permanently
- **Next Run**: View when the schedule will execute next
- **Last Result**: See whether the last run worked, and why it didn't if not

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

**Verify file exists** (use `~/fluidd` for Fluidd):
```bash
ls -la ~/mainsail/scheduler.html
```

If the page disappeared after a web client update, run `python3 install.py` again.

**Check browser console (F12)** for JavaScript errors.

### Schedule Not Executing

1. Check if schedule is enabled (green badge)
2. Check its last result: `missed`, `skipped`, `failed`, and `invalid` each say why it didn't run
3. Verify next run time is in the future, and that the printer's clock and timezone are right
4. Check Moonraker logs during scheduled time
5. Verify macro exists in Klipper configuration

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

The code lives in this repository, so only your schedules need backing up:

```bash
# Backup database (includes schedules)
cp ~/printer_data/database/moonraker-sql.db \
   ~/moonraker-db-backup.db
```

### Restore

```bash
sudo systemctl stop moonraker
cp ~/moonraker-db-backup.db ~/printer_data/database/moonraker-sql.db
sudo systemctl start moonraker
```

Don't copy files over the installed component or page: they are links, so that would overwrite this repository.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run the tests: `python3 -m unittest discover -s tests` and `node --test tests/web_ui.test.js`
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

### v0.2.1 (2026-11-03)

- The installer adds a Git hook that runs it again after each Update Manager update, so new files and config entries in later versions are set up without running it by hand. Run `python3 install.py` once to add the hook.

### v0.2.0 (2026-11-02)

**Run `python3 install.py` once after updating**, then restart Moonraker and KlipperScreen.

Behavior changes:
- Runs missed while the printer was off or Klipper wasn't ready are now skipped instead of running at startup. Set `missed_run_policy` to `run` to catch up.
- Schedules now skip while printing or paused, including existing ones. Turn off `skip_if_printing` for macros meant to run during a print.
- Re-enabling a schedule works out a new next run instead of firing immediately. A "once" schedule whose time has passed can't be re-enabled.
- Stored schedules that fail the new checks are disabled on startup and marked `invalid`. This includes a macro field holding a full command such as `M117 hello`.
- `api_base` is now limited to the page's own host.
- The installer now links files instead of copying them, and no longer adds a menu entry for the editor panel.

Fixes:
- KlipperScreen panels work again on current KlipperScreen, which removed the REST client they used. Requests no longer block the screen.
- Invalid intervals and cron expressions could run a macro nonstop. All input is now validated by the server, including G-code injection through parameters.
- Cron is rewritten: ranges, lists, weekday 7, and standard day/weekday rules work, and invalid expressions are rejected.
- Schedules no longer disappear when added before Klipper is ready, and are available without Klipper.
- Failed saves now return an error instead of reporting success.
- Macro results are recorded. Each run is saved before it starts, so a restart can't repeat it.
- A single loop rechecks the clock every 30 seconds, so clock changes after boot no longer delay runs.
- Fixed stored XSS in the web UI, and misleading display of interval, cron, and authorization errors.
- `macro_scheduler:executed` now reaches websocket clients, as `notify_macro_scheduler_executed`, and includes the result.
- Web UI: dates use a calendar, and hours and minutes use dropdowns in every browser, so times don't need typing. The default "once" time is the next hour.
- KlipperScreen: delete asks for confirmation, the list refreshes when shown, Back works as expected, dates are readable, and the form never defaults to a past time.
- Installer: `--dry-run` no longer changes config files, the list panel gets its menu entry, Fluidd and multiple instances are supported, missing folders are no longer created, and the web page survives web client updates.

Added automated tests and CI.

The project is now licensed under GPLv3, to match Moonraker and Klipper. Earlier releases were published under Apache 2.0, and remain available under those terms.

### v0.1.6 (2025-11-08)
- Installer compatibility fix for legacy Raspberry Pi OS (Bullseye / Python 3.8)
- Documented the `?api_base=` override for alternate hosting setups

### v0.1.5 (2025-10-16)
- Added first-class KlipperScreen support with viewer and editor panels
- Switched to the automated `install.py` workflow for deploying all assets
- Updated documentation to reflect the simplified install path and panel usage

### v0.1.0 (2025-10-12)
- Initial release
- Support for 5 schedule types
- Web UI interface
- Persistent storage
- Macro parameter support

---

**Made with ❤️ for the Klipper community**
