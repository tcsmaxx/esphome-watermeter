"""Exercise actual timeout recording, delayed reboot and persisted evidence."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parent.parent
cpp=(root/'components/meter_setup/meter_setup.cpp').read_text();h=(root/'components/meter_setup/meter_setup.h').read_text()
record=h[h.index('struct RecoveryRecord {'):h.index('struct LegacyIlluminationSettings {')]
methods=cpp[cpp.index('// Recovery keeps the worker'):cpp.rfind('\n}')]
timeout=cpp[cpp.index('  if(busy_ && !timed_out_'):cpp.index('  if(!busy_ && !capture_pending_')]
source=r'''
#include <string>
#include <cstring>
#include <ctime>
#include <cstdint>
#include <cassert>
#include <iostream>
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_SPIRAM 2
#define MALLOC_CAP_8BIT 4
#define ESP_LOGW(...)
#define ESP_LOGE(...)
uint32_t now_ms=0;uint32_t millis(){return now_ms;}
uint32_t heap_caps_get_free_size(int caps){return caps&1?12345:3456789;}
'''+record+r'''
struct Preference {RecoveryRecord stored{};bool save(RecoveryRecord *r){stored=*r;return true;}};
struct Globals{int syncs=0;bool sync(){++syncs;return true;}}globals;Globals *global_preferences=&globals;
struct AppType{int reboots=0;void safe_reboot(){++reboots;}}App;
struct AlignedMeterReader {bool paused=false;const char *phase()const{return "idle";}void set_pause_processing(bool v){paused=v;}};
struct Settings{uint32_t baseline=1864266;};
struct MeterSetup {
 RecoveryRecord recovery_{};Preference recovery_preference_;AlignedMeterReader reader;AlignedMeterReader *reader_=&reader;
 Settings settings_;int alignment_=0,saves=0;bool capture_pending_=false,inference_started_=true;uint8_t capture_stage_=0;
 bool busy_=true,timed_out_=false,paused_=false,reading_problem_=false,reboot_pending_=false,lamp=true;
 uint32_t frame_=6291,started_=0,reboot_at_=0,fault_saved_at_=0;std::string last_reader_log_="CRITICAL: Camera Frame Failure",alignment_result_="Referenzen fehlen",message_,reading_error_;
 int illumination_settings_=0;void set_illumination_(bool v,int){lamp=v;}bool save_configuration_(const Settings&,int,bool){++saves;return true;}
 std::string reader_phase_()const;void record_fault_(const std::string&,bool);void recovery_loop_();
 void check_timeout_(){
'''+timeout+r'''
 }
};
'''+methods+r'''
int main(){
 MeterSetup meter;now_ms=60000;meter.check_timeout_();assert(!meter.timed_out_);
 now_ms=60001;meter.check_timeout_();assert(meter.reboot_pending_&&meter.busy_&&meter.paused_&&!meter.lamp&&meter.reader.paused);
 assert(meter.recovery_.automatic_restarts==1&&meter.recovery_.consecutive_timeouts==1);
 assert(std::string(meter.recovery_.phase)=="awaiting_result");assert(meter.recovery_.free_heap==12345&&meter.recovery_.free_psram==3456789);
 assert(meter.recovery_.frame==6291&&std::string(meter.recovery_.reader_log)==meter.last_reader_log_);
 assert(meter.saves==1&&globals.syncs==1&&meter.settings_.baseline==1864266);
 now_ms=62000;meter.check_timeout_();assert(meter.recovery_.automatic_restarts==1);meter.recovery_loop_();assert(App.reboots==0);
 now_ms=65001;meter.recovery_loop_();assert(App.reboots==1);
 MeterSetup after_boot;after_boot.recovery_=meter.recovery_preference_.stored;assert(after_boot.recovery_.reason[0]&&after_boot.recovery_.automatic_restarts==1);
 std::cout<<"Recovery passed: timeout boundary, worker isolation, light off, persistent phase/log/heap/stand, grace period and one recovery request\n";
}
'''
with tempfile.TemporaryDirectory(prefix='meter-recovery-') as t:
 binary=str(Path(t)/'test');subprocess.run(['g++','-std=c++17','-x','c++','-','-o',binary],input=source,text=True,check=True);subprocess.run([binary],check=True)
