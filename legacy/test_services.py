import win32serviceutil
import win32service
import win32event
import servicemanager
import os
from pathlib import Path
import time

class MyService(win32serviceutil.ServiceFramework):
    _svc_name_ = "MyPythonService"
    _svc_display_name_ = "My Python Service"
    _svc_description_ = "Demo Python Windows Service"

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.running = True

    def SvcStop(self):
        self.running = False
        win32event.SetEvent(self.stop_event)
        servicemanager.LogInfoMsg("Service is stopping...")

    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, ""),
        )
        try:
            self.main()
        except Exception as e:
            servicemanager.LogErrorMsg(f"Unhandled error: {e!r}")
            raise

    def main(self):
        log_dir = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / self._svc_name_
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "log.txt"

        while self.running:
            rc = win32event.WaitForSingleObject(self.stop_event, 5000)
            if rc == win32event.WAIT_OBJECT_0:
                break

            with log_path.open("a", encoding="utf-8") as f:
                f.write("Service running...\n")

        servicemanager.LogInfoMsg("Service stopped.")

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(MyService)