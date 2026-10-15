"""Check production status serialization, including non-finite confidence."""
from pathlib import Path
import json
import subprocess
import tempfile
root = Path(__file__).resolve().parent.parent
cpp = (root / "components/meter_setup/meter_setup.cpp").read_text()
header = (root / "components/meter_setup/meter_setup.h").read_text()
settings = header[header.index("struct Settings {"):header.index("class MeterSetup")]
quote = cpp[cpp.index("static std::string quote("):cpp.index("int MeterSetup::invalid_box_(")]
zones = cpp[cpp.index("static std::string zones(const Settings &s) {"):cpp.index("void MeterSetup::setup()")]
status = cpp[cpp.index("std::string MeterSetup::status_()"):cpp.index("void MeterSetup::handleRequest(")]
source = r'''
#include <string>
#include <memory>
#include <cmath>
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <iostream>
#define ESPHOME_LOOP_TASK_STACK_SIZE 32768
unsigned uxTaskGetStackHighWaterMark(void *) { return 24000; }
'''+f'#include "{root / "components/meter_setup/alignment.h"}"\nusing namespace esphome::meter_setup;\n'+settings+quote+zones+r'''
class MeterSetup {
 public:
 Settings settings_{}; AlignmentReference alignment_{},draft_alignment_{}; uint32_t reference_revision_=0,alignment_ms_=0;std::string alignment_result_="Ausgeschaltet";
 bool busy_=false,paused_=true,capture_pending_=false,illumination_on_=false,light_test_=false;void *illumination_=nullptr;IlluminationSettings illumination_settings_{};
 uint32_t frame_=12,http_stack_free_=1200,reset_count_=0;
 std::string digits_="00123456",message_="Test \"ok\"",http_task_name_="httpd";
 float confidence_=73.4f;
 uint16_t led_capacity_() const{return 64;}
 std::shared_ptr<uint8_t> preview_;uint32_t preview_sequence_=0;bool preview_rgb_=false;
 struct Power{bool supported(){return true;}bool standby_enabled(){return true;}bool weak_drive(){return false;}bool sleeping(){return true;}std::string status(){return "Sensor im Software-Standby";}}camera_power_;
 AutofocusSettings autofocus_settings_{};struct AF{bool supported(){return false;}int error(){return 0;}}autofocus_;std::string autofocus_status_="Kamera ohne Autofokus";
 RuntimeSettings runtime_{};float reading_age_=NAN;bool stale_=false;uint32_t config_revision_=0;float digit_confidences_[8]{};std::string confidence_digits_;
 RecoveryRecord recovery_{};bool reboot_pending_=false;uint32_t recovery_delay_ms_=10000;std::string last_reader_log_;std::string reader_phase_()const{return "idle";}
 std::string status_();
};
'''+status+r'''
int main() {
 MeterSetup meter;
 std::cout<<meter.status_()<<"\n";
 meter.confidence_=NAN;
 std::cout<<meter.status_()<<"\n";
 meter.confidence_=INFINITY;
 std::cout<<meter.status_()<<"\n";
}
'''
with tempfile.TemporaryDirectory(prefix="meter-status-test-") as directory:
 binary = str(Path(directory) / "status-test")
 subprocess.run(["g++", "-std=c++17", "-x", "c++", "-", "-o", binary], input=source, text=True, check=True)
 rows = [json.loads(line) for line in subprocess.check_output([binary], text=True).splitlines()]
 assert [row["confidence"] for row in rows] == [73.4, 0, 0]
 assert rows[0]["message"] == 'Test "ok"'
 assert rows[0]["digits"] == "00123456"
 assert rows[0]["loop_stack_size"] == 32768
 assert rows[0]["loop_stack_free"] == 24000
 assert rows[0]["http_task"] == "httpd"
 assert rows[0]["http_stack_free"] == 1200
 assert len(rows[0]["boxes"]) == 8
 print("Status JSON tests passed: confidence, escaping, leading zeros, stack diagnostics")
