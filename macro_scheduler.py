# macro_scheduler.py
# Moonraker component for scheduling Klipper macros
#
# Copyright (C) 2025 Carlos Perez <carlos_perez@darkoperator.com.com>
#
# This file may be distributed under the terms of the GNU GPLv2 license.

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List

class MacroScheduler:
    def __init__(self, config):
        self.server = config.get_server()
        self.name = config.get_name()
        self.schedules: Dict[int, Dict[str, Any]] = {}
        self.next_schedule_id = 1
        self.tasks: Dict[int, asyncio.Task] = {}
        
        # Get database component for persistent storage
        self.database = None
        self.db_namespace = "macro_scheduler"
        
        # Register API endpoints
        self.server.register_endpoint(
            "/server/macro_scheduler/schedules", 
            ['GET'], 
            self._handle_list_schedules
        )
        self.server.register_endpoint(
            "/server/macro_scheduler/add", 
            ['POST'], 
            self._handle_add_schedule
        )
        self.server.register_endpoint(
            "/server/macro_scheduler/delete", 
            ['POST'], 
            self._handle_delete_schedule
        )
        self.server.register_endpoint(
            "/server/macro_scheduler/toggle", 
            ['POST'], 
            self._handle_toggle_schedule
        )
        self.server.register_endpoint(
            "/server/macro_scheduler/list_text", 
            ['GET'], 
            self._handle_list_text
        )
        
        logging.info("Macro Scheduler Component Initialized")
        
        # Register ready handler
        self.server.register_event_handler(
            "server:klippy_ready",
            self._handle_ready
        )
    
    async def _handle_ready(self):
        """Called when Klipper is ready"""
        # Try to get database component
        try:
            self.database = self.server.lookup_component("database")
            await self._load_schedules()
        except Exception as e:
            logging.warning(f"Database not available, schedules won't persist: {e}")
        
        await self._start_all_schedules()
        logging.info("Macro Scheduler is ready")
        logging.info("API available at: /server/macro_scheduler/schedules")
        logging.info("Use LIST_SCHEDULES macro to view schedules from Klipper")
    
    async def _load_schedules(self):
        """Load schedules from database"""
        if not self.database:
            return
            
        try:
            data = await self.database.get_item(
                self.db_namespace, 
                "schedules", 
                None
            )
            if data:
                self.schedules = {int(k): v for k, v in data.get("schedules", {}).items()}
                self.next_schedule_id = data.get("next_id", 1)
                logging.info(f"Loaded {len(self.schedules)} schedules from database")
        except Exception as e:
            logging.error(f"Error loading schedules: {e}")
    
    async def _save_schedules(self):
        """Save schedules to database"""
        if not self.database:
            return
            
        try:
            await self.database.insert_item(
                self.db_namespace,
                "schedules",
                {
                    "schedules": {str(k): v for k, v in self.schedules.items()},
                    "next_id": self.next_schedule_id
                }
            )
        except Exception as e:
            logging.error(f"Error saving schedules: {e}")
    
    async def _handle_list_schedules(self, web_request):
        """GET /server/macro_scheduler/schedules"""
        schedule_list = [
            {**schedule, "id": int(schedule.get("id", sid))}
            for sid, schedule in self.schedules.items()
        ]
        return {"schedules": schedule_list}
    
    async def _handle_add_schedule(self, web_request):
        """POST /server/macro_scheduler/add"""
        try:
            name = web_request.get_str("name")
            macro = web_request.get_str("macro")
            schedule_type = web_request.get_str("schedule_type", "once")
            params = web_request.get("params", {})
            
            schedule = {
                "id": self.next_schedule_id,
                "name": name,
                "macro": macro,
                "schedule_type": schedule_type,
                "params": params,
                "enabled": True,
                "next_run": None
            }
            
            if schedule_type == "once":
                datetime_str = web_request.get_str("datetime")
                schedule["datetime"] = datetime_str
                schedule["next_run"] = datetime_str
            elif schedule_type == "daily":
                time_str = web_request.get_str("time")
                schedule["time"] = time_str
                schedule["next_run"] = self._calculate_next_daily_run(time_str)
            elif schedule_type == "weekly":
                time_str = web_request.get_str("time")
                days = web_request.get("days", [])
                schedule["time"] = time_str
                schedule["days"] = days
                schedule["next_run"] = self._calculate_next_weekly_run(time_str, days)
            elif schedule_type == "interval":
                interval_minutes = web_request.get_int("interval_minutes", 60)
                schedule["interval_minutes"] = interval_minutes
                schedule["next_run"] = self._calculate_next_interval_run(interval_minutes)
            elif schedule_type == "cron":
                cron_expr = web_request.get_str("cron_expression")
                schedule["cron_expression"] = cron_expr
                schedule["next_run"] = self._calculate_next_cron_run(cron_expr)
            
            self.schedules[self.next_schedule_id] = schedule
            self.next_schedule_id += 1
            
            await self._save_schedules()
            await self._start_schedule(schedule["id"])
            
            return {"schedule": schedule}
        except Exception as e:
            logging.error(f"Error adding schedule: {e}")
            raise self.server.error(str(e), 400)
    
    async def _handle_delete_schedule(self, web_request):
        """POST /server/macro_scheduler/delete"""
        try:
            schedule_id = web_request.get_int("id")
            
            if schedule_id in self.schedules:
                await self._stop_schedule(schedule_id)
                del self.schedules[schedule_id]
                await self._save_schedules()
                return {"deleted": schedule_id}
            
            raise self.server.error(f"Schedule {schedule_id} not found", 404)
        except Exception as e:
            logging.error(f"Error deleting schedule: {e}")
            raise self.server.error(str(e), 400)
    
    async def _handle_toggle_schedule(self, web_request):
        """POST /server/macro_scheduler/toggle"""
        try:
            schedule_id = web_request.get_int("id")
            
            if schedule_id not in self.schedules:
                raise self.server.error(f"Schedule {schedule_id} not found", 404)
            
            schedule = self.schedules[schedule_id]
            schedule["enabled"] = not schedule["enabled"]
            
            if schedule["enabled"]:
                await self._start_schedule(schedule_id)
            else:
                await self._stop_schedule(schedule_id)
            
            await self._save_schedules()
            return {"schedule": schedule}
        except Exception as e:
            logging.error(f"Error toggling schedule: {e}")
            raise self.server.error(str(e), 400)
    
    async def _handle_list_text(self, web_request):
        """GET /server/macro_scheduler/list_text - Returns text format for macros"""
        if not self.schedules:
            return {"text": "No scheduled macros configured"}
        
        lines = ["=== Scheduled Macros ===", ""]
        for sid, schedule in self.schedules.items():
            status = "✓ ACTIVE" if schedule.get("enabled") else "✗ DISABLED"
            schedule_type = schedule["schedule_type"].upper()
            
            lines.append(f"[{sid}] {schedule['name']}")
            lines.append(f"    Macro: {schedule['macro']}")
            lines.append(f"    Type: {schedule_type}")
            lines.append(f"    Status: {status}")
            
            if schedule.get("enabled") and schedule.get("next_run"):
                lines.append(f"    Next run: {schedule['next_run']}")
            
            lines.append("")
        
        active = sum(1 for s in self.schedules.values() if s.get("enabled"))
        lines.append(f"Total: {active}/{len(self.schedules)} active")
        
        return {"text": "\n".join(lines)}
    
    def _calculate_next_daily_run(self, time_str: str) -> str:
        """Calculate next run time for daily schedule"""
        now = datetime.now()
        time_parts = time_str.split(":")
        hour, minute = int(time_parts[0]), int(time_parts[1])
        
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        
        return next_run.isoformat()
    
    def _calculate_next_weekly_run(self, time_str: str, days: List[int]) -> str:
        """Calculate next run time for weekly schedule
        days: list of weekday numbers (0=Monday, 6=Sunday)
        """
        if not days:
            return self._calculate_next_daily_run(time_str)
        
        now = datetime.now()
        time_parts = time_str.split(":")
        hour, minute = int(time_parts[0]), int(time_parts[1])
        
        for i in range(7):
            check_date = now + timedelta(days=i)
            if check_date.weekday() in days:
                next_run = check_date.replace(
                    hour=hour, 
                    minute=minute, 
                    second=0, 
                    microsecond=0
                )
                if next_run > now:
                    return next_run.isoformat()
        
        return now.isoformat()
    
    def _calculate_next_interval_run(self, interval_minutes: int) -> str:
        """Calculate next run time for interval-based schedule"""
        now = datetime.now()
        next_run = now + timedelta(minutes=interval_minutes)
        return next_run.isoformat()
    
    def _calculate_next_cron_run(self, cron_expression: str) -> str:
        """Calculate next run time for cron-style schedule
        Simplified cron parser supporting: minute hour day month weekday
        Examples:
        - "0 9 * * 1" = Every Monday at 9:00 AM
        - "30 14 * * 1,3,5" = Every Mon, Wed, Fri at 2:30 PM
        - "0 */3 * * *" = Every 3 hours
        """
        try:
            parts = cron_expression.split()
            if len(parts) != 5:
                logging.error(f"Invalid cron expression: {cron_expression}")
                return datetime.now().isoformat()
            
            minute, hour, day, month, weekday = parts
            now = datetime.now()
            
            # Simple cron parser for common patterns
            # Start from current time and check next valid times
            for days_ahead in range(366):  # Check up to a year ahead
                check_time = now + timedelta(days=days_ahead)
                
                # Check month
                if month != "*" and str(check_time.month) != month:
                    continue
                
                # Check day of month
                if day != "*" and str(check_time.day) != day:
                    continue
                
                # Check weekday (0=Monday in Python, 0=Sunday in cron, so convert)
                if weekday != "*":
                    cron_weekday = (check_time.weekday() + 1) % 7  # Convert to cron format
                    weekdays = [int(d) for d in weekday.split(",") if d.isdigit()]
                    if weekdays and cron_weekday not in weekdays:
                        continue
                
                # Check hour
                if hour.startswith("*/"):  # Every N hours
                    interval = int(hour[2:])
                    valid_hours = [h for h in range(24) if h % interval == 0]
                else:
                    valid_hours = [int(hour)] if hour != "*" else list(range(24))
                
                # Check minute
                if minute.startswith("*/"):  # Every N minutes
                    interval = int(minute[2:])
                    valid_minutes = [m for m in range(60) if m % interval == 0]
                else:
                    valid_minutes = [int(minute)] if minute != "*" else [0]
                
                # Find next valid time on this day
                for h in sorted(valid_hours):
                    for m in sorted(valid_minutes):
                        next_run = check_time.replace(
                            hour=h, 
                            minute=m, 
                            second=0, 
                            microsecond=0
                        )
                        if next_run > now:
                            return next_run.isoformat()
            
            # Fallback if no valid time found
            return (now + timedelta(days=1)).isoformat()
            
        except Exception as e:
            logging.error(f"Error parsing cron expression {cron_expression}: {e}")
            return (datetime.now() + timedelta(hours=1)).isoformat()
    
    async def _start_all_schedules(self):
        """Start all enabled schedules"""
        for schedule_id in list(self.schedules.keys()):
            schedule = self.schedules[schedule_id]
            if schedule.get("enabled", True):
                await self._start_schedule(schedule_id)
    
    async def _start_schedule(self, schedule_id: int):
        """Start a specific schedule"""
        if schedule_id in self.tasks:
            await self._stop_schedule(schedule_id)
        
        schedule = self.schedules[schedule_id]
        task = asyncio.create_task(self._run_schedule(schedule_id))
        self.tasks[schedule_id] = task
        
        logging.info(f"Started schedule {schedule_id}: {schedule['name']}")
    
    async def _stop_schedule(self, schedule_id: int):
        """Stop a specific schedule"""
        if schedule_id in self.tasks:
            self.tasks[schedule_id].cancel()
            try:
                await self.tasks[schedule_id]
            except asyncio.CancelledError:
                pass
            del self.tasks[schedule_id]
            logging.info(f"Stopped schedule {schedule_id}")
    
    async def _run_schedule(self, schedule_id: int):
        """Execute schedule loop"""
        while True:
            try:
                schedule = self.schedules.get(schedule_id)
                if not schedule or not schedule.get("enabled", True):
                    break
                
                next_run_str = schedule.get("next_run")
                if not next_run_str:
                    break
                    
                next_run = datetime.fromisoformat(next_run_str)
                now = datetime.now()
                
                wait_seconds = (next_run - now).total_seconds()
                
                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                
                await self._execute_macro(schedule)
                
                # Calculate next run based on schedule type
                if schedule["schedule_type"] == "once":
                    schedule["enabled"] = False
                    await self._save_schedules()
                    break
                elif schedule["schedule_type"] == "daily":
                    schedule["next_run"] = self._calculate_next_daily_run(
                        schedule["time"]
                    )
                elif schedule["schedule_type"] == "weekly":
                    schedule["next_run"] = self._calculate_next_weekly_run(
                        schedule["time"],
                        schedule.get("days", [])
                    )
                elif schedule["schedule_type"] == "interval":
                    schedule["next_run"] = self._calculate_next_interval_run(
                        schedule["interval_minutes"]
                    )
                elif schedule["schedule_type"] == "cron":
                    schedule["next_run"] = self._calculate_next_cron_run(
                        schedule["cron_expression"]
                    )
                
                await self._save_schedules()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in schedule {schedule_id}: {e}")
                await asyncio.sleep(60)
    
    async def _execute_macro(self, schedule: Dict[str, Any]):
        """Execute a Klipper macro"""
        try:
            klippy_apis = self.server.lookup_component('klippy_apis')
            
            macro_name = schedule["macro"]
            params = schedule.get("params", {})
            
            param_str = " ".join([f"{k}={v}" for k, v in params.items()])
            gcode = f"{macro_name} {param_str}".strip()
            
            logging.info(f"Executing scheduled macro: {gcode}")
            
            await klippy_apis.run_gcode(gcode)
            
            self.server.send_event(
                "macro_scheduler:executed",
                {
                    "schedule": schedule["name"],
                    "macro": gcode,
                    "time": datetime.now().isoformat()
                }
            )
            
        except Exception as e:
            logging.error(f"Error executing macro {schedule['macro']}: {e}")

def load_component(config):
    return MacroScheduler(config)
